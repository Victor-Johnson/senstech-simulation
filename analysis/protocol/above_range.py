"""Review item 5: fraction of photons above LINDA's front-end range (~199 keV, D-L23) behind each alloy.

Spectrum: SpekPy 1 keV bins (spike5/spectra_1keV.csv; T-09 tube, tag A). Transmission: NIST XCOM total
with coherent (reference/xcom), narrow beam (unscattered primaries). Densities and grades: T-01 bracket, tag A.
This is the INCIDENT photon fraction; the fraction of DEPOSITED charge above 45 ke- (what saturates) comes from
the Stage-B response and is reported with the lost/clipped scenarios.
Output: analysis/protocol/exp2/above_range_fraction.csv
"""
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
OUT = R / "analysis/protocol/exp2"; OUT.mkdir(parents=True, exist_ok=True)
TOP_KEV = 199.0
DENS = {"Cu": 8.96, "CuZn37": 8.44, "CuZn39Pb3": 8.47, "CuSn8": 8.80, "CuNi10Fe1Mn": 8.90}
spec = pd.read_csv(R / "analysis/protocol/spike5/spectra_1keV.csv")
rows = []
for alloy, rho in DENS.items():
    x = pd.read_csv(R / f"analysis/protocol/reference/xcom/{alloy}.csv", keep_default_na=False)
    mu = x[x.edge == ""].set_index("energy_keV").total_with_coherent
    for (kvp, cu), s in spec[spec.kvp.isin([150, 225, 300])].groupby(["kvp", "prefilter_mm_cu"]):
        s = s[s.energy_keV >= 10]
        E = s.energy_keV.to_numpy(float); phi = s.photons_per_keV_cm2_mAs_1m.to_numpy()
        m = mu.reindex(E).to_numpy()
        for t in (0, 1, 2, 5, 10, 15, 20):
            T = np.exp(-m * rho * t / 10)
            n = phi * T
            rows.append(dict(kvp=kvp, prefilter_mm_cu=cu, alloy=alloy, thickness_mm=t,
                             transmitted_fluence_rel=n.sum() / phi.sum(),
                             frac_above_199keV=n[E > TOP_KEV].sum() / n.sum(),
                             mean_keV=(E * n).sum() / n.sum()))
d = pd.DataFrame(rows); d.to_csv(OUT / "above_range_fraction.csv", index=False)
pv = d[d.alloy == "CuZn39Pb3"].pivot_table(index=["kvp", "prefilter_mm_cu"], columns="thickness_mm", values="frac_above_199keV")
print("Fraction of transmitted photons above 199 keV, CuZn39Pb3 (rows kVp/prefilter mm Cu, cols thickness mm):")
print(pv.round(3).to_string())
print("\nSpread across the 5 grades at 300 kVp, 1 mm Cu (min-max):")
q = d[(d.kvp == 300) & (d.prefilter_mm_cu == 1.0)].groupby("thickness_mm").frac_above_199keV.agg(["min", "max"])
print(q.round(3).T.to_string())
