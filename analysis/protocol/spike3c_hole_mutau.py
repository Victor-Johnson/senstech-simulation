"""Review item 3: does hole trapping matter at the pessimistic hole mu-tau (1e-5 cm2/V, tau_h = 91 ns)?
Compares, at 1000 events each: simple model (electrons only), induced-charge model at baseline
mu-tau_h = 1.8e-4 (spike3 runs), induced-charge model at mu-tau_h = 1e-5 (spike3c runs).
Output: analysis/protocol/spike3c_hole_mutau.csv"""
from pathlib import Path
import numpy as np, pandas as pd
from analysis.protocol.textwriter import read_pixel_charge
R = Path(__file__).resolve().parents[2]
SRC = {"simple": R / "data/protocol_spikes/spike3_simple_{T}um_{E}keV_n1000_cps100.txt",
       "transient_mutau1.8e-4": R / "data/protocol_spikes/spike3_transient_{T}um_{E}keV_n1000_cps100.txt",
       "transient_mutau1e-5": R / "data/protocol_runs/spike3/spike3_transient_{T}um_{E}keV_n1000_cps100_muth1e-5.txt"}
rows = []
for T in (1000, 2000):
    for E in (60, 150):
        for model, pat in SRC.items():
            f = Path(str(pat).format(T=T, E=E))
            if not f.exists():
                continue
            df, n = read_pixel_charge(f)
            Ep = df.charge_e * 4.43e-3
            ev = df[Ep > 5].assign(E=Ep[Ep > 5]).groupby("event").E.sum()
            peak = ev[np.abs(ev - E) < 0.1 * E]
            rows.append(dict(thickness_mm=T / 1000, E_keV=E, model=model, n_events=n,
                             detected_frac=len(ev) / n,
                             fep_frac=float((np.abs(ev - E) < 0.05 * E).sum()) / n,
                             tail_frac=float(((ev < 0.95 * E) & (ev > 0.5 * E)).sum()) / n,
                             peak_pos_keV=float(peak.median()) if len(peak) else np.nan,
                             mean_collected_over_E=float(ev.mean() / E)))
d = pd.DataFrame(rows); d.to_csv(R / "analysis/protocol/spike3c_hole_mutau.csv", index=False)
pd.set_option("display.width", 200); print(d.round(3).to_string(index=False))
