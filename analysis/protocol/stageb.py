"""Stage B: detector-response runs (mono-energetic, Allpix²). Generate -> validate -> run (container) -> convert.

    PYTHONPATH=. ./venv/bin/python -m analysis.protocol.stageb generate <campaign>
    docker compose run --rm -T --user 1000:1000 -e HOME=/tmp allpix \
        bash /data/simulation/protocol_runs/stageB/run_list.sh <campaign>
    PYTHONPATH=. ./venv/bin/python -m analysis.protocol.stageb convert <campaign>

Every setting below is traceable to inputs_register.csv (IDs in comments). Nothing is run unless
config_rules.validate() passes (PH-12: integration_time >= 1.5 x slowest drift).

Output per run (data/protocol_runs/stageB/<campaign>/):
  <name>.txt            TextWriter PixelCharge (deleted after conversion unless --keep)
  <name>_objects.root   MCTrack (record_all_tracks) -> interaction depth (deleted after conversion)
  <name>.npz            compact: pixel table (event, px, py, charge_e) + event table (event, z_wmean_mm,
                        z_min_mm, z_max_mm, t_e_wmean_ns, t_h_wmean_ns) + run metadata
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
import numpy as np
import pandas as pd

from analysis.protocol.config_rules import REPO, validate, drift_spec

SIM_DIR = REPO / "simulation/protocol_runs/stageB"
DATA_DIR = REPO / "data/protocol_runs/stageB"
CONTAINER_SIM = "/data/simulation/protocol_runs/stageB"
CONTAINER_OUT = "/data/output/protocol_runs/stageB"


@dataclass
class Detector:
    name: str
    pitch_um: float
    npix: tuple[int, int]          # REAL array (x along belt, y across) -- used for system-level edge modelling
    thickness_um: float
    bias_V: float
    tags: dict = field(default_factory=dict)
    # Stage B is the response per incident photon, scored in a central FIDUCIAL region (review 2026-11-05 item 2):
    #   beam     uniform flat GPS plane source, rectangular, direction +z, covering the fiducial square plus
    #            beam_margin_um on each side (flat beam verified: chi2/ndf 2.25 / 1.06 in x / y)
    #   fiducial fid_npix x fid_npix pixels at the matrix centre, aligned with pixel boundaries; an event is
    #            scored iff its primary photon's entry point (MCTrack, source plane) lies inside
    #   matrix   sim_npix, large enough that charge sharing and K-fluorescence from the fiducial stay inside
    #            (>= 1.2 mm margin; Cd/Te K x-ray attenuation length in CdTe <= ~0.1 mm)
    # Real array size and edges (LINDA 8x20) are a separate system-level model, not Stage B.
    sim_npix: tuple[int, int] | None = None
    fid_npix: int = 4
    beam_margin_um: float = 100.0

    @property
    def sim_array(self) -> tuple[int, int]:
        return self.sim_npix or self.npix

    @property
    def fid_half_mm(self) -> float:
        return self.fid_npix * self.pitch_um / 2e3

    @property
    def beam_half_mm(self) -> float:
        return self.fid_half_mm + self.beam_margin_um / 1e3


# CdTe transport (PH-01..PH-04, Arino-Estrada 2014, tag S): tau = mu-tau / mu
MU_E, MU_H = 1090.0, 110.0
TAU_E_NS = 2.7e-3 / MU_E * 1e9      # 2477 ns
TAU_H_NS = 1.8e-4 / MU_H * 1e9      # 1636 ns

DETECTORS = {
    # LINDA: 8 TDI rows along belt x 20 across, 330 um (D-L04/05/07, S); 1 mm CdTe (D-L03, S); bias A (D-L26 TBD)
    "linda": Detector("linda", 330, (8, 20), 1000, -500,
                      {"pitch": "S", "array": "S", "thickness": "S", "bias": "A (D-L26 TBD, bracket -300..-500)"},
                      sim_npix=(16, 16), fid_npix=4),
    # Medipix3 pixel-level patch (R-03): 64 x 64 at 55 um (D-M01, P); 1 mm CdTe (D-M05, A); bias A
    "medipix3": Detector("medipix3", 55, (64, 64), 1000, -500,
                         {"pitch": "P", "thickness": "A (protocol)", "bias": "A"}, fid_npix=16),
    # VAREX patch: 32 x 32 at 100 um (D-V03, S); thickness bracket 0.75/1/1.5/2 mm (D-V13) -> milestone 1 mm (A)
    "varex": Detector("varex", 100, (32, 32), 1000, -500,
                      {"pitch": "S", "thickness": "A (D-V13 bracket; milestone 1 mm)", "bias": "A"}, fid_npix=8),
    # Timepix3 CdTe for Exp0 V1 reference spectra (55 um, 1 mm): parameters to be matched to the publication
    "timepix3": Detector("timepix3", 55, (64, 64), 1000, -500,
                         {"pitch": "P", "thickness": "A (match publication)", "bias": "A (match publication)"},
                         fid_npix=16),
}

# Am-241 photon emission lines (keV, photons per decay). TO VERIFY against DDEP/LNHB (colleague) before V1 use.
AM241_LINES = [(13.9, 0.13), (17.75, 0.19), (20.8, 0.048), (26.34, 0.0227), (59.54, 0.3592)]

FANO_CDTE = 0.24   # PH-19: Allpix default for CdTe, now set explicitly (log: "Fano factor 0.24")

# Stage B variants (overrides of the baseline transport); used by the Exp 0 V1 FWHM breakdown.
VARIANTS = {
    "base": {},
    "notrap": dict(trapping=False),                       # electron trapping off
    "nofano": dict(fano=1e-4),                            # Fano ~ 0 (pair statistics off)
    "ideal": dict(trapping=False, fano=1e-4),             # both off: deposited energy only
    "transient": dict(transport="transient", events=3000),                        # induced charge, holes
    "transient_mutau1e-5": dict(transport="transient", events=3000, tau_h_ns=1e-5 / MU_H * 1e9),  # PH-04 low
}

CAMPAIGNS = {
    # first milestone: LINDA, Medipix3, VAREX at 1 mm, reduced statistics, 10 keV grid 10-300 keV
    "milestone1": dict(detectors=["linda", "medipix3", "varex"],
                       energies=[float(e) for e in range(10, 301, 10)], events=20000, seed=101),
    # Exp0 V1 preparation: Am-241 lines. Timepix3 uses the SAME Stage B as Medipix3 until the publication's
    # sensor parameters (thickness, bias) arrive -- only Stage C electronics differ (no duplicate runs).
    "exp0_v1_am241": dict(detectors=["medipix3"],
                          energies=[e for e, _ in AM241_LINES], events=50000, seed=201),
    # Exp0 V1 FWHM breakdown at 59.54 keV (review 2026-11-05 item 1)
    "exp0_v1_fwhm": dict(detectors=["medipix3"], energies=[59.54], events=50000, seed=301,
                         variants=["base", "notrap", "nofano", "ideal", "transient", "transient_mutau1e-5"]),
}

STAGEB_DET_ALIAS = {"timepix3": "medipix3"}   # Stage B shared until Timepix3 publication parameters exist


def run_name(campaign: str, det: str, E: float, variant: str = "base") -> str:
    n = f"pr_{campaign}_{det}_{E:g}keV".replace(".", "p")
    return n if variant == "base" else f"{n}_{variant}"


def gps_macro(det: Detector, E_keV: float) -> str:
    h = det.beam_half_mm
    return f"""# Uniform flat beam (review 2026-11-05 item 2): GPS plane source, rectangle, fixed direction +z
/gps/particle gamma
/gps/pos/type Plane
/gps/pos/shape Rectangle
/gps/pos/centre 0 0 -10 mm
/gps/pos/halfx {h:.4f} mm
/gps/pos/halfy {h:.4f} mm
/gps/direction 0 0 1
/gps/ene/type Mono
/gps/ene/mono {E_keV:g} keV
"""


def config_text(det: Detector, E_keV: float, events: int, seed: int, name: str, out_dir: str,
                macro_path: str, variant: dict | None = None) -> tuple[str, str]:
    v = variant or {}
    nx, ny = det.sim_array
    det_conf = f"""[{det.name}]
type = "medipix3"
position = 0 0 0
orientation = 0 0 0
number_of_pixels = {nx} {ny}
pixel_size = {det.pitch_um}um {det.pitch_um}um
sensor_thickness = {det.thickness_um}um
sensor_material = "cadmium_telluride"
"""
    tau_h = v.get("tau_h_ns", TAU_H_NS)
    trapping = (f"""trapping_model = "constant"
trapping_time_electron = {TAU_E_NS:.0f}ns
trapping_time_hole = {tau_h:.1f}ns""" if v.get("trapping", True) else 'trapping_model = "none"')
    common = f"""temperature = 293K
# PH-12: integration_time >= 1.5 x slowest drift (validated before run)
integration_time = 1us
mobility_model = "constant"
mobility_electron = {MU_E:g}cm*cm/V/s
mobility_hole = {MU_H:g}cm*cm/V/s
{trapping}"""
    if v.get("transport", "generic") == "transient":
        # Induced charge (Shockley-Ramo), both carriers; settings from feasibility spike 3 (constant field)
        transport = f"""[WeightingPotentialReader]
model = "pad"

[TransientPropagation]
charge_per_step = 100
timestep = 0.5ns
distance = 1
{common}

[PulseTransfer]"""
    else:
        transport = f"""[GenericPropagation]
charge_per_step = 10
propagate_holes = false
{common}

[SimpleTransfer]
max_depth_distance = 5um"""
    main = f"""[Allpix]
log_level = "WARNING"
number_of_events = {events}
detectors_file = "{CONTAINER_SIM}/detector_{det.name}.conf"
random_seed = {seed}
output_directory = "{out_dir}"
root_file = "{name}_modules"

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
# PH-09: QGSP_BERT_LIV, Allpix default range cut
physics_list = QGSP_BERT_LIV
record_all_tracks = true
# Uniform flat beam over the fiducial square + margin (GPS macro); scoring by primary entry point
source_type = "macro"
file_name = "{macro_path}"
number_of_particles = 1
# PH-05 / PH-19: pair creation energy and Fano factor set explicitly
charge_creation_energy = 4.43eV
fano_factor = {v.get("fano", FANO_CDTE):g}

[ElectricFieldReader]
# PH-16 (decision, A): constant field for a fully depleted CdTe sensor
model = "constant"
bias_voltage = {det.bias_V:g}V

{transport}

[DetectorHistogrammer]

[TextWriter]
file_name = "{name}"
include = "PixelCharge"

[ROOTObjectWriter]
file_name = "{name}_objects"
include = "MCTrack"
"""
    return det_conf, main


def generate(campaign: str) -> Path:
    c = CAMPAIGNS[campaign]
    cdir = SIM_DIR / campaign
    cdir.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / campaign).mkdir(parents=True, exist_ok=True)
    names = []
    for dn in c["detectors"]:
        det = DETECTORS[dn]
        for E in c["energies"]:
            for vn in c.get("variants", ["base"]):
                v = VARIANTS[vn]
                name = run_name(campaign, dn, E, vn)
                (cdir / f"{name}.mac").write_text(gps_macro(det, E))
                det_conf, main = config_text(det, E, v.get("events", c["events"]), c["seed"], name,
                                             f"{CONTAINER_OUT}/{campaign}", f"{CONTAINER_SIM}/{campaign}/{name}.mac", v)
                (SIM_DIR / f"detector_{dn}.conf").write_text(det_conf)
                p = cdir / f"{name}.conf"
                p.write_text(main)
                validate(p)  # raises IntegrationTimeError -> nothing is written to the run list
                names.append(name)
    (cdir / "run_list.txt").write_text("\n".join(names) + "\n")
    meta = dict(campaign=campaign, **c, detectors_spec={d: asdict(DETECTORS[d]) for d in c["detectors"]},
                variants_spec={vn: VARIANTS[vn] for vn in c.get("variants", ["base"])}, fano=FANO_CDTE,
                transport=dict(mu_e=MU_E, mu_h=MU_H, tau_e_ns=TAU_E_NS, tau_h_ns=TAU_H_NS))
    (cdir / "campaign.json").write_text(json.dumps(meta, indent=1))
    runner = SIM_DIR / "run_list.sh"
    runner.write_text(f"""#!/bin/bash
# Run every config in <campaign>/run_list.txt (resumable). Generated by analysis/protocol/stageb.py.
set -uo pipefail
C=$1; D={CONTAINER_SIM}/$C; O={CONTAINER_OUT}/$C; mkdir -p $O
LOG=$O/run_log.csv; [ -f $LOG ] || echo "name,status,seconds,allpix_version" > $LOG
V=$(allpix --version 2>/dev/null | sed -n '1p' | tr -d ',\\n')
while read -r n; do
  [ -z "$n" ] && continue
  {{ [ -f "$O/$n.npz" ] || [ -f "$O/$n.txt" ]; }} && continue
  t0=$(date +%s)
  if allpix -c "$D/$n.conf" > "$O/$n.log" 2>&1 && [ -f "$O/$n.txt" ]; then st=ok; else st=FAILED; fi
  # depth + primary entry point per event (C++ reader; validated vs drift.track_depths, tests/test_protocol.py)
  [ $st = ok ] && (cd /tmp && /data/output/protocol_runs/bin/mctrack_depths "$O/${{n}}_objects.root" "$O/${{n}}_depths.csv") || true
  echo "$n,$st,$(( $(date +%s) - t0 )),$V" >> $LOG
done < "$D/run_list.txt"
echo "done: $(grep -c ',ok,' $LOG) ok, $(grep -c FAILED $LOG) failed"
""")
    print(f"{campaign}: {len(names)} configs generated and validated in {cdir.relative_to(REPO)}")
    return cdir


def convert(campaign: str, keep: bool = False) -> None:
    """TextWriter + MCTrack -> compact npz with per-event depth and drift times."""
    from analysis.protocol.textwriter import read_pixel_charge
    from analysis.protocol.drift import track_depths, drift_time_ns
    cdir, odir = SIM_DIR / campaign, DATA_DIR / campaign
    for name in (cdir / "run_list.txt").read_text().split():
        txt, obj, out = odir / f"{name}.txt", odir / f"{name}_objects.root", odir / f"{name}.npz"
        if out.exists() or not txt.exists():
            continue
        conf = cdir / f"{name}.conf"
        spec, info = drift_spec(conf)
        pix, n_events = read_pixel_charge(txt)
        dcsv = odir / f"{name}_depths.csv"   # from simulation/protocol_runs/tools/mctrack_depths (C++, validated vs track_depths)
        if dcsv.exists():
            ev = pd.read_csv(dcsv).set_index("event")
        else:
            ev = track_depths(obj) if obj.exists() else None
        z_imp = spec.thickness_cm * 10 / 2  # pixel implant at +d/2 (verified: feasibility drift validation)
        if ev is not None and len(ev):
            ev["t_e_wmean_ns"] = drift_time_ns(spec, ev.z_wmean_mm.to_numpy(), z_imp, "e")
            ev["t_h_wmean_ns"] = drift_time_ns(spec, ev.z_wmean_mm.to_numpy(), z_imp, "h")
        meta = dict(name=name, n_events=n_events, config_sha256=hashlib.sha256(conf.read_bytes()).hexdigest(),
                    **{k: v for k, v in info.items() if isinstance(v, (int, float, str, bool, type(None)))})
        np.savez_compressed(
            out,
            pix_event=pix.event.to_numpy(np.int32), pix_x=pix.px.to_numpy(np.int16), pix_y=pix.py.to_numpy(np.int16),
            pix_charge_e=pix.charge_e.to_numpy(np.float32),
            ev_event=(ev.index.to_numpy(np.int32) if ev is not None else np.array([], np.int32)),
            **({c: ev[c].to_numpy(np.float32) for c in ev.columns} if ev is not None else {}),
            meta=json.dumps(meta))
        if not keep:
            txt.unlink(); obj.unlink(missing_ok=True); dcsv.unlink(missing_ok=True)
        print("converted", name, len(pix), "pixel records")


def fiducial(d: dict, det: Detector) -> tuple[np.ndarray, int]:
    """Events whose primary photon enters inside the central fiducial square, and their count (= the number of
    incident photons to normalise per-photon quantities; non-interacting photons are included)."""
    if "x0_mm" not in d:
        raise ValueError(f"{d['meta']['name']}: no primary entry points (run predates the flat-beam set-up)")
    h = det.fid_half_mm
    m = (np.abs(d["x0_mm"]) < h) & (np.abs(d["y0_mm"]) < h)
    return d["ev_event"][m], int(m.sum())


def load_fiducial(campaign: str, name: str, det: Detector) -> tuple[pd.DataFrame, int, dict]:
    """Pixel table restricted to fiducial events, the fiducial photon count, and the raw npz dict."""
    d = load(campaign, name)
    ev, n = fiducial(d, det)
    pix = pd.DataFrame(dict(event=d["pix_event"], px=d["pix_x"], py=d["pix_y"], charge_e=d["pix_charge_e"]))
    return pix[pix.event.isin(ev)].reset_index(drop=True), n, d


def load(campaign: str, name: str) -> dict:
    z = np.load(DATA_DIR / campaign / f"{name}.npz", allow_pickle=False)
    d = {k: z[k] for k in z.files}
    d["meta"] = json.loads(str(d["meta"]))
    return d


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("action", choices=["generate", "convert"]); a.add_argument("campaign")
    a.add_argument("--keep", action="store_true")
    o = a.parse_args()
    generate(o.campaign) if o.action == "generate" else convert(o.campaign, o.keep)
