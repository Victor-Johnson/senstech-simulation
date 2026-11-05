#!/usr/bin/env python3
"""Phase 2 -- Theoretical Reference Framework (v2/v3) selection experiment.

Produces the framework's Table 10 for BOTH scenarios from v3 Section 9:
  * NATIVE  (Sec 9.1) -- each chip at the CdTe thickness it ships with (EIGER2 0.75 mm, rest 1 mm)
  * MATCHED (Sec 9.2) -- all six at a common 1 mm

For each detector x alloy (30 combos) and each scenario:
  N_theory = N0 * sum_{E in [Emin,Emax]} w(E) * T_a(E) * P_CdTe(E, thickness)   [analytic step-window]
  N_sim    = N0 * sum_E w(E) * T_a(E) * R_d(E)                                   [hybrid, R_d from p2_bare ROOTs]
plus delta, a basic pooled chi^2 (sigma_sim only), and CNR.

Detector params: framework v3 Table 8/8a. Thickness enters both P_CdTe (analytic)
and which bare ROOT is read (EIGER2 native reads the p2_bare_eiger2_075mm_* files).
"""
from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
import numpy as np
import pandas as pd

import analysis.scripts.material_penetration_experiment as m

ROOT = Path("/home/victor-pc/itek/senstech-simulation")
UNIFORM = ROOT / "analysis/results/material_penetration_uniform"
OUT = ROOT / "analysis/results/phase2_selection_framework"
DATA = ROOT / "data"
N0 = 1_000_000
EPS = m.EPSILON_CDTE_EV


@dataclass(frozen=True)
class Det:
    key: str
    label: str
    lower_keV: float
    upper_keV: float
    bins: int
    proxy: bool

    @property
    def root_detector(self) -> str:
        return f"{self.key}_detector"


DETS = [
    Det("medipix3", "D1 Medipix3", 3.10, 110.0, 2, False),
    Det("medipix4", "D6 Medipix4", 7.85, 150.0, 2, False),
    Det("timepix3_cdte", "D4 Timepix3", 2.21, 120.0, 2, False),
    Det("timepix4", "D5 Timepix4", 4.43, 150.0, 2, False),
    Det("eiger2", "D2 EIGER2", 4.00, 80.0, 2, False),
    Det("hexitec_proxy", "D3 HEXITEC", 2.00, 200.0, 2, True),
]
ALLOYS = {
    "alloy1": "C11000 Cu", "alloy2": "C36000 brass", "alloy3": "C70600 CuNi 90/10",
    "alloy4": "C95500 Al bronze", "alloy5": "C17200 BeCu",
}

# v3 Table 8a native commercial CdTe thickness (mm). Only EIGER2 differs from 1 mm.
NATIVE_MM = {"medipix3": 1.0, "medipix4": 1.0, "timepix3_cdte": 1.0,
             "timepix4": 1.0, "eiger2": 0.75, "hexitec_proxy": 1.0}
SCENARIOS = {
    "native": NATIVE_MM,                          # v4 Table 10 (§9) -- commercial thickness
    "matched": {d.key: 0.75 for d in DETS},       # v4 Table 10b (§10) -- common 0.75 mm
}


def bare_root_path(det_key: str, thick_mm: float, energy: float) -> Path:
    """1 mm runs are the plain p2_bare_*; the EIGER2 native 0.75 mm runs carry the
    _075mm tag written by the driver's OUTPUT_TAG."""
    tag = "_075mm" if abs(thick_mm - 0.75) < 1e-6 else ""
    return DATA / f"p2_bare_{det_key}{tag}_{energy:.0f}keV.root"


def load_inputs():
    w = pd.read_csv(ROOT / "spectra/150kvp_weights.csv")
    weights = dict(zip(w.energy_keV.astype(float), w.weight))
    att = pd.read_csv(UNIFORM / "alloy_attenuation.csv")
    T = {a: att[att.alloy == a].set_index("energy_keV").transmission.to_dict() for a in ALLOYS}
    ci = pd.read_csv(UNIFORM / "cdte_interaction.csv").set_index("energy_keV")
    mu = ci["mu_linear_cm_inv"].to_dict()           # CdTe linear atten, for P at any thickness
    manifest = m.load_manifest(DATA / "phase2_selection_run_manifest.csv")
    return weights, T, mu, manifest


def P_cdte(mu: dict, energy: float, thick_mm: float) -> float:
    return 1.0 - np.exp(-mu[energy] * thick_mm / 10.0)


def bare_windowed_response(det: Det, thick_mm: float, energy: float, events: int) -> tuple[float, float]:
    rpath = bare_root_path(det.key, thick_mm, energy)
    if not rpath.exists():
        return np.nan, np.nan
    counts, charge_ke = m.read_cluster_charge(rpath, det.root_detector)
    cluster_count = float(np.sum(counts))
    detected = m.read_detected_event_count(rpath, det.root_detector)
    charge_energy = charge_ke * EPS
    edges = np.linspace(det.lower_keV, det.upper_keV, det.bins + 1)
    in_win = (charge_energy >= edges[0]) & (charge_energy <= edges[-1])
    window_acc = float(np.sum(counts[in_win])) / cluster_count if cluster_count > 0 else 0.0
    intrinsic = min(detected / events, 1.0)
    r = min(intrinsic * window_acc, intrinsic)
    return r, float(m.binomial_se(r, events))


def build_table(weights, T, mu, manifest, thick_by_det: dict) -> pd.DataFrame:
    rows = []
    for det in DETS:
        t_mm = thick_by_det[det.key]
        for a, aname in ALLOYS.items():
            n_theory = n_sim = var_sim = 0.0
            sim_ok = True
            for E in sorted(weights):
                wE, tE = weights[E], T[a][E]
                pE = P_cdte(mu, E, t_mm)
                if det.lower_keV <= E <= det.upper_keV:
                    n_theory += N0 * wE * tE * pE
                events = m.get_events(manifest, "bare", det.key, E, 10000)
                r, r_se = bare_windowed_response(det, t_mm, E, events)
                if np.isnan(r):
                    sim_ok = False
                    continue
                n_sim += N0 * wE * tE * r
                var_sim += (N0 * wE * tE * r_se) ** 2
            rows.append({
                "detector": det.key, "detector_label": det.label, "alloy": a, "alloy_name": aname,
                "proxy": det.proxy, "thickness_mm": t_mm, "N_theory": n_theory,
                "N_sim": n_sim if sim_ok else np.nan,
                "sigma_sim": np.sqrt(var_sim) if sim_ok else np.nan,
                "delta_pct": (100 * (n_sim - n_theory) / n_theory) if (sim_ok and n_theory > 0) else np.nan,
            })
    return pd.DataFrame(rows)


def cnr_table(table: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for det in DETS:
        d = table[table.detector == det.key].set_index("alloy")
        for a1, a2 in combinations(ALLOYS, 2):
            def cnr(col):
                n1, n2 = d.loc[a1, col], d.loc[a2, col]
                return abs(n1 - n2) / np.sqrt(n1 + n2) if np.isfinite(n1) and np.isfinite(n2) and (n1 + n2) > 0 else np.nan
            rows.append({"detector": det.key, "pair": f"{a1}-{a2}",
                         "CNR_theory": cnr("N_theory"), "CNR_sim": cnr("N_sim")})
    return pd.DataFrame(rows)


def summarise(table: pd.DataFrame, scenario: str):
    have = table["N_sim"].notna().any()
    g = table.groupby(["detector", "detector_label", "proxy", "thickness_mm"], sort=False).agg(
        N_theory=("N_theory", "mean"), N_sim=("N_sim", "mean"), delta=("delta_pct", "mean")).reset_index()
    g = g.sort_values("N_sim" if have else "N_theory", ascending=False)
    print(f"\n===== {scenario.upper()} thickness =====")
    for r in g.itertuples():
        sim = f"{r.N_sim:9,.0f}" if np.isfinite(r.N_sim) else "  (no sim)"
        dl = f"{r.delta:+5.1f}%" if np.isfinite(r.delta) else "  --"
        print(f"  {r.detector_label:13} [{r.thickness_mm:.2f}mm]  N_theory={r.N_theory:9,.0f}  N_sim={sim}  d={dl}")
    if have:
        real = g[~g.proxy]
        print("  real-chip ranking (N_sim):", " > ".join(real.detector_label))
    return g


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data_csv").mkdir(exist_ok=True)
    weights, T, mu, manifest = load_inputs()
    for scenario, thick in SCENARIOS.items():
        table = build_table(weights, T, mu, manifest, thick)
        cnr = cnr_table(table)
        table.to_csv(OUT / f"data_csv/table10_{scenario}.csv", index=False)
        cnr.to_csv(OUT / f"data_csv/cnr_{scenario}.csv", index=False)
        summarise(table, scenario)


if __name__ == "__main__":
    main()
