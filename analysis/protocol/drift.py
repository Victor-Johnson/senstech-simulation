"""Per-photon drift time from interaction depth (review item 2).

Electrons drift from each deposit to the pixel (implant) side; holes drift to the opposite (bias) side.
For a deposit at local depth z in a sensor of thickness d with the implant at z_imp:

    t_e(z) = integral over the path z -> z_imp of dz' / v_e(E(z'))
    t_h(z) = integral over the path z -> z_back of dz' / v_h(E(z'))

with the field and mobility taken from the same DriftSpec as the integration_time rule (config_rules.py),
so the timing layer and the config validator can never disagree.

Per event (one photon) this module reports the charge-weighted and maximum electron and hole drift times,
which feed the time-domain layer (TL-07): the pulse of a photon starts at its Poisson arrival time and its
induced current lasts for its own drift times instead of one constant per detector.

Also provides a TextWriter parser for DepositedCharge / PropagatedCharge blocks (validation only; too large
for production -- see feasibility_report.md).
"""
from __future__ import annotations
import re
from pathlib import Path
import numpy as np
import pandas as pd
from analysis.protocol.config_rules import DriftSpec, jacoboni_velocity

_NUM = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"


def field_at(spec: DriftSpec, depth_from_depleting_side_cm: np.ndarray) -> np.ndarray:
    d, V = spec.thickness_cm, abs(spec.bias_V)
    x = np.clip(depth_from_depleting_side_cm, 0, d)
    if spec.field_model == "linear":
        Vd = abs(spec.depletion_V) if spec.depletion_V is not None else V
        return (V - Vd) / d + 2 * Vd / d * (1 - x / d)
    return np.full_like(x, V / d, dtype=float)


def velocity(spec: DriftSpec, E: np.ndarray, carrier: str) -> np.ndarray:
    if spec.mobility_model == "jacoboni":
        return jacoboni_velocity(E, carrier, spec.temperature_K)
    mu = spec.mu_e if carrier == "e" else spec.mu_h
    return mu * E


def drift_time_ns(spec: DriftSpec, z_local_mm: np.ndarray, z_implant_mm: float, carrier: str,
                  n: int = 400) -> np.ndarray:
    """Drift time (ns) for carriers created at local z (mm), sensor centred at z=0.

    The linear field model is measured from the implant side (Allpix default: depletion from the implant),
    so depth x = |z - z_implant|.
    """
    z = np.atleast_1d(np.asarray(z_local_mm, float))
    d_mm = spec.thickness_cm * 10
    z_back = -z_implant_mm  # opposite face
    target = z_implant_mm if carrier == "e" else z_back
    out = np.empty_like(z)
    for i, zi in enumerate(z):
        path = np.linspace(zi, target, n + 1)
        mid = 0.5 * (path[1:] + path[:-1])
        x_cm = np.abs(mid - z_implant_mm) / 10
        v = velocity(spec, field_at(spec, x_cm), carrier)
        out[i] = np.sum(np.abs(np.diff(path)) / 10 / v) * 1e9
    assert d_mm > 0
    return out


def parse_charges(path: str | Path, kinds=("Deposited", "Propagated")) -> pd.DataFrame:
    """Parse DepositedCharge / PropagatedCharge blocks: event, kind, carrier, state, charge, x, y, z (local mm), t (ns)."""
    rows, ev, cur = [], None, None
    for line in open(path):
        if line.startswith("==="):
            m = re.match(r"=== (\d+) ===", line); ev = int(m.group(1)) if m else ev; cur = None; continue
        if line.startswith("--- "):
            cur = None
            for k in kinds:
                if line.startswith(f"--- {k} charge information"):
                    cur = {"event": ev, "kind": k, "state": ""}
            continue
        if cur is None:
            continue
        if line.startswith("Type:"):
            cur["carrier"] = line.split()[1].strip('"')
        elif line.startswith("State:"):
            cur["state"] = line.split()[1]
        elif line.startswith("Charge:"):
            cur["charge"] = abs(float(re.findall(_NUM, line)[0]))
        elif line.startswith("Local Position"):
            cur["x"], cur["y"], cur["z"] = (float(v) for v in re.findall(_NUM, line.split("(")[1])[:3])
        elif line.startswith("Local time"):
            cur["t"] = float(re.findall(_NUM, line.split(":")[1])[0]); rows.append(cur); cur = None
    return pd.DataFrame(rows)


def per_event_drift(dep: pd.DataFrame, spec: DriftSpec, z_implant_mm: float) -> pd.DataFrame:
    """Charge-weighted and max electron/hole drift time per event from its deposits (electron deposits only:
    every deposit creates an equal e/h pair at the same point)."""
    e = dep[(dep.kind == "Deposited") & (dep.carrier == "e")].copy()
    e["t_e"] = drift_time_ns(spec, e.z.to_numpy(), z_implant_mm, "e")
    e["t_h"] = drift_time_ns(spec, e.z.to_numpy(), z_implant_mm, "h")
    g = e.groupby("event")
    return pd.DataFrame({
        "charge": g.charge.sum(),
        "z_mean_mm": g.apply(lambda t: np.average(t.z, weights=t.charge)),
        "t_e_wmean_ns": g.apply(lambda t: np.average(t.t_e, weights=t.charge)),
        "t_e_max_ns": g.t_e.max(),
        "t_h_wmean_ns": g.apply(lambda t: np.average(t.t_h, weights=t.charge)),
        "t_h_max_ns": g.t_h.max(),
    })


def track_depths(objects_root: str | Path, sensor_vol_substr: str = "sensor", z_offset_mm: float = 0.0,
                 entry_stop: int | None = None) -> pd.DataFrame:
    """Production source of interaction depth: MCTrack start points (ROOTObjectWriter, record_all_tracks=true).

    For each event, electrons (PDG 11) that start inside the sensor are the ionisation sites; their initial
    kinetic energy is the charge they will create (electron range << sensor thickness at these energies).
    Returns per event: KE-weighted mean z and min/max z (local mm = global z - z_offset_mm).
    Event index = entry number + 1 (matches TextWriter event numbering).
    """
    import uproot
    arr = uproot.open(objects_root)["MCTrack"]["global"].array(library="np", entry_stop=entry_stop)
    rows = []
    for i, ev in enumerate(arr):
        zs, ws = [], []
        for t in ev:
            if t.member("particle_id_") == 11 and sensor_vol_substr in t.member("start_g4_vol_name_"):
                p = t.member("start_point_")
                zs.append(p.member("fCoordinates").member("fZ") - z_offset_mm); ws.append(t.member("initial_kin_E_"))
        if zs:
            zs, ws = np.array(zs), np.array(ws)
            rows.append((i + 1, np.average(zs, weights=ws) if ws.sum() > 0 else zs.mean(), zs.min(), zs.max(), ws.sum() * 1e3))
    return pd.DataFrame(rows, columns=["event", "z_wmean_mm", "z_min_mm", "z_max_mm", "e_keV"]).set_index("event")
