"""Material-penetration (uniform 1 mm) headline totals before/after the integration-time fix, with 95% CIs.

Inputs: two runs of analysis/scripts/material_penetration_experiment.py (identical code and arguments)
  before: original data/ ROOT files (integration_time 25 ns default) -- reproduces the committed results exactly
  after:  same, with the 206 valid 1 us audit re-runs overlaid (data/audit_itime/)
Uncertainty: Monte Carlo statistics of the simulated detector response only (binomial, per energy, from the
script's detected_bin_se). The five alloys reuse the SAME bare-detector runs, so their errors are fully
correlated within an energy: SE_total = sqrt( sum_E ( sum_alloy se[a, E] )^2 ). Different detectors are
independent runs -> the Medipix3 - Timepix3 difference adds in quadrature. 95% CI = +-1.96 SE.
Not included: Poisson noise of a real measurement (the totals are expected counts for N0 = 1e6 photons).
Output: analysis/protocol/audit/material_penetration_uniform_ranking_ci.csv
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

R = Path(__file__).resolve().parents[2]
Z = 1.96
REAL = ["medipix3", "timepix3_cdte", "eiger2"]


def totals(out_dir: Path) -> pd.DataFrame:
    p = pd.read_csv(out_dir / "per_energy_results.csv")
    p = p[p.detector.isin(REAL + ["hexitec_proxy"])]
    tot = p.groupby("detector").detected_bin.sum()
    se = p.groupby(["detector", "energy_keV"]).detected_bin_se.sum().pow(2).groupby("detector").sum().pow(0.5)
    return pd.DataFrame(dict(total=tot, se=se))


def run(before_dir: Path, after_dir: Path) -> pd.DataFrame:
    b, a = totals(before_dir), totals(after_dir)
    t = b.join(a, lsuffix="_before", rsuffix="_after")
    for s in ("before", "after"):
        t[f"ci95_{s}"] = Z * t[f"se_{s}"]
    t["rel_change"] = t.total_after / t.total_before - 1
    t = t.loc[REAL + ["hexitec_proxy"]]
    rows = []
    for s in ("before", "after"):
        d = t.loc["medipix3", f"total_{s}"] - t.loc["timepix3_cdte", f"total_{s}"]
        se = np.hypot(t.loc["medipix3", f"se_{s}"], t.loc["timepix3_cdte", f"se_{s}"])
        rows.append(dict(state=s, medipix3_minus_timepix3=d, ci95=Z * se, significant=abs(d) > Z * se))
    diff = pd.DataFrame(rows)
    out = R / "analysis/protocol/audit"
    t.to_csv(out / "material_penetration_uniform_ranking_ci.csv")
    diff.to_csv(out / "material_penetration_uniform_mpx3_vs_tpx3_ci.csv", index=False)
    return t, diff


if __name__ == "__main__":
    t, d = run(Path(sys.argv[1]), Path(sys.argv[2]))
    pd.set_option("display.width", 200)
    print(t.round(1).to_string()); print(d.round(1).to_string(index=False))
