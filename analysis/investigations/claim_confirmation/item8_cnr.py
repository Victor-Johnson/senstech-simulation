#!/usr/bin/env python3
"""Item 8 -- does an average CNR of ~40 hide an important weak pair?

The handover reports "CNR = 40.3 / 40.2 / ... / 27.7" per detector and states
that no chip can distinguish pure copper from copper-nickel 90/10, calling that
"a limit set by the alloys' near-identical physical properties, not by detector
choice."

Two things to test: (a) what the average conceals, and (b) whether "cannot
distinguish" is a physical limit or an exposure limit.

The CNR definition in phase2_selection_experiment.cnr_table() is
    CNR = |N1 - N2| / sqrt(N1 + N2)
applied to the N0-SCALED counts. Since N1, N2 are both proportional to N0,
    CNR = sqrt(N0) * |f1 - f2| / sqrt(f1 + f2)
so CNR scales as sqrt(N0) exactly. Every quoted CNR is therefore conditional on
the arbitrary 10^6-photon budget, which is a free parameter of the analysis, not
a property of the detectors or the alloys.

Run: PYTHONPATH=. ./venv/bin/python analysis/investigations/claim_confirmation/item8_cnr.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

OUT = Path(__file__).resolve().parent
DATA = OUT / "data"
CSV = REPO_ROOT / "analysis/results/phase2_selection_framework/data_csv"
N0_PUBLISHED = 1_000_000
DETECTION_BAR = 5.0  # the conventional "clearly detectable" CNR

ALLOY_NAME = {
    "alloy1": "C11000 Cu", "alloy2": "C36000 brass",
    "alloy3": "C70600 CuNi 90/10", "alloy4": "C95500 Al bronze",
    "alloy5": "C17200 BeCu",
}


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    cnr = pd.read_csv(CSV / "cnr_native.csv")
    t10 = pd.read_csv(CSV / "table10_native.csv")

    # Attach the counts that went into each CNR, as the checklist requires.
    counts = t10.set_index(["detector", "alloy"]).N_sim
    def pair_counts(row):
        a1, a2 = row.pair.split("-")
        return pd.Series({"N_sim_a": counts.get((row.detector, a1), np.nan),
                          "N_sim_b": counts.get((row.detector, a2), np.nan)})
    cnr = pd.concat([cnr, cnr.apply(pair_counts, axis=1)], axis=1)
    cnr["pair_name"] = cnr.pair.map(
        lambda p: " vs ".join(ALLOY_NAME.get(x, x) for x in p.split("-")))
    cnr["N0_for_detection_bar"] = N0_PUBLISHED * (DETECTION_BAR / cnr.CNR_sim) ** 2
    cnr.to_csv(DATA / "item8_cnr_all_pairs.csv", index=False)

    print("=" * 78)
    print("ITEM 8 -- average CNR vs worst-pair CNR")
    print("=" * 78)
    print()
    summ = cnr.groupby("detector").CNR_sim.agg(["mean", "min", "max"])
    summ["worst_pair"] = cnr.loc[cnr.groupby("detector").CNR_sim.idxmin()] \
                            .set_index("detector").pair_name
    summ["spread_factor"] = summ["max"] / summ["min"]
    summ = summ.sort_values("mean", ascending=False)
    print(f"{'detector':16s} {'mean':>7s} {'min':>7s} {'max':>7s} {'max/min':>8s}  worst pair")
    for d, r in summ.iterrows():
        print(f"{d:16s} {r['mean']:7.2f} {r['min']:7.2f} {r['max']:7.2f} "
              f"{r.spread_factor:8.1f}  {r.worst_pair}")
    summ.to_csv(DATA / "item8_cnr_summary.csv")

    print()
    print(f"  -> the reported average conceals a spread of up to "
          f"{summ.spread_factor.max():.0f}x within a single detector.")
    print(f"  -> the worst pair is the SAME for every detector: "
          f"{summ.worst_pair.iloc[0]}")

    print()
    print("-" * 78)
    print(f"Is 'cannot distinguish' physical, or just this photon budget?")
    print("-" * 78)
    hard = cnr[cnr.pair == "alloy1-alloy3"].sort_values("CNR_sim")
    print(f"  Cu vs CuNi 90/10, at the published N0 = {N0_PUBLISHED:,}:")
    print(f"{'detector':16s} {'CNR':>7s} {'N_sim(Cu)':>11s} {'N_sim(CuNi)':>12s} "
          f"{'N0 for CNR=5':>14s} {'x more':>8s}")
    for _, r in hard.iterrows():
        print(f"{r.detector:16s} {r.CNR_sim:7.2f} {r.N_sim_a:11.0f} {r.N_sim_b:12.0f} "
              f"{r.N0_for_detection_bar:14.3e} {r.N0_for_detection_bar / N0_PUBLISHED:7.0f}x")

    print()
    print(f"  CNR scales as sqrt(N0) exactly, so reaching the CNR={DETECTION_BAR:g} "
          f"detectability bar needs")
    print(f"  {hard.N0_for_detection_bar.min() / N0_PUBLISHED:.0f}-"
          f"{hard.N0_for_detection_bar.max() / N0_PUBLISHED:.0f}x more photons "
          f"({hard.N0_for_detection_bar.min():.2e} to "
          f"{hard.N0_for_detection_bar.max():.2e}).")
    print("  That is an EXPOSURE limit, not a physical one.")

    print()
    print("-" * 78)
    print("What the decision rule actually is (and isn't)")
    print("-" * 78)
    print("  CNR = |N1-N2| / sqrt(N1+N2), Poisson shot noise on N0-scaled counts.")
    print("  NOT modelled anywhere: electronic noise, background, dark counts,")
    print("  exposure time, number of repeated measurements, or any stated CNR")
    print("  cutoff for 'reliably distinguish'. The quoted values are therefore an")
    print("  optimistic upper bound at one arbitrary photon budget.")
    print()
    print(f"Wrote {DATA}/item8_cnr_all_pairs.csv, item8_cnr_summary.csv")


if __name__ == "__main__":
    main()
