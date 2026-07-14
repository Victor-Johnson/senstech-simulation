#!/usr/bin/env python3
"""Medipix3 upper-window sensitivity figure (uniform 1.0 mm campaign).

Left: Medipix3 response with its standard 5-460 keV window vs capped at
      5-120 keV, with Timepix3 (2.88-120 keV) as the reference chip that
      natively has the 120 keV edge.
Right: what it does to the detected totals.

Outputs analysis/material_penetration_uniform_mpx120/medipix3_window_sensitivity.png
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "analysis" / "results" / "material_penetration_uniform_mpx120" / "medipix3_window_sensitivity.png"

# Color follows the entity (same mapping as ranking_change.png):
# Medipix3 = blue; its capped variant = same hue, lighter step + dashed.
BLUE, BLUE_LIGHT, GREEN = "#2a78d6", "#86b6ef", "#008300"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e5e4e0", "#fcfcfb"

resp_std = pd.read_csv(REPO / "analysis" / "results" / "material_penetration_uniform" / "detector_response.csv")
resp_cap = pd.read_csv(REPO / "analysis" / "results" / "material_penetration_uniform_mpx120" / "detector_response.csv")
perf_std = pd.read_csv(REPO / "analysis" / "results" / "material_penetration_uniform" / "performance_evaluation.csv").set_index("detector")
perf_cap = pd.read_csv(REPO / "analysis" / "results" / "material_penetration_uniform_mpx120" / "performance_evaluation.csv").set_index("detector")

mpx_std = resp_std[resp_std.detector == "medipix3"].sort_values("energy_keV")
mpx_cap = resp_cap[resp_cap.detector == "medipix3"].sort_values("energy_keV")
tpx = resp_std[resp_std.detector == "timepix3_cdte"].sort_values("energy_keV")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5.0), dpi=180, width_ratios=[1.5, 1])
fig.patch.set_facecolor(SURFACE)

# ---- Left: response curves ----
ax1.axvspan(90, 130, color="#f3f2ee", zorder=1)
ax1.text(106, 0.02, "beam after 5 mm alloy\nis mostly here", ha="center", va="bottom",
         fontsize=8, color=INK2)
series = [
    (mpx_std, BLUE, "-", "Medipix3, window 5–460 keV"),
    (mpx_cap, BLUE_LIGHT, (0, (5, 3)), "Medipix3, capped 5–120 keV"),
    (tpx, GREEN, "-", "Timepix3 (native 120 keV edge)"),
]
for d, color, ls, label in series:
    ax1.plot(d["energy_keV"], d["windowed_response"], color=color, ls=ls, lw=2,
             marker="o", ms=4, label=label, zorder=3)
label_pos = [
    ("Medipix3 5–460", mpx_std, 6),
    ("Medipix3 capped 120", mpx_cap, 5),
    ("Timepix3", tpx, -8),
]
for text, d, dy in label_pos:
    last = d.iloc[-1]
    ax1.annotate(text, (last["energy_keV"], last["windowed_response"]),
                 xytext=(6, dy), textcoords="offset points", fontsize=8.5, color=INK, va="center")
ax1.axvline(120, color=INK2, lw=1, ls=(0, (2, 3)), alpha=0.7, zorder=2)
ax1.text(120, 1.02, "120 keV window edge", ha="center", va="bottom", fontsize=7.5, color=INK2)
ax1.set_xlabel("Photon energy (keV)", color=INK)
ax1.set_ylabel("Probability a photon is counted\n(all sensors 1.0 mm CdTe)", color=INK)
ax1.set_title("Capping Medipix3 at 120 keV only trims the tail", fontsize=11, color=INK, loc="left")
ax1.set_xlim(15, 190)
ax1.set_ylim(0, 1.12)
ax1.legend(loc="upper left", fontsize=8, frameon=False)
ax1.grid(color=GRID, zorder=0)

# ---- Right: detected totals ----
bars = [
    ("Medipix3\n5–460 keV", float(perf_std.loc["medipix3", "mean_detected_total"]), BLUE),
    ("Medipix3\ncapped 120 keV", float(perf_cap.loc["medipix3", "mean_detected_total"]), BLUE_LIGHT),
    ("Timepix3\n(native 120 keV)", float(perf_std.loc["timepix3_cdte", "mean_detected_total"]), GREEN),
]
xs = range(len(bars))
for x, (label, v, color) in zip(xs, bars):
    ax2.bar(x, v, width=0.55, color=color, zorder=3)
    ax2.text(x, v + 300, f"{v/1000:.1f}k", ha="center", va="bottom", fontsize=9, color=INK)
ax2.annotate("−8.2%", xy=(1, 17750), ha="center", fontsize=9, color=INK2)
ax2.set_xticks(list(xs), [b[0] for b in bars], fontsize=8.5, color=INK)
ax2.set_ylabel("Mean detected photons per 10⁶ fired\n(averaged over the 5 alloys)", color=INK)
ax2.set_title("Ranking unchanged", fontsize=11, color=INK, loc="left")
ax2.set_ylim(0, 21000)
ax2.grid(axis="y", color=GRID, zorder=0)

for ax in (ax1, ax2):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2)

fig.tight_layout()
fig.savefig(OUT, facecolor=fig.get_facecolor())
print(f"wrote {OUT}")
