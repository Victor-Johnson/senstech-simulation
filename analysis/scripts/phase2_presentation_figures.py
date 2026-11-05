#!/usr/bin/env python3
"""Phase 2 presentation figures — simple, minimal-text."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = Path("/home/victor-pc/itek/senstech-simulation/analysis/results/phase2_selection_framework")
OUT = BASE / "presentation_figures"
OUT.mkdir(exist_ok=True)

INK, INK2, SURF = "#0b0b0b", "#5b5b57", "#fcfcfb"
BLUE, GREY, GRID = "#2a78d6", "#c2ccd6", "#e8e8e4"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "font.size": 13, "axes.titlesize": 15, "axes.titleweight": "normal",
    "axes.edgecolor": GRID, "axes.linewidth": 1.0,
})
NAME = {"medipix3": "Medipix3", "medipix4": "Medipix4", "timepix3_cdte": "Timepix3",
        "timepix4": "Timepix4", "eiger2": "EIGER2", "hexitec_proxy": "HEXITEC"}


def load(scn):
    t = pd.read_csv(BASE / f"data_csv/table10_{scn}.csv")
    g = t.groupby("detector").agg(th=("N_theory", "mean"), sim=("N_sim", "mean")).reset_index()
    return g, t


def bare(ax, axis="x"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis=axis, color=GRID, lw=1); ax.set_axisbelow(True)
    ax.tick_params(length=0)


def ranking(scn, title, fname):
    g, _ = load(scn)
    g = g.sort_values("sim")
    y = np.arange(len(g))
    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.barh(y, g.sim, 0.62, color=BLUE)
    for yi, v in zip(y, g.sim):
        ax.text(v + max(g.sim) * 0.012, yi, f"{v:,.0f}", va="center", fontsize=12, color=INK)
    ax.set_yticks(y, [NAME[k] for k in g.detector], fontsize=13)
    ax.set_xlim(0, max(g.sim) * 1.15)
    ax.set_xlabel("Detected photons (per million fired)")
    ax.set_title(title, pad=12)
    bare(ax)
    fig.tight_layout(); fig.savefig(OUT / fname, dpi=200); plt.close(fig)


def theory_vs_sim(scn, fname):
    g, _ = load(scn)
    g = g.sort_values("sim", ascending=False)
    x = np.arange(len(g)); w = 0.4
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.bar(x - w / 2, g.th, w, color=GREY, label="Predicted (physics)")
    ax.bar(x + w / 2, g.sim, w, color=BLUE, label="Simulated")
    ax.set_xticks(x, [NAME[k] for k in g.detector], fontsize=12)
    ax.set_ylabel("Detected photons (per million fired)")
    ax.set_title("Prediction vs simulation", pad=12)
    ax.legend(frameon=False, fontsize=12, loc="upper right")
    bare(ax, "y")
    fig.tight_layout(); fig.savefig(OUT / fname, dpi=200); plt.close(fig)


def matrix(scn, fname):
    g, t = load(scn)
    ALLOY = {"alloy1": "Cu", "alloy2": "Brass", "alloy3": "CuNi", "alloy4": "Al-bronze", "alloy5": "BeCu"}
    order = g.sort_values("sim", ascending=False).detector.tolist()
    piv = t.pivot(index="detector", columns="alloy", values="N_sim").reindex(order)
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    im = ax.imshow(piv.values, aspect="auto", cmap="Blues", vmin=0)
    ax.set_xticks(range(piv.shape[1]), [ALLOY[a] for a in piv.columns], fontsize=12)
    ax.set_yticks(range(len(order)), [NAME[k] for k in order], fontsize=12)
    mx = np.nanmax(piv.values)
    for i in range(len(order)):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            ax.text(j, i, f"{v:,.0f}", ha="center", va="center", fontsize=11,
                    color="white" if v > mx * 0.55 else INK)
    ax.set_title("Detected photons — detector × alloy", pad=12)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks(np.arange(-.5, piv.shape[1]), minor=True)
    ax.set_yticks(np.arange(-.5, len(order)), minor=True)
    ax.grid(which="minor", color=SURF, lw=2); ax.tick_params(which="both", length=0)
    fig.tight_layout(); fig.savefig(OUT / fname, dpi=200); plt.close(fig)


if __name__ == "__main__":
    ranking("native", "Detected counts by detector  (commercial thickness)", "01_ranking_native.png")
    ranking("matched", "Detected counts by detector  (matched 0.75 mm)", "02_ranking_matched.png")
    theory_vs_sim("native", "03_theory_vs_sim.png")
    matrix("native", "04_detector_alloy_matrix.png")
    print("wrote:", *[p.name for p in sorted(OUT.glob("*.png"))])
