"""First milestone (LINDA, Medipix3, VAREX; CdTe 1 mm; reduced statistics 20k photons/energy).

Scoring: flat GPS beam; only photons entering the central fiducial square (stageb.Detector.fid_npix) are
counted, and they are the denominator (incident photons, including non-interacting ones).

Part A -- Exp 1 first look (Protocol Tbl 11/12 columns, ideal electronics: no noise, 5 keV threshold):
  detected_frac     events with total deposited charge >= 5 keV, per incident photon
  ceiling           1 - exp(-mu_tot rho t), XCOM CdTe, rho 5.85 g/cm3, t 0.1 cm  (pass rule: detected <= ceiling)
  full_energy_frac  events with total deposit within +-2 keV of E (charge summed over ALL pixels = ideal summing)
  spm_peak_frac     events with a SINGLE pixel within +-2 keV of E (counting without summing)
  multi_pixel_frac  among detected events, fraction with >1 pixel above 5 keV
  counts_per_photon_spm  pixel signals above 5 keV per incident photon (>1 = double counting)
Part B -- review item 5 (L7, HIGH PRIORITY): LINDA at 225/300 kVp behind CuZn39Pb3 0/5/10/20 mm, above-range
  photons "lost" vs "clip" (into the top bin). Folding: spectrum weight (1 keV SpekPy, 1 mm Cu) x XCOM
  transmission, summed into the 10 keV Stage-B grid (each grid energy represents [E-5, E+5) keV; tag A,
  reduced-statistics milestone). Spectrum below 10 keV and above 300 keV is ignored (negligible after 1 mm Cu).
  Electronics: thresholds 20/49.8/79.7/109.5/139.3/169.2 keV (A1 uniform split, tag A), saturation 45 ke-
  (D-L23, ~199 keV), noise 90 e- (D-L22, P), summing 3x3 efficiency 1.0 (R-01 baseline, tag A).
Outputs: analysis/protocol/exp1/milestone1_response.csv, analysis/protocol/exp2/linda_above_range_bins.csv
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

from analysis.protocol.stageb import load_fiducial, DETECTORS, run_name
from analysis.protocol.electronics import Electronics, bin_counts, W_EV

R = Path(__file__).resolve().parents[2]
E_GRID = list(range(10, 301, 10))
RHO_CDTE, T_CM = 5.85, 0.1
THR_KEV, TOL_KEV = 5.0, 2.0
LINDA_THR = [20.0, 49.8, 79.7, 109.5, 139.3, 169.2]
RHO_ALLOY = 8.47  # CuZn39Pb3, T-01 bracket
PROV_A = ("PROVISIONAL (tag A): bias -500 V (D-L26), Medipix3 1 mm CdTe (D-M05), VAREX 1 mm (D-V13), "
          "CdTe transport S-in-progress (PH-01..04), Fano 0.24 (PH-06 conflict); reduced statistics 20k/energy")
PROV_B = (PROV_A + "; alloy grade CuZn39Pb3 bracket (T-01); LINDA thresholds A1 uniform split; saturation 45 ke- "
          "and above-range behaviour (D-L23/D-L24 MISSING, both scenarios); summing 3x3 eff 1.0 (R-04); "
          "spectra tube params (T-09); 10 keV folding grid")


def pix_df(d):
    return pd.DataFrame(dict(event=d["pix_event"], px=d["pix_x"], py=d["pix_y"], charge_e=d["pix_charge_e"]))


def response_row(det: str, E: int, mu_cdte: pd.Series) -> dict:
    pix, n, _ = load_fiducial("milestone1", run_name("milestone1", det, float(E)), DETECTORS[det])
    pix = pix.copy()
    pix["keV"] = pix.charge_e * W_EV / 1e3
    tot = pix.groupby("event").keV.sum()
    above = pix[pix.keV >= THR_KEV]
    npx = above.groupby("event").size()
    det_ev = tot[tot >= THR_KEV]
    return dict(detector=det, energy_keV=E, n_events=n,
                detected_frac=len(det_ev) / n,
                ceiling=1 - np.exp(-mu_cdte.loc[float(E)] * RHO_CDTE * T_CM),
                full_energy_frac=float((np.abs(tot - E) <= TOL_KEV).sum()) / n,
                spm_peak_frac=float((np.abs(pix.keV - E) <= TOL_KEV).groupby(pix.event).any().sum()) / n,
                multi_pixel_frac=float((npx.reindex(det_ev.index, fill_value=0) > 1).mean()) if len(det_ev) else np.nan,
                counts_per_photon_spm=len(above) / n)


def part_a() -> pd.DataFrame:
    x = pd.read_csv(R / "analysis/protocol/reference/xcom/CdTe.csv", keep_default_na=False)
    mu = x[x.edge == ""].set_index("energy_keV").total_with_coherent
    df = pd.DataFrame([response_row(det, E, mu) for det in ("linda", "medipix3", "varex") for E in E_GRID])
    df["sigma_binom"] = np.sqrt(df.detected_frac * (1 - df.detected_frac) / df.n_events)
    df["pass_ceiling"] = df.detected_frac <= df.ceiling + 3 * df.sigma_binom
    df["provisional"] = PROV_A
    out = R / "analysis/protocol/exp1"; out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "milestone1_response.csv", index=False)
    return df


def part_b() -> pd.DataFrame:
    x = pd.read_csv(R / "analysis/protocol/reference/xcom/CuZn39Pb3.csv", keep_default_na=False)
    mu = x[x.edge == ""].set_index("energy_keV").total_with_coherent
    base = dict(thresholds_keV=LINDA_THR, sigma_noise_e=90, summing="nxn", neighbourhood=3,
                summing_efficiency=1.0, saturation_e=45000)
    npix = DETECTORS["linda"].sim_array
    resp = {}
    for E in E_GRID:
        pix, n, _ = load_fiducial("milestone1", run_name("milestone1", "linda", float(E)), DETECTORS["linda"])
        resp[E] = {s: bin_counts(pix, n, Electronics(above_range=s, **base), npix) for s in ("lost", "clip")}
    rows = []
    for kvp in (225, 300):
        sp = pd.read_csv(R / f"simulation/stageA_g4/spectra/spek_{kvp}kVp_1mmCu.csv")
        sp = sp[(sp.energy_keV >= 5) & (sp.energy_keV < 305)]
        for t in (0, 5, 10, 20):
            w = sp.weight.to_numpy() * np.exp(-mu.reindex(sp.energy_keV.astype(float)).to_numpy() * RHO_ALLOY * t / 10)
            w = w / w.sum()
            grid = np.clip(np.rint(sp.energy_keV.to_numpy() / 10) * 10, 10, 300).astype(int)
            wk = pd.Series(w).groupby(grid).sum()
            inc_above = float(w[sp.energy_keV.to_numpy() > 199].sum())
            for s in ("lost", "clip"):
                c = sum(wk[E] * resp[E][s]["counts_per_photon"] for E in wk.index)
                a = sum(wk[E] * resp[E][s]["above_range_per_photon"] for E in wk.index)
                row = dict(kvp=kvp, alloy="CuZn39Pb3", thickness_mm=t, scenario=s,
                           incident_frac_above_199keV=inc_above, saturating_signals_per_photon=a,
                           counts_per_photon=c.sum())
                row.update({f"bin{i+1}_{lo:g}keV": v for i, (lo, v) in enumerate(zip(LINDA_THR, c))})
                row["top_bin_share"] = c[-1] / c.sum()
                rows.append(row)
    df = pd.DataFrame(rows)
    df["provisional"] = PROV_B
    out = R / "analysis/protocol/exp2"; out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "linda_above_range_bins.csv", index=False)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    a = part_a()
    print(a.drop(columns=["n_events", "sigma_binom"]).round(3).to_string(index=False))
    b = part_b()
    print(b.round(4).to_string(index=False))
