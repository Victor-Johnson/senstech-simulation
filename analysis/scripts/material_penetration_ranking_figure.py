#!/usr/bin/env python3
"""Two-panel summary figure for the detector ranking.

Left: mean detected photons per detector (the true 1.0 mm result), one bar
      each, ranked by signal.
Right: bare-detector response curves at 1.0 mm, with each chip's upper window
       edge marked -- the physics behind the ranking.

Outputs analysis/<campaign-dir>/ranking_change.png
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import argparse

REPO = Path(__file__).resolve().parents[2]

_parser = argparse.ArgumentParser(description=__doc__)
_parser.add_argument(
    "--campaign-dir",
    default="material_penetration_uniform",
    help="Results dir under analysis/ used for the third (1.0 mm) campaign bar and the "
    "response curves (default: the uniform 1.0 mm run).",
)
_parser.add_argument(
    "--out",
    default=None,
    help="Output PNG path (default: <campaign-dir>/ranking_change.png).",
)
_parser.add_argument(
    "--uniform-label",
    default="This sim (uniform 1.0 mm sensors)",
    help="Legend label for the third campaign bar.",
)
_parser.add_argument(
    "--medipix3-edge",
    type=int,
    default=120,
    help="Medipix3 upper window edge in keV to draw on the response panel (default 120, "
    "Medipix3's true window).",
)
_args = _parser.parse_args()

CAMPAIGN_DIR = _args.campaign_dir
OUT = Path(_args.out) if _args.out else REPO / "analysis" / "results" / CAMPAIGN_DIR / "ranking_change.png"

# Reference categorical palette, slots 1-4 in validated order (dataviz skill).
SERIES = {"medipix3": "#2a78d6", "eiger2": "#1baf7a", "hexitec_proxy": "#eda100", "timepix3_cdte": "#008300"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e5e4e0"

LABELS = {
    "medipix3": "Medipix3",
    "eiger2": "EIGER2",
    "hexitec_proxy": "HEXITEC",
    "timepix3_cdte": "Timepix3",
}
UPPER_EDGE_KEV = {"medipix3": _args.medipix3_edge, "eiger2": 80, "hexitec_proxy": 200, "timepix3_cdte": 120}

mean_detected = {}
for tag, d in [("uniform", CAMPAIGN_DIR)]:
    perf = pd.read_csv(REPO / "analysis" / "results" / d / "performance_evaluation.csv")
    mean_detected[tag] = perf.set_index("detector")["mean_detected_total"]

resp = pd.read_csv(REPO / "analysis" / "results" / CAMPAIGN_DIR / "detector_response.csv")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5.0), dpi=180)
fig.patch.set_facecolor("#fcfcfb")

# ---- Left: one bar per detector (the true 1.0 mm result), ranked ----
order = mean_detected["uniform"].sort_values(ascending=False).index.tolist()
vals = [mean_detected["uniform"][d] for d in order]
bars = ax1.bar(range(len(order)), vals, width=0.62, color=[SERIES[d] for d in order], zorder=3)
for d, b, v in zip(order, bars, vals):
    if d == "hexitec_proxy":  # spectroscopic proxy, marked
        b.set_hatch("///")
        b.set_edgecolor("white")
    ax1.text(b.get_x() + b.get_width() / 2, v + 500, f"{v/1000:.1f}k",
             ha="center", va="bottom", fontsize=9, color=INK)
xlabels = [LABELS[d] + ("\n(proxy)" if d == "hexitec_proxy" else "") for d in order]
ax1.set_xticks(range(len(order)), xlabels, color=INK)
ax1.set_ylabel("Mean detected photons per 10⁶ fired\n(averaged over the 5 alloys)", color=INK)
ax1.set_title("Detected signal by detector", fontsize=12, color=INK, loc="left")
ax1.set_ylim(0, max(vals) * 1.18)
ax1.grid(axis="y", color=GRID, zorder=0)

# ---- Right: uniform-thickness response curves with window edges ----
label_dodge_pts = {"hexitec_proxy": 6, "medipix3": -7, "timepix3_cdte": 6, "eiger2": -7}
for det in order:
    d = resp[resp["detector"] == det].sort_values("energy_keV")
    ax2.plot(d["energy_keV"], d["windowed_response"], color=SERIES[det], lw=2,
             marker="o", ms=4, label=LABELS[det], zorder=3)
    last = d.iloc[-1]
    ax2.annotate(LABELS[det], (last["energy_keV"], last["windowed_response"]),
                 xytext=(6, label_dodge_pts[det]), textcoords="offset points",
                 fontsize=9, color=INK, va="center")
# Mark the upper window edges. Draw Medipix3's only if it falls on the plotted
# axis (its 120 keV edge does; a wider edge would sit off-axis and need no marker).
edge_dets = ["eiger2", "timepix3_cdte"]
if UPPER_EDGE_KEV["medipix3"] <= 178:
    edge_dets.append("medipix3")
edge_label_y = {det: 1.02 for det in edge_dets}
# If Medipix3's cap coincides with Timepix3's native edge, drop its label lower
# so the two don't overprint at the same x.
if "medipix3" in edge_dets and UPPER_EDGE_KEV["medipix3"] == UPPER_EDGE_KEV["timepix3_cdte"]:
    edge_label_y["medipix3"] = 0.80
for det in edge_dets:
    edge = UPPER_EDGE_KEV[det]
    ax2.axvline(edge, color=SERIES[det], lw=1, ls=(0, (4, 3)), alpha=0.6, zorder=2)
    ax2.text(edge, edge_label_y[det], f"{LABELS[det]}\nwindow ends {edge} keV", ha="center",
             va="bottom", fontsize=7.5, color=INK2)
ax2.axvspan(90, 130, color="#f3f2ee", zorder=1)
ax2.text(110, 0.02, "beam after 5 mm alloy\nis mostly here", ha="center", va="bottom",
         fontsize=8, color=INK2)
ax2.set_xlabel("Photon energy (keV)", color=INK)
ax2.set_ylabel("Probability a photon is counted\n(all sensors 1.0 mm CdTe)", color=INK)
ax2.set_title("The physics: upper window edges vs the hardened beam", fontsize=11, color=INK, loc="left")
ax2.set_xlim(15, 178)
ax2.set_ylim(0, 1.12)
ax2.grid(color=GRID, zorder=0)

for ax in (ax1, ax2):
    ax.set_facecolor("#fcfcfb")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK2)
    ax.tick_params(colors=INK2)

fig.tight_layout()
fig.savefig(OUT, facecolor=fig.get_facecolor())
print(f"wrote {OUT}")
