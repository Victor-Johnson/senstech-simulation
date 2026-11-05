"""Feasibility test 5: SpekPy tube spectra at 80/150/225/300 kVp and attenuation cross-check.

Run: PYTHONPATH=. ./venv/bin/python analysis/protocol/spike5_spectra_and_attenuation.py

Outputs (analysis/protocol/spike5/):
  spectra_1keV.csv              photons/keV/mAs at 1 m for each kVp x prefilter (SpekPy)
  spectra_summary.csv           mean energy, fraction above 199 keV (LINDA range), fluence per mAs
  alloy_mu_comparison.csv       mu/rho from SpekPy-NIST (XCOM-based) vs xraydb (Elam), per alloy/energy
  alloy_transmission.csv        Beer-Lambert T for 1/2/5/10/20 mm from both sources + relative difference

Every input here is tagged in inputs_register.csv:
  tube: W anode, 1 mm Be + 2 mm Al inherent (T-09, tag A), anode angle 12 deg (tag A; not in protocol)
  prefilter 0 / 1 / 2 mm Cu (T-10)
  alloys: CuZn37, CuZn39Pb3, CuSn8, CuNi10Fe1Mn (T-01 bracket, tag A) + pure Cu
NOTE: this compares two tabulations. The protocol's Exp-0 check (Geant4 primary-only transport vs XCOM)
needs the standalone Geant4 app (test 4) and is NOT done here.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import spekpy as sp
import xraydb
from spekpy.DataTables import MuData

OUT = Path(__file__).resolve().parent / "spike5"
OUT.mkdir(exist_ok=True)

KVPS = (80, 150, 225, 300)
PREFILTERS_MM_CU = (0.0, 1.0, 2.0)
ANODE_ANGLE_DEG = 12.0  # tag A
INHERENT = (("Be", 1.0), ("Al", 2.0))  # T-09, tag A
LINDA_TOP_KEV = 199.0  # D-L23 derived

# Placeholder grades (T-01, tag A): nominal mass fractions and densities (g/cm3)
ALLOYS = {
    "Cu (pure)":   ({"Cu": 1.0}, 8.96),
    "CuZn37":      ({"Cu": 0.63, "Zn": 0.37}, 8.44),
    "CuZn39Pb3":   ({"Cu": 0.58, "Zn": 0.39, "Pb": 0.03}, 8.47),
    "CuSn8":       ({"Cu": 0.918, "Sn": 0.08, "P": 0.002}, 8.80),
    "CuNi10Fe1Mn": ({"Cu": 0.875, "Ni": 0.10, "Fe": 0.015, "Mn": 0.01}, 8.90),
}
Z = {"Cu": 29, "Zn": 30, "Pb": 82, "Sn": 50, "P": 15, "Ni": 28, "Fe": 26, "Mn": 25}
THICK_MM = (1, 2, 5, 10, 20)
ENERGIES = np.arange(20.0, 301.0, 1.0)


def spectra():
    rows, summ = [], []
    for kvp in KVPS:
        for cu in PREFILTERS_MM_CU:
            s = sp.Spek(kvp=kvp, th=ANODE_ANGLE_DEG)
            for m, t in INHERENT:
                s.filter(m, t)
            if cu > 0:
                s.filter("Cu", cu)
            k, phi = s.get_spectrum(edges=False)  # photons/keV/cm2/mAs at 1 m (SpekPy default)
            # rebin to 1 keV
            e = np.arange(1, kvp + 1)
            w = np.array([np.trapezoid(phi[(k >= a - 0.5) & (k < a + 0.5)], k[(k >= a - 0.5) & (k < a + 0.5)])
                          if ((k >= a - 0.5) & (k < a + 0.5)).sum() > 1 else 0.0 for a in e])
            for a, v in zip(e, w):
                rows.append((kvp, cu, a, v))
            flu = w.sum()
            summ.append(dict(kvp=kvp, prefilter_mm_cu=cu, fluence_per_mAs_cm2_1m=flu,
                             mean_keV=(e * w).sum() / flu,
                             frac_above_199keV=w[e > LINDA_TOP_KEV].sum() / flu,
                             spekpy_mean_keV=s.get_emean()))
    pd.DataFrame(rows, columns=["kvp", "prefilter_mm_cu", "energy_keV", "photons_per_keV_cm2_mAs_1m"]).to_csv(
        OUT / "spectra_1keV.csv", index=False)
    df = pd.DataFrame(summ)
    df.to_csv(OUT / "spectra_summary.csv", index=False)
    return df


def attenuation():
    nist = MuData("nist_mu.dat")
    mu_rows, t_rows = [], []
    for name, (comp, rho) in ALLOYS.items():
        mr_nist = sum(f * np.asarray(nist.get_mu_over_rho(Z[el], ENERGIES), float) for el, f in comp.items())
        mr_elam = sum(f * np.asarray(xraydb.mu_elam(el, ENERGIES * 1e3, kind="total"), float) for el, f in comp.items())
        for E, a, b in zip(ENERGIES, mr_nist, mr_elam):
            mu_rows.append(dict(alloy=name, energy_keV=E, mu_rho_nist=a, mu_rho_elam=b, rel_diff=(b - a) / a))
            for t in THICK_MM:
                ta, tb = np.exp(-a * rho * t / 10), np.exp(-b * rho * t / 10)
                t_rows.append(dict(alloy=name, thickness_mm=t, energy_keV=E, T_nist=ta, T_elam=tb,
                                   rel_diff=(tb - ta) / ta if ta > 0 else np.nan))
    mu, tr = pd.DataFrame(mu_rows), pd.DataFrame(t_rows)
    mu.to_csv(OUT / "alloy_mu_comparison.csv", index=False)
    tr.to_csv(OUT / "alloy_transmission.csv", index=False)
    return mu, tr


if __name__ == "__main__":
    import time
    t0 = time.time()
    s = spectra()
    t1 = time.time()
    mu, tr = attenuation()
    t2 = time.time()
    pd.set_option("display.width", 200)
    print(f"spectra: {t1 - t0:.1f} s; attenuation: {t2 - t1:.1f} s")
    print(s.round(4).to_string(index=False))
    print("\nmu/rho  |rel diff| xraydb(Elam) vs SpekPy-NIST, by alloy (max / at 88 keV Pb edge region):")
    g = mu.assign(a=mu.rel_diff.abs())
    print(g.groupby("alloy").a.agg(["median", "max"]).round(4).to_string())
    print("\nworst energies:")
    print(g.sort_values("a", ascending=False).head(6)[["alloy", "energy_keV", "mu_rho_nist", "mu_rho_elam", "rel_diff"]].round(4).to_string(index=False))
    sel = tr[(tr.T_nist > 1e-4)]
    bad = sel[sel.rel_diff.abs() > 0.02]
    print(f"\nBeer-Lambert transmission cells with T>1e-4: {len(sel)}; cells differing >2% between sources: {len(bad)}")
    if len(bad):
        print(bad.assign(a=bad.rel_diff.abs()).sort_values("a", ascending=False).head(8).round(5).to_string(index=False))
