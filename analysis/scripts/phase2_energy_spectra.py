#!/usr/bin/env python3
"""Phase 2 -- detected photons separated by beam energy.

Instead of one total per detector, show the detected count in each incident
energy bin: detected(d,E) = N0 * w(E) * T_Cu(E) * R_d(E), where R_d(E) is the
detector's windowed response (measured from the ROOTs). Reveals where each
chip's energy window cuts the transmitted beam, and HEXITEC's flat spectroscopic
reach vs the counters.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import analysis.scripts.material_penetration_experiment as m

ROOT = Path("/home/victor-pc/itek/senstech-simulation")
BASE = ROOT / "analysis/results/phase2_selection_framework"
DATA = ROOT / "data"
N0 = 1_000_000
EPS = m.EPSILON_CDTE_EV

w = pd.read_csv(ROOT / "spectra/150kvp_weights.csv")
weights = dict(zip(w.energy_keV.astype(float), w.weight))
att = pd.read_csv(ROOT / "analysis/results/material_penetration_uniform/alloy_attenuation.csv")
Tcu = att[att.alloy == "alloy1"].set_index("energy_keV").transmission.to_dict()

DETS = {"medipix3": ("Medipix3", 3.10, 110), "medipix4": ("Medipix4", 7.85, 150),
        "timepix3_cdte": ("Timepix3", 2.21, 120), "timepix4": ("Timepix4", 4.43, 150),
        "eiger2": ("EIGER2", 4.0, 80), "hexitec_proxy": ("HEXITEC", 2.0, 200)}
ENERGIES = sorted(weights)


def windowed_R(det_key, lo, hi, E):
    r = DATA / f"p2_bare_{det_key}_{E:.0f}keV.root"
    if not r.exists():
        return np.nan
    counts, charge_ke = m.read_cluster_charge(r, f"{det_key}_detector")
    cc = counts.sum()
    det = m.read_detected_event_count(r, f"{det_key}_detector")
    dep = charge_ke * EPS
    win = (dep >= lo) & (dep <= hi)
    wa = counts[win].sum() / cc if cc > 0 else 0
    return min(min(det / 10000, 1.0) * wa, 1.0)


detected = {}
for k, (name, lo, hi) in DETS.items():
    detected[k] = np.array([N0 * weights[E] * Tcu[E] * windowed_R(k, lo, hi, E) for E in ENERGIES])

INK, INK2, SURF, GRID = "#0b0b0b", "#5b5b57", "#fcfcfb", "#e8e8e4"
COL = {"medipix3": "#2a78d6", "medipix4": "#1baf7a", "timepix3_cdte": "#eb6834",
       "timepix4": "#4a3aa7", "eiger2": "#e34948", "hexitec_proxy": "#8a8a86"}
plt.rcParams.update({"figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
                     "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "font.size": 12, "axes.edgecolor": GRID})

fig, ax = plt.subplots(figsize=(10, 5.6))
Ex = np.array(ENERGIES)
for k, (name, lo, hi) in DETS.items():
    dash = k == "hexitec_proxy"
    ax.plot(Ex, detected[k], marker="o", color=COL[k], lw=2, ms=5,
            ls="--" if dash else "-", label=name)
ax.set_xlabel("Beam energy  (keV)")
ax.set_ylabel("Detected photons  (through 5 mm Cu)")
ax.set_title("Detected photons separated by beam energy", pad=10)
ax.set_xlim(15, 155)
ax.legend(frameon=False, fontsize=10, ncol=2)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.grid(color=GRID, lw=0.8); ax.set_axisbelow(True); ax.tick_params(length=0)
ax.annotate("EIGER2's 80 keV window\ndrops the high-energy beam", xy=(110, detected["eiger2"][ENERGIES.index(110)]),
            xytext=(118, 3200), fontsize=9, color=COL["eiger2"],
            arrowprops=dict(arrowstyle="->", color=COL["eiger2"], lw=1.2))
fig.tight_layout()
(BASE / "presentation_figures").mkdir(exist_ok=True)
fig.savefig(BASE / "presentation_figures/05_energy_spectrum.png", dpi=200)

out = pd.DataFrame({"beam_keV": ENERGIES, **{DETS[k][0]: detected[k] for k in DETS}})
out.to_csv(BASE / "data_csv/detected_by_energy.csv", index=False)
print("saved 05_energy_spectrum.png + detected_by_energy.csv")
for k, (name, lo, hi) in DETS.items():
    hi_frac = detected[k][np.array(ENERGIES) > 90].sum() / detected[k].sum()
    print(f"  {name:9} total={detected[k].sum():7,.0f}   share above 90 keV = {100*hi_frac:2.0f}%")
