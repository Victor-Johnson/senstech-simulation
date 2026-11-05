#!/usr/bin/env python3
"""Item 1 -- EIGER2's 80 keV "upper edge": which operating mode does it represent?

Finding that drives this: the 80 keV edge exists NOWHERE in the simulation. Across
all 551 generated configs the [DefaultDigitizer] block carries exactly three keys
(threshold, electronics_noise, threshold_smearing), all LOWER discriminators. The
80 keV cut is applied only in Python, at phase2_selection_experiment.py:100,
against collected cluster charge x 4.43 eV -- while the theory branch at :117 cuts
on incident spectrum bin energy.

EIGER2 hardware supports three distinct outputs (Donath 2023). All three are
recoverable from the SAME existing ROOT files with no re-simulation, because the
files retain every cluster and the window is only a mask:

    lower-threshold image  : clusters >= 4 keV        (counting mode)
    upper-threshold image  : clusters >= 80 keV
    difference image       : 4 keV <= clusters <= 80  <- what the study models

and lower - upper == difference exactly, by construction.

This script computes all three over the full 14-energy x 5-alloy grid and emits
them as separate labelled rows. It NEVER merges them into one "EIGER2" figure.

It does not modify phase2_selection_experiment.py: it imports it and varies the
detector via dataclasses.replace, so the delivered table10_*.csv are untouched.

Run: PYTHONPATH=. ./venv/bin/python analysis/investigations/claim_confirmation/item1_eiger2_modes.py
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import analysis.scripts.phase2_selection_experiment as p2  # noqa: E402

OUT = Path(__file__).resolve().parent
DATA = OUT / "data"

# Sentinel for "no upper cut". Deliberately finite, NOT np.inf: line 99 of
# phase2_selection_experiment builds np.linspace(lower, upper, bins+1), which
# produces nan interior edges when upper is inf. 1e6 keV is ~4500x the highest
# bin the cluster_charge histogram can hold (221.5 keV), so it is unreachable.
NO_UPPER_KEV = 1.0e6

# EIGER2 native commercial thickness.
THICK_MM = 0.75

MODES = {
    "difference_image": dict(
        lower=4.00, upper=80.0,
        label="Difference image (4-80 keV)",
        note="What the study currently models. Equals lower-threshold minus "
             "upper-threshold image.",
    ),
    "lower_threshold_image": dict(
        lower=4.00, upper=NO_UPPER_KEV,
        label="Lower-threshold image (>=4 keV)",
        note="Straight photon counting above the discriminator. The most likely "
             "mode for a penetration/counting application.",
    ),
    "upper_threshold_image": dict(
        lower=80.0, upper=NO_UPPER_KEV,
        label="Upper-threshold image (>=80 keV)",
        note="The high-energy half. Reported for completeness and to verify the "
             "lower - upper = difference identity.",
    ),
}


def build_for_mode(mode_key: str, weights, T, mu, manifest) -> pd.DataFrame:
    """Full 14-energy x 5-alloy computation for one EIGER2 operating mode.

    Mirrors phase2_selection_experiment.build_table() exactly, including the
    theory branch's incident-energy cut, so the two sides stay comparable.
    """
    spec = MODES[mode_key]
    base = next(d for d in p2.DETS if d.key == "eiger2")
    det = dataclasses.replace(base, lower_keV=spec["lower"], upper_keV=spec["upper"])

    rows = []
    for alloy, alloy_name in p2.ALLOYS.items():
        n_theory = n_sim = var_sim = 0.0
        for E in sorted(weights):
            wE, tE = weights[E], T[alloy][E]
            pE = p2.P_cdte(mu, E, THICK_MM)
            # Theory: hard step-window on INCIDENT photon energy.
            if det.lower_keV <= E <= det.upper_keV:
                n_theory += p2.N0 * wE * tE * pE
            events = p2.m.get_events(manifest, "bare", det.key, E, 10_000)
            # Simulation: window on DEPOSITED (cluster-charge) energy.
            r, r_se = p2.bare_windowed_response(det, THICK_MM, E, events)
            if np.isnan(r):
                continue
            n_sim += p2.N0 * wE * tE * r
            var_sim += (p2.N0 * wE * tE * r_se) ** 2
        rows.append({
            "mode": mode_key,
            "mode_label": spec["label"],
            "lower_keV": det.lower_keV,
            "upper_keV": det.upper_keV if det.upper_keV < NO_UPPER_KEV else np.inf,
            "alloy": alloy,
            "alloy_name": alloy_name,
            "thickness_mm": THICK_MM,
            "N_theory": n_theory,
            "N_sim": n_sim,
            "sigma_sim": float(np.sqrt(var_sim)),
            "delta_pct": (n_sim - n_theory) / n_theory * 100 if n_theory else np.nan,
        })
    return pd.DataFrame(rows)


def verify_identity(per_alloy: pd.DataFrame) -> pd.DataFrame:
    """lower-threshold - upper-threshold must equal the difference image."""
    piv = per_alloy.pivot_table(index="alloy", columns="mode", values="N_sim")
    piv["lower_minus_upper"] = piv.lower_threshold_image - piv.upper_threshold_image
    piv["identity_residual"] = piv.lower_minus_upper - piv.difference_image
    piv["identity_holds"] = piv.identity_residual.abs() < 1e-6
    return piv


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    weights, T, mu, manifest = p2.load_inputs()

    frames = [build_for_mode(k, weights, T, mu, manifest) for k in MODES]
    per_alloy = pd.concat(frames, ignore_index=True)
    per_alloy.to_csv(DATA / "item1_eiger2_modes_per_alloy.csv", index=False)

    print("=" * 76)
    print("ITEM 1 -- EIGER2 operating modes, all from existing ROOTs (no reruns)")
    print("=" * 76)
    print()

    summary = (per_alloy.groupby(["mode", "mode_label"])
               .agg(N_theory=("N_theory", "mean"), N_sim=("N_sim", "mean"),
                    sigma_sim=("sigma_sim", "mean"), delta_pct=("delta_pct", "mean"))
               .reset_index())
    order = ["difference_image", "lower_threshold_image", "upper_threshold_image"]
    summary["_o"] = summary["mode"].map({m: i for i, m in enumerate(order)})
    summary = summary.sort_values("_o").drop(columns="_o")
    summary.to_csv(DATA / "item1_eiger2_modes_summary.csv", index=False)

    print("Mean over the 5 alloys, EIGER2 at its native 0.75 mm:")
    print()
    print(f"{'mode':34s} {'N_theory':>10s} {'N_sim':>10s} {'delta %':>9s}")
    for _, r in summary.iterrows():
        print(f"{r.mode_label:34s} {r.N_theory:10.0f} {r.N_sim:10.0f} {r.delta_pct:9.1f}")

    base = summary[summary["mode"] == "difference_image"].iloc[0]
    low = summary[summary["mode"] == "lower_threshold_image"].iloc[0]
    print()
    print(f"  lower-threshold image is {low.N_sim / base.N_sim:.2f}x the difference image")
    print(f"  (published Table 10 native EIGER2 = 3,463 theory / 6,372 sim -- the "
          f"difference-image row)")

    print()
    print("-" * 76)
    print("Identity check: lower-threshold - upper-threshold == difference image")
    print("-" * 76)
    ident = verify_identity(per_alloy)
    print(ident.round(4).to_string())
    ident.to_csv(DATA / "item1_identity_check.csv")
    print()
    print(f"  identity holds for all alloys: {bool(ident.identity_holds.all())}")

    print()
    print("-" * 76)
    print("Where EIGER2 would rank, per mode, against the other five chips")
    print("-" * 76)
    t10 = pd.read_csv(REPO_ROOT / "analysis/results/phase2_selection_framework"
                      / "data_csv/table10_native.csv")
    others = (t10[t10.detector != "eiger2"]
              .groupby("detector_label").N_sim.mean().rename("N_sim"))
    for _, r in summary.iterrows():
        board = pd.concat([others,
                           pd.Series({f"EIGER2 [{r.mode_label}]": r.N_sim})])
        board = board.sort_values(ascending=False)
        pos = list(board.index).index(f"EIGER2 [{r.mode_label}]") + 1
        print(f"\n  {r.mode_label}  ->  rank {pos} of {len(board)}")
        for name, val in board.items():
            mark = "  <--" if name.startswith("EIGER2") else ""
            print(f"      {name:44s} {val:9.0f}{mark}")

    print()
    print(f"Wrote {DATA}/item1_eiger2_modes_per_alloy.csv, "
          f"item1_eiger2_modes_summary.csv, item1_identity_check.csv")


if __name__ == "__main__":
    main()
