"""Exp 0 data check (PH-14 ruling b): Geant4 Livermore mu/rho vs NIST XCOM, tolerance on mu/rho.

Inputs:  data/protocol_runs/g4mu/mu_<mat>.csv   (stagea_spike mu mode; QGSP_BERT_LIV)
         analysis/protocol/reference/xcom/<mat>.csv (NIST XCOM, fetched by xcom.py)
Outputs: analysis/protocol/exp0/data_check_mu.csv  (per material x energy, total + per process)
         analysis/protocol/exp0/data_check_summary.csv
         analysis/protocol/exp0/thick_part_T_band.csv  (transmission uncertainty band from the mu/rho difference)
Tolerance: |mu_G4/mu_XCOM - 1| <= 2% (total with coherent). Points within +-1 keV of an absorption edge are
reported separately (edge placement on a 1 keV grid, not a data disagreement).
"""
from pathlib import Path
import numpy as np, pandas as pd
R = Path(__file__).resolve().parents[2]
OUT = R / "analysis/protocol/exp0"; OUT.mkdir(parents=True, exist_ok=True)
TOL = 0.02
EDGES_KEV = {"Pb": 88.005, "Sn": 29.200, "Cd": 26.711, "Te": 31.814, "Cs": 35.985, "I": 33.169, "Gd": 50.239, "W": 69.525}
MAT_EDGES = {"CuZn39Pb3": ["Pb"], "CuSn8": ["Sn"], "CdTe": ["Cd", "Te"], "CsI": ["Cs", "I"], "GOS": ["Gd"], "W": ["W"]}
DENS = {"Cu": 8.96, "CuZn37": 8.44, "CuZn39Pb3": 8.47, "CuSn8": 8.80, "CuNi10Fe1Mn": 8.90}
rows = []
for m in ["Cu", "CuZn37", "CuZn39Pb3", "CuSn8", "CuNi10Fe1Mn", "CdTe", "CsI", "GOS", "W"]:
    g = pd.read_csv(R / f"data/protocol_runs/g4mu/mu_{m}.csv")
    x = pd.read_csv(R / f"analysis/protocol/reference/xcom/{m}.csv", keep_default_na=False)
    x = x[x.edge == ""].set_index("energy_keV")
    for _, r in g.iterrows():
        E = float(r.energy_keV); xr = x.loc[E]
        near = any(abs(E - EDGES_KEV[e]) <= 1.0 for e in MAT_EDGES.get(m, []))
        rows.append(dict(material=m, energy_keV=E, near_edge=near,
                         mu_g4=r.total_with_coherent, mu_xcom=xr.total_with_coherent,
                         rel_total=r.total_with_coherent / xr.total_with_coherent - 1,
                         rel_photo=r.photoelectric / xr.photoelectric - 1 if xr.photoelectric > 0 else np.nan,
                         rel_incoh=r.incoherent / xr.incoherent - 1, rel_coh=r.coherent / xr.coherent - 1))
d = pd.DataFrame(rows); d.to_csv(OUT / "data_check_mu.csv", index=False)
s = (d[~d.near_edge].assign(a=lambda t: t.rel_total.abs())
     .groupby("material").agg(n=("a", "size"), median_abs=("a", "median"), max_abs=("a", "max"),
                              E_at_max=("a", lambda t: d.loc[t.idxmax(), "energy_keV"]),
                              n_fail=("a", lambda t: int((t > TOL).sum()))))
s["pass"] = s.n_fail == 0
s.to_csv(OUT / "data_check_summary.csv")
pd.set_option("display.width", 200)
print("Data check, Geant4 QGSP_BERT_LIV vs XCOM, total mu/rho with coherent, tolerance 2% (edge +-1 keV excluded):")
print(s.round(4).to_string())
print("\nnear-edge points:", d.near_edge.sum(), "max |rel|", d[d.near_edge].rel_total.abs().max().round(3))
print("\nper-process median |rel| (non-edge): photo %.4f  incoh %.4f  coh %.4f" % tuple(
    d[~d.near_edge][c].abs().median() for c in ("rel_photo", "rel_incoh", "rel_coh")))
# transmission band for alloys (mu from XCOM vs G4), thicknesses 1-20 mm
b = []
for m, rho in DENS.items():
    t = d[d.material == m]
    for mm in (1, 2, 5, 10, 20):
        for _, r in t.iterrows():
            Tx, Tg = np.exp(-r.mu_xcom * rho * mm / 10), np.exp(-r.mu_g4 * rho * mm / 10)
            b.append(dict(material=m, thickness_mm=mm, energy_keV=r.energy_keV, T_xcom=Tx, T_g4=Tg,
                          rel_T=Tg / Tx - 1 if Tx > 0 else np.nan, mu_t=r.mu_xcom * rho * mm / 10))
b = pd.DataFrame(b); b.to_csv(OUT / "thick_part_T_band.csv", index=False)
q = b[(b.T_xcom > 1e-4)].assign(a=lambda t: t.rel_T.abs()).groupby("thickness_mm").a.agg(["median", "max"])
print("\nTransmission band |T_G4/T_XCOM - 1| over alloys and 20-300 keV with T>1e-4, by thickness:")
print(q.round(4).to_string())
