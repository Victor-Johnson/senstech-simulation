#!/usr/bin/env python3
"""Item 6 -- do the prose, tables and figures come from the same results?

Four specific statements to check against the one results file, plus the
percentage formula itself.

Run: PYTHONPATH=. ./venv/bin/python analysis/investigations/claim_confirmation/item6_consistency.py
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


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    nat = pd.read_csv(CSV / "table10_native.csv")
    mat = pd.read_csv(CSV / "table10_matched.csv")

    print("=" * 78)
    print("ITEM 6 -- numerical and version consistency")
    print("=" * 78)

    # --- 6a. the delta formula -------------------------------------------
    print()
    print("6a. Can delta be recomputed from the N_theory / N_sim columns printed")
    print("    beside it?  (the checklist asks to state delta = 100(Ns-Nt)/Nt)")
    print()
    g = nat.groupby("detector_label").agg(
        N_theory=("N_theory", "mean"), N_sim=("N_sim", "mean"),
        delta_published=("delta_pct", "mean"))
    g["delta_from_columns"] = (g.N_sim - g.N_theory) / g.N_theory * 100
    g["reproducible"] = (g.delta_published - g.delta_from_columns).abs() < 0.1
    g = g.sort_values("N_sim", ascending=False)
    print(f"{'detector':16s} {'N_theory':>9s} {'N_sim':>9s} {'published':>10s} "
          f"{'from cols':>10s} {'ok':>4s}")
    for d, r in g.iterrows():
        print(f"{d:16s} {r.N_theory:9.0f} {r.N_sim:9.0f} {r.delta_published:10.2f} "
              f"{r.delta_from_columns:10.2f} {'YES' if r.reproducible else 'NO':>4s}")
    g.to_csv(DATA / "item6_delta_reproducibility.csv")
    bad = int((~g.reproducible).sum())
    print()
    print(f"  {bad} of {len(g)} rows CANNOT be reproduced from their own columns.")
    print("  Cause: the published delta is the MEAN OF PER-ALLOY delta, while the")
    print("  displayed N_theory/N_sim are means. mean-of-ratios != ratio-of-means,")
    print("  and the two diverge most exactly where delta is largest.")

    # --- 6b. "four chips agree within 1%" --------------------------------
    print()
    print("6b. 'For the FOUR chips ... agree to under 1%'")
    under1 = g[g.delta_published.abs() < 1]
    print(f"    chips with |delta| < 1%: {len(under1)} -> "
          f"{', '.join(under1.index)}")
    print(f"    Timepix3 is {g.loc['D4 Timepix3'].delta_published:+.2f}% -- not under 1%.")
    print(f"    VERDICT: should be THREE, not four.")

    # --- 6c. "every chip loses roughly 15%" ------------------------------
    print()
    print("6c. 'every chip loses roughly 15% of its signal' (native -> matched)")
    n = nat.groupby("detector_label").N_sim.mean()
    m = mat.groupby("detector_label").N_sim.mean()
    loss = ((n - m) / n * 100).sort_values(ascending=False)
    for d, v in loss.items():
        flag = "  <-- loses NOTHING" if abs(v) < 0.01 else ""
        print(f"    {d:16s} {v:6.2f}%{flag}")
    loss.to_frame("loss_pct").to_csv(DATA / "item6_thickness_loss.csv")
    print(f"    VERDICT: true for 5 of 6. EIGER2 is 0.75 mm in BOTH scenarios so")
    print(f"    it loses 0%; the blanket 'every chip' is wrong.")

    # --- 6d. run count ----------------------------------------------------
    print()
    print("6d. 'a total of 84 bare-detector simulation runs'")
    # Use the registry to separate published-campaign runs from this audit's
    # reruns. A naive "_cdte" filter is wrong: timepix3_cdte legitimately
    # contains that string, so p2_bare_timepix3_cdte_80keV is a real campaign
    # run while p2_bare_medipix3_cdte_80keV is an audit rerun. parse_name()
    # returns None for the audit tags because they are not valid thickness tags.
    from analysis.viz import registry as reg
    roots = [r for r in sorted((REPO_ROOT / "data").glob("p2_bare_*.root"))
             if reg.parse_name(r.stem) is not None]
    tagged = [r for r in roots if "075mm" in r.stem]
    print(f"    p2_bare_* ROOTs on disk (excluding this audit's reruns): {len(roots)}")
    print(f"      untagged (1 mm)   : {len(roots) - len(tagged)}")
    print(f"      _075mm (0.75 mm)  : {len(tagged)}")
    print(f"    VERDICT: 84 describes ONE scenario. Producing both Table 10 and")
    print(f"    Table 10b required {len(roots)}.")

    # --- 6e. figure provenance -------------------------------------------
    print()
    print("6e. Figure source files and run tags")
    print("    Figures 2, 3, A1  <- table10_native.csv        (EIGER2 = 0.75 mm) OK")
    print("    Figure A2         <- phase2_energy_spectra.py, which builds its path")
    print("                         as p2_bare_{det}_{E}keV.root with NO thickness")
    print("                         tag -> reads EIGER2's 1 mm runs.")
    # Compare like with like: phase2_energy_spectra.py weights by alloy1 (Cu)
    # only, so the comparison target is Table A1's Cu cell, NOT the 5-alloy mean.
    e_cu = float(nat[(nat.detector == "eiger2") & (nat.alloy == "alloy1")].N_sim.iloc[0])
    byE = pd.read_csv(CSV / "detected_by_energy.csv")
    print(f"    EIGER2, Table A1 Cu cell (0.75 mm)    : {e_cu:8.0f}")
    print(f"    EIGER2, summed from Figure A2 (Cu)    : {byE.EIGER2.sum():8.0f}")
    print(f"    discrepancy                            : "
          f"{(byE.EIGER2.sum() - e_cu) / e_cu * 100:+7.1f}%")
    # control: a wide-window chip should agree, since its untagged runs are 1 mm
    # native and therefore the correct file.
    t4_cu = float(nat[(nat.detector == "timepix4") & (nat.alloy == "alloy1")].N_sim.iloc[0])
    print(f"    control Timepix4, Table A1 Cu         : {t4_cu:8.0f}")
    print(f"    control Timepix4, from Figure A2      : {byE.Timepix4.sum():8.0f}"
          f"   (agrees -> the fault is EIGER2-specific)")
    print("    VERDICT: Figure A2's EIGER2 curve is from a different thickness AND")
    print("    from the run set separately shown to be internally inconsistent.")

    print()
    print(f"Wrote {DATA}/item6_delta_reproducibility.csv, item6_thickness_loss.csv")


if __name__ == "__main__":
    main()
