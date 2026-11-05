"""Exp 0 V1: breakdown of the Medipix3 CSM 59.54 keV FWHM (review 2026-11-05 item 1).

The Am-241 59.54 keV peak region contains only the 59.54 keV line (the other lines and their escape peaks lie
below 37 keV), so the breakdown uses the mono 59.54 keV Stage B runs of campaign exp0_v1_fwhm (flat beam,
16 x 16 pixel fiducial, 50k photons; transient variants 3k photons).

Stage B variants (physics in the charge signal):
  ideal      no Fano (F = 1e-4), no trapping          -> deposited energy only
  nofano     trapping on, F ~ 0
  notrap     Fano 0.24, no trapping
  base       Fano 0.24 + electron trapping (tau_e 2477 ns), electrons only, SimpleTransfer (no hole signal)
  transient  induced charge (Shockley-Ramo, pad weighting potential), both carriers, mu-tau_h 1.8e-4
  transient_mutau1e-5   same, mu-tau_h 1e-5 cm2/V (PH-04 low end)
Stage C (electronics):
  summing    "full" = all pixels of the event (complete summing), "2x2" = Medipix3 CSM block
  noise      sigma per pixel and where it enters (electronics.Electronics.noise_mode)
  dispersion per-pixel threshold offset sigma (energy-scale shift of the pixel)
Ballistic deficit proper (finite CSA shaping) is NOT in any Stage B variant: SimpleTransfer / PulseTransfer
integrate the full 1 us. That needs the X0-CSA model (required, not built). The transient rows give the
induced-charge / hole-trapping part only.
Contribution of an effect = sqrt(FWHM_with^2 - FWHM_without^2) (quadrature; meaningful while shapes stay
near-Gaussian -- the direct FWHM is reported alongside).
Output: analysis/protocol/exp0/v1/fwhm_breakdown.csv, fwhm_single_vs_shared.csv
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

from analysis.protocol.stageb import DETECTORS, load_fiducial, run_name
from analysis.protocol.electronics import Electronics, signals, W_EV
from analysis.protocol.exp0_v1 import BINS, CENTRES, peak_metrics, multi_pixel_fraction

R = Path(__file__).resolve().parents[2]
OUT = R / "analysis/protocol/exp0/v1"
CAMP, DET, E = "exp0_v1_fwhm", "medipix3", 59.54
THR_KEV = 5.0
FANO, W = 0.24, 4.43


def _load(variant):
    return load_fiducial(CAMP, run_name(CAMP, DET, E, variant), DETECTORS[DET])


def energies(variant: str, summing: str, noise: float = 0.0, noise_mode: str = "pixel", disp: float = 0.0,
             seed: int = 12345):
    pix, n_fid, _ = _load(variant)
    D = DETECTORS[DET]
    rng = np.random.default_rng(seed)
    if summing == "full":
        g = pix.groupby("event").charge_e
        q = g.sum().to_numpy()
        k = g.size().to_numpy()
        if noise > 0:
            q = q + rng.normal(0, 1, len(q)) * noise * np.sqrt(k)      # noise of every summed (recorded) pixel
        e = q * W / 1e3
    else:
        el = Electronics([THR_KEV], sigma_noise_e=noise, summing="nxn", neighbourhood=2, noise_mode=noise_mode,
                         sigma_disp_e=disp, seed=seed)
        s = signals(pix, el, D.sim_array)
        q = s.charge_e.to_numpy()
        if disp > 0:
            off = np.random.default_rng(seed + 1).normal(0, disp, size=D.sim_array)
            q = q - off[s.px.to_numpy(), s.py.to_numpy()]
        e = q * W / 1e3
    e = e[e >= THR_KEV]
    return np.histogram(e, BINS)[0] / n_fid, n_fid, pix


ROWS = [
    # label, stageB variant, summing, noise_e, noise_mode, dispersion_e
    ("A1 deposited energy only (no Fano, no trapping), full summing", "ideal", "full", 0, "pixel", 0),
    ("A2 + Fano 0.24", "notrap", "full", 0, "pixel", 0),
    ("A3 + electron trapping = Stage B base", "base", "full", 0, "pixel", 0),
    ("A4 + incomplete summing (2x2 block)", "base", "2x2", 0, "pixel", 0),
    ("A5 + noise 80 e-/pixel on all 4 block pixels (new V1 default)", "base", "2x2", 80, "pixel_all", 0),
    ("A6 + threshold dispersion 20 e-", "base", "2x2", 80, "pixel_all", 20),
    ("A6 + threshold dispersion 40 e-", "base", "2x2", 80, "pixel_all", 40),
    ("A6 + threshold dispersion 80 e-", "base", "2x2", 80, "pixel_all", 80),
    ("A7 induced charge, mu-tau_h 1.8e-4 (transient) instead of base, A5 electronics", "transient", "2x2", 80, "pixel_all", 0),
    ("A8 induced charge, mu-tau_h 1e-5 (transient), A5 electronics", "transient_mutau1e-5", "2x2", 80, "pixel_all", 0),
    ("T1 transient mu-tau_h 1.8e-4, full summing, no noise", "transient", "full", 0, "pixel", 0),
    ("T2 transient mu-tau_h 1e-5, full summing, no noise", "transient_mutau1e-5", "full", 0, "pixel", 0),
    # the setting that produced the reported 3.5 keV, and one-at-a-time switch-offs from it
    ("B0 REPORTED SETTING: base, 2x2, 175 e- on every recorded pixel then summed", "base", "2x2", 175, "pixel", 0),
    ("B1  B0 with noise off", "base", "2x2", 0, "pixel", 0),
    ("B2  B0 with threshold dispersion off (it was already 0)", "base", "2x2", 175, "pixel", 0),
    ("B3  B0 with incomplete summing off (full summing)", "base", "full", 175, "pixel", 0),
    ("B4  B0 with electron trapping off", "notrap", "2x2", 175, "pixel", 0),
    ("B5  B0 with Fano off", "nofano", "2x2", 175, "pixel", 0),
    ("B6  B0 with hole/induced-charge tail on (transient 1.8e-4) -- not in B0", "transient", "2x2", 175, "pixel", 0),
    ("N1 noise 175 e- applied once to the summed signal", "base", "2x2", 175, "summed", 0),
    ("N2 noise 175 e- on all 4 block pixels", "base", "2x2", 175, "pixel_all", 0),
]


SPLIT = [  # label, stageB variant, noise_e, noise_mode
    ("no noise", "base", 0, "pixel"),
    ("legacy: 175 e- on recorded pixels only, then summed", "base", 175, "pixel"),
    ("NEW: 80 e- on every pixel (incl. empty), every event; block = largest noisy sum (chip)", "base", 80, "pixel_all"),
    ("same, block chosen on noiseless charge (diagnostic)", "base", 80, "pixel_all/true"),
    ("175 e- once on the summed signal", "base", 175, "summed"),
]
SINGLE_FRAC = 0.99   # clean single-pixel event: the seed pixel holds >= 99% of the event's (noiseless) charge


def split_run() -> pd.DataFrame:
    """CSM 59.54 keV FWHM for clean single-pixel events vs shared events (review 2026-11-05 item 1).
    Class from noiseless Stage B charge; signals from the 2x2 CSM chain; normalised per fiducial photon."""
    rows = []
    for label, var, noise, mode in SPLIT:
        pix, n_fid, _ = _load(var)
        g = pix.groupby("event").charge_e
        frac = (g.max() / g.sum())
        cls = pd.Series(np.where(frac >= SINGLE_FRAC, "single", "shared"), index=frac.index)
        nm, _, arb = mode.partition("/")
        el = Electronics([THR_KEV], sigma_noise_e=noise, summing="nxn", neighbourhood=2, noise_mode=nm,
                         arbitration=arb or "noisy")
        sig = signals(pix, el, DETECTORS[DET].sim_array)
        sig["cls"] = cls.reindex(sig.event).to_numpy()
        for c in ("single", "shared"):
            e = sig.loc[sig.cls == c, "charge_e"].to_numpy() * W / 1e3
            h = np.histogram(e[e >= THR_KEV], BINS)[0] / n_fid
            rows.append(dict(noise_case=label, event_class=c, n_events=int((cls == c).sum()),
                             **peak_metrics(CENTRES, h, E)))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "fwhm_single_vs_shared.csv", index=False)
    return df


def run() -> pd.DataFrame:
    rows = []
    for label, var, summ, noise, mode, disp in ROWS:
        h, n_fid, pix = energies(var, summ, noise, mode, disp)
        m = peak_metrics(CENTRES, h, E)
        rows.append(dict(case=label, stageB=var, summing=summ, noise_e=noise, noise_mode=mode, dispersion_e=disp,
                         n_fiducial=n_fid, **m, multi_pixel_5keV=multi_pixel_fraction(pix, 5.0)))
    df = pd.DataFrame(rows)
    b0 = df.loc[df.case.str.startswith("B0"), "fwhm_keV"].iloc[0]
    df["contribution_vs_B0_keV"] = np.where(df.case.str.match(r"B[1-5]"),
                                            np.sqrt(np.clip(b0 ** 2 - df.fwhm_keV ** 2, 0, None)), np.nan)
    df["provisional"] = "PROVISIONAL (tag A): Fano 0.24 (PH-06 conflict), D-M04/D-M12 placeholders, transport PH-01..04"
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "fwhm_breakdown.csv", index=False)
    return df


def expected() -> dict:
    """Analytic expectations at 59.54 keV (FWHM, keV)."""
    k = 2.3548 * W / 1e3
    return dict(fano=k * np.sqrt(FANO * E * 1e3 / W), noise_175_once=k * 175, noise_80_x4=k * 80 * 2,
                noise_175_x4=k * 175 * 2)


if __name__ == "__main__":
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 90)
    print({k: round(v, 3) for k, v in expected().items()})
    print(split_run()[["noise_case", "event_class", "n_events", "peak_keV", "fwhm_keV", "fwhm_direct_keV"]].round(3).to_string(index=False))
    df = run()
    print(df[["case", "n_fiducial", "peak_keV", "fwhm_keV", "fwhm_direct_keV", "tail_over_core",
              "contribution_vs_B0_keV"]].round(3).to_string(index=False))
