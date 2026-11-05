#!/usr/bin/env python3
"""Compare pure-Cu WINDOWED scatter buildup at 0 mm (contact) vs 30 mm air gap.

Uses production-consistent (windowed) counts so EIGER2's baseline matches the
ranking and the transport captures downscattered photons refilling its 4-80 keV
window. Reads the two saved windowed snapshots.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = Path("/home/victor-pc/itek/senstech-simulation/analysis/results/material_penetration_uniform")
zg = pd.read_csv(BASE / "pilot_cu_0mm_windowed.csv")
gp = pd.read_csv(BASE / "pilot_cu_30mm_windowed.csv")
lbl = {"medipix3": "Medipix3", "eiger2": "EIGER2", "hexitec_proxy": "HEXITEC proxy", "timepix3_cdte": "Timepix3"}
order = ["medipix3", "timepix3_cdte", "eiger2", "hexitec_proxy"]
colors = {"medipix3": "#2f7f74", "eiger2": "#c44e52", "hexitec_proxy": "#8172b3", "timepix3_cdte": "#4c72b0"}

def tot(df):
    return df.groupby("detector").agg(h=("hybrid_win_counts", "sum"), t=("transport_win_counts", "sum"))

tz, tg = tot(zg), tot(gp)
print("=" * 80)
print("PURE-Cu WINDOWED buildup:  0 mm contact  vs  30 mm realistic gap")
print("=" * 80)
print(f"{'detector':15}{'hybrid(win)':>12}{'0mm x':>9}{'30mm x':>9}")
for k in order:
    print(f"{lbl[k]:15}{tz.loc[k,'h']:>12,.0f}{tz.loc[k,'t']/tz.loc[k,'h']:>8.2f}x{tg.loc[k,'t']/tg.loc[k,'h']:>8.2f}x")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
for k in order:
    d0 = zg[(zg.detector == k) & (zg.energy_keV >= 60)].sort_values("energy_keV")
    d3 = gp[(gp.detector == k) & (gp.energy_keV >= 60)].sort_values("energy_keV")
    ax1.plot(d0.energy_keV, d0.delta_win_pct, "o-", color=colors[k], alpha=0.4, lw=1)
    ax1.plot(d3.energy_keV, d3.delta_win_pct, "s-", color=colors[k], label=lbl[k])
ax1.axhline(0, color="k", lw=0.8, ls="--")
ax1.set_xlabel("Photon energy (keV)")
ax1.set_ylabel("Windowed transport excess over hybrid (%)")
ax1.set_title("Windowed scatter excess vs energy\nfaint = 0mm contact, solid = 30mm gap")
ax1.legend(fontsize=8)
ax1.grid(alpha=0.3)

x = np.arange(len(order))
w = 0.26
ax2.bar(x - w, [tz.loc[k, "h"] for k in order], w, label="Hybrid (windowed)", color="#b9c6d6")
ax2.bar(x, [tz.loc[k, "t"] for k in order], w, label="Transport 0mm (contact)", color="#c44e52")
ax2.bar(x + w, [tg.loc[k, "t"] for k in order], w, label="Transport 30mm (realistic)", color="#2f7f74")
for xi, k in enumerate(order):
    ax2.text(xi + w, tg.loc[k, "t"], f"{tg.loc[k,'t']/tg.loc[k,'h']:.2f}x", ha="center", va="bottom", fontsize=8, fontweight="bold")
ax2.set_xticks(x, [lbl[k] for k in order], rotation=15)
ax2.set_ylabel("Pure-Cu detected counts (windowed, N0=1e6)")
ax2.set_title("Windowed totals: hybrid vs transport at 0mm vs 30mm gap")
ax2.legend(fontsize=8)
fig.tight_layout()
fig.savefig(BASE / "pilot_cu_gap_comparison.png", dpi=170)
print("\nSaved: pilot_cu_gap_comparison.png (windowed)")
