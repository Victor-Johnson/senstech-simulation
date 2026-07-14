#!/usr/bin/env python3
"""Clean single-run result figure for the material penetration study.

Left:  mean detected photons per detector (this run only, no comparison).
Right: bare-detector response curves at 1.0 mm CdTe, with each chip's upper
       window edge marked.

Defaults to the uniform 1.0 mm run (Medipix3 window 5-120 keV). Output goes to
<campaign-dir>/result_summary.png.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = Path(__file__).resolve().parents[2]

_parser = argparse.ArgumentParser(description=__doc__)
_parser.add_argument(
    "--campaign-dir",
    default="material_penetration_uniform",
    help="Results dir under analysis/ to read from (default: the uniform 1.0 mm run).",
)
_parser.add_argument("--out", default=None, help="Output PNG (default: <campaign-dir>/result_summary.png).")
_args = _parser.parse_args()

CAMPAIGN_DIR = _args.campaign_dir
OUT = Path(_args.out) if _args.out else REPO / "analysis" / "results" / CAMPAIGN_DIR / "result_summary.png"

# Color follows the detector (validated categorical palette, dataviz skill).
SERIES = {"eiger2": "#1baf7a", "hexitec_proxy": "#eda100", "medipix3": "#2a78d6", "timepix3_cdte": "#008300"}
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e5e4e0", "#fcfcfb"
LABELS = {"medipix3": "Medipix3", "eiger2": "EIGER2", "hexitec_proxy": "HEXITEC", "timepix3_cdte": "Timepix3"}
UPPER_EDGE_KEV = {"medipix3": 120, "eiger2": 80, "hexitec_proxy": 200, "timepix3_cdte": 120}

perf = pd.read_csv(REPO / "analysis" / "results" / CAMPAIGN_DIR / "performance_evaluation.csv").set_index("detector")
resp = pd.read_csv(REPO / "analysis" / "results" / CAMPAIGN_DIR / "detector_response.csv")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.5, 5.0), dpi=180)
fig.patch.set_facecolor(SURFACE)

# ---- Left: one bar per detector, ordered by detected signal ----
order = perf["mean_detected_total"].sort_values(ascending=False).index.tolist()
vals = [perf.loc[d, "mean_detected_total"] for d in order]
errs = [perf.loc[d, "mean_detected_total_se"] for d in order]
bars = ax1.bar(range(len(order)), vals, yerr=errs, capsize=4,
               color=[SERIES[d] for d in order], zorder=3)
for d, b, v in zip(order, bars, vals):
    if d == "hexitec_proxy":  # mark the spectroscopic proxy visually
        b.set_hatch("///")
        b.set_edgecolor("white")
    ax1.text(b.get_x() + b.get_width() / 2, v + 600, f"{v/1000:.1f}k",
             ha="center", va="bottom", fontsize=9, color=INK)
xlabels = [LABELS[d] + ("\n(proxy)" if d == "hexitec_proxy" else "") for d in order]
ax1.set_xticks(range(len(order)), xlabels, color=INK)
ax1.set_ylabel("Mean detected photons per 10⁶ fired\n(averaged over the 5 alloys)", color=INK)
ax1.set_title("Detected signal by detector", fontsize=12, color=INK, loc="left")
ax1.set_ylim(0, max(vals) * 1.18)
ax1.grid(axis="y", color=GRID, zorder=0)

# ---- Right: response curves with upper window edges ----
label_dodge = {"hexitec_proxy": 6, "medipix3": -7, "timepix3_cdte": 6, "eiger2": -7}
for det in order:
    d = resp[resp["detector"] == det].sort_values("energy_keV")
    ax2.plot(d["energy_keV"], d["windowed_response"], color=SERIES[det], lw=2,
             marker="o", ms=4, zorder=3)
    last = d.iloc[-1]
    ax2.annotate(LABELS[det], (last["energy_keV"], last["windowed_response"]),
                 xytext=(6, label_dodge[det]), textcoords="offset points",
                 fontsize=9, color=INK, va="center")

# Draw upper-window edges; merge detectors that share an edge into one label.
ax2.axvspan(90, 130, color="#f3f2ee", zorder=1)
ax2.text(110, 0.02, "beam after 5 mm alloy\nis mostly here", ha="center", va="bottom",
         fontsize=8, color=INK2)
edges: dict[int, list[str]] = {}
for det in ("eiger2", "medipix3", "timepix3_cdte"):
    edges.setdefault(UPPER_EDGE_KEV[det], []).append(LABELS[det])
for edge, dets in edges.items():
    ax2.axvline(edge, color=INK2, lw=1, ls=(0, (4, 3)), alpha=0.55, zorder=2)
    ax2.text(edge, 1.02, f"{' & '.join(dets)}\nwindow ends {edge} keV",
             ha="center", va="bottom", fontsize=7.5, color=INK2)
ax2.set_xlabel("Photon energy (keV)", color=INK)
ax2.set_ylabel("Probability a photon is counted\n(all sensors 1.0 mm CdTe)", color=INK)
ax2.set_title("Response vs photon energy", fontsize=12, color=INK, loc="left")
ax2.set_xlim(15, 178)
ax2.set_ylim(0, 1.12)
ax2.grid(color=GRID, zorder=0)

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
