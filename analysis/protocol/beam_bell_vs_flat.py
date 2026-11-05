"""Item 2 re-check: did the bell-shaped "rectangle" beam bias the milestone-1 / Am-241 responses?

old: data/protocol_runs/stageB/<campaign>_bellbeam  (beam_shape rectangle -> bell, sigma ~ beam_size/2;
     all events, normalised by n_events; LINDA on its real 8 x 20 array)
new: data/protocol_runs/stageB/<campaign>           (flat GPS beam, fiducial scoring)
Same metric definitions as milestone1.response_row. Output: analysis/protocol/audit/beam_bell_vs_flat.csv
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

from analysis.protocol.stageb import DATA_DIR, DETECTORS, load_fiducial, run_name
from analysis.protocol.electronics import W_EV

R = Path(__file__).resolve().parents[2]
THR, TOL = 5.0, 2.0


def metrics(pix: pd.DataFrame, n: int, E: float) -> dict:
    kev = pix.charge_e * W_EV / 1e3
    tot = kev.groupby(pix.event).sum()
    npx = (kev >= THR).groupby(pix.event).sum()
    det = tot[tot >= THR]
    return dict(detected=len(det) / n, full_energy=float((np.abs(tot - E) <= TOL).sum()) / n,
                multi_pixel=float((npx.reindex(det.index, fill_value=0) > 1).mean()),
                spm_peak=float((np.abs(kev - E) <= TOL).groupby(pix.event).any().sum()) / n)


def old(campaign, det, E):
    z = np.load(DATA_DIR / f"{campaign}_bellbeam" / f"{run_name(campaign, det, E)}.npz")
    pix = pd.DataFrame(dict(event=z["pix_event"], px=z["pix_x"], py=z["pix_y"], charge_e=z["pix_charge_e"]))
    return pix, json.loads(str(z["meta"]))["n_events"]


def run() -> pd.DataFrame:
    rows = []
    for det in ("linda", "medipix3", "varex"):
        for E in (10.0, 30.0, 60.0, 100.0, 150.0, 200.0, 300.0):
            if det == "linda":
                p = DATA_DIR / "milestone1_bellbeam/superseded_linda_8x20" / f"{run_name('milestone1', det, E)}.npz"
                z = np.load(p)
                po = pd.DataFrame(dict(event=z["pix_event"], px=z["pix_x"], py=z["pix_y"], charge_e=z["pix_charge_e"]))
                no = json.loads(str(z["meta"]))["n_events"]
            else:
                po, no = old("milestone1", det, E)
            pn, nn, _ = load_fiducial("milestone1", run_name("milestone1", det, E), DETECTORS[det])
            a, b = metrics(po, no, E), metrics(pn, nn, E)
            r = dict(campaign="milestone1", detector=det, energy_keV=E, n_old=no, n_new_fiducial=nn)
            for k in a:
                r[f"{k}_bell"], r[f"{k}_flat"] = a[k], b[k]
                se = np.sqrt(b[k] * (1 - b[k]) / nn + a[k] * (1 - a[k]) / no) if k != "multi_pixel" else np.nan
                r[f"{k}_diff"] = b[k] - a[k]
                if k != "multi_pixel":
                    r[f"{k}_pull"] = (b[k] - a[k]) / se if se > 0 else np.nan
            rows.append(r)
    df = pd.DataFrame(rows)
    (R / "analysis/protocol/audit").mkdir(parents=True, exist_ok=True)
    df.to_csv(R / "analysis/protocol/audit/beam_bell_vs_flat.csv", index=False)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    d = run()
    print(d[["detector", "energy_keV", "detected_bell", "detected_flat", "detected_pull", "full_energy_diff",
             "full_energy_pull", "multi_pixel_bell", "multi_pixel_flat", "spm_peak_diff", "spm_peak_pull"]].round(4).to_string(index=False))
