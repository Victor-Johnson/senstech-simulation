#!/usr/bin/env python3
"""Two simple figures that explain the calculation itself.

1. calculation_anatomy.png -- the hybrid formula
   detected = N0 x weight x transmission x response, factor by factor,
   for the worked example used in the docs (Timepix3 x aluminum bronze),
   with the 100 keV column traced through all four panels.

2. beam_hardening_spectra.png -- incident beam shape vs the beam that
   survives 5 mm of aluminum bronze: the physical reason upper window
   edges decide the detector ranking.

Outputs into analysis/material_penetration_uniform/.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "analysis" / "results" / "material_penetration_uniform"

BLUE, AQUA, YELLOW, GREEN = "#2a78d6", "#1baf7a", "#eda100", "#008300"
INK, INK2, GRID, SURFACE, MUTED = "#0b0b0b", "#52514e", "#e5e4e0", "#fcfcfb", "#b5b3ac"
HILITE_E = 100.0

spectrum = pd.read_csv(REPO / "spectra" / "150kvp_weights.csv")
att = pd.read_csv(REPO / "analysis" / "results" / "material_penetration_fixed" / "alloy_attenuation.csv")
resp = pd.read_csv(REPO / "analysis" / "results" / "material_penetration_uniform" / "detector_response.csv")

E = spectrum["energy_keV"].to_numpy()
w = spectrum["weight"].to_numpy()
T = att[att.alloy == "alloy4"].sort_values("energy_keV")["transmission"].to_numpy()
R = resp[resp.detector == "timepix3_cdte"].sort_values("energy_keV")["windowed_response"].to_numpy()
N0 = 1_000_000
incident = N0 * w
detected = incident * T * R
hi = int(np.where(E == HILITE_E)[0][0])


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.grid(axis="y", color=GRID, zorder=0)


# ================= Figure 1: anatomy of the calculation =================
fig, axes = plt.subplots(4, 1, figsize=(8.5, 9.2), dpi=180, sharex=True)
fig.patch.set_facecolor(SURFACE)
ax_a, ax_b, ax_c, ax_d = axes

for ax in axes:
    ax.axvspan(HILITE_E - 3.4, HILITE_E + 3.4, color="#fdeecd", zorder=1)

ax_a.bar(E, incident, width=7, color=BLUE, zorder=3)
ax_a.set_title("Step 1 — the beam: 1,000,000 photons split by the spectrum weights",
               fontsize=10, color=INK, loc="left")
ax_a.set_ylabel("photons fired\nper energy slice", fontsize=8.5, color=INK)
ax_a.text(HILITE_E, incident[hi] + 8000, f"{incident[hi]:,.0f}\nat 100 keV", ha="center",
          va="bottom", fontsize=8, color=INK)
ax_a.set_ylim(0, 245000)

ax_b.plot(E, T, color=AQUA, lw=2, marker="o", ms=4, zorder=3)
ax_b.set_title("Step 2 — the slab: fraction passing 5 mm of aluminum bronze untouched (Beer–Lambert)",
               fontsize=10, color=INK, loc="left")
ax_b.set_ylabel("transmission", fontsize=8.5, color=INK)
ax_b.text(HILITE_E, T[hi] + 0.05, f"× {T[hi]:.3f}", ha="center", va="bottom", fontsize=8.5, color=INK)
ax_b.set_ylim(0, 0.62)

ax_c.plot(E, R, color=GREEN, lw=2, marker="o", ms=4, zorder=3)
ax_c.set_title("Step 3 — the chip: probability Timepix3 (1.0 mm) counts a photon of this energy",
               fontsize=10, color=INK, loc="left")
ax_c.set_ylabel("response", fontsize=8.5, color=INK)
ax_c.text(HILITE_E, R[hi] + 0.06, f"× {R[hi]:.3f}", ha="center", va="bottom", fontsize=8.5, color=INK)
ax_c.set_ylim(0, 0.95)

ax_d.bar(E, detected, width=7, color=YELLOW, zorder=3)
ax_d.set_title("Step 4 — multiply the three, slice by slice: photons actually counted",
               fontsize=10, color=INK, loc="left")
ax_d.set_ylabel("photons counted\nper energy slice", fontsize=8.5, color=INK)
ax_d.set_xlabel("Photon energy (keV)", color=INK)
ax_d.text(HILITE_E, detected[hi] + 200, f"= {detected[hi]:,.0f}", ha="center", va="bottom",
          fontsize=8.5, color=INK)
ax_d.text(24, 5600,
          f"sum of all 14 slices = {detected.sum():,.0f} photons\n"
          "(this one number is what goes into the ranking tables)",
          fontsize=8.5, color=INK2, va="top")
ax_d.set_ylim(0, 6300)

for ax in axes:
    style(ax)
fig.suptitle("How one number is calculated:  detected = 1,000,000 × weight × transmission × response\n"
             "worked example: Timepix3 behind 5 mm aluminum bronze — follow the highlighted 100 keV slice",
             fontsize=10.5, color=INK, x=0.02, ha="left")
fig.tight_layout(rect=(0, 0, 1, 0.94))
fig.savefig(OUT_DIR / "calculation_anatomy.png", facecolor=fig.get_facecolor())
plt.close(fig)

# ================= Figure 2: beam hardening, seen directly =================
trans_shape = w * T / (w * T).sum()
mean_in = float(np.average(E, weights=w))
mean_out = float(np.average(E, weights=w * T))

fig, ax = plt.subplots(figsize=(8.5, 4.6), dpi=180)
fig.patch.set_facecolor(SURFACE)
width = 3.4
ax.bar(E - width / 2 - 0.2, w, width=width, color=MUTED, label="beam entering the slab", zorder=3)
ax.bar(E + width / 2 + 0.2, trans_shape, width=width, color=BLUE,
       label="beam after 5 mm aluminum bronze", zorder=3)
for mean, color, y, name in [(mean_in, INK2, 0.225, f"mean {mean_in:.0f} keV"),
                             (mean_out, BLUE, 0.245, f"mean {mean_out:.0f} keV")]:
    ax.annotate("", xy=(mean, y - 0.012), xytext=(mean, y),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.4))
    ax.text(mean, y + 0.003, name, ha="center", fontsize=8.5, color=color)
ax.annotate("", xy=(mean_out - 2, 0.262), xytext=(mean_in + 2, 0.262),
            arrowprops=dict(arrowstyle="->", color=INK2, lw=1.2))
ax.text((mean_in + mean_out) / 2, 0.268, "the metal eats the soft photons first,\nso the survivors are much harder",
        ha="center", fontsize=8.5, color=INK2)
ax.set_xlabel("Photon energy (keV)", color=INK)
ax.set_ylabel("Share of photons in each slice", color=INK)
ax.set_title("Beam hardening: why the upper window edge decides the ranking", fontsize=11,
             color=INK, loc="left")
ax.set_ylim(0, 0.30)
ax.legend(loc="upper left", fontsize=8.5, frameon=False)
style(ax)
ax.grid(axis="y", color=GRID, zorder=0)
fig.tight_layout()
fig.savefig(OUT_DIR / "beam_hardening_spectra.png", facecolor=fig.get_facecolor())
print("wrote", OUT_DIR / "calculation_anatomy.png")
print("wrote", OUT_DIR / "beam_hardening_spectra.png")
