#!/usr/bin/env python3
"""Phase 2 physics figures for all 6 candidates.

Three figures, reusing the exact Phase-2 experiment data/helpers:
  05_cnr_matrix_phase2.png    -- CNR (material discrimination) matrix: 6 detectors x 10 alloy pairs
  06_alloy_attenuation.png    -- Beer-Lambert transmission T(E) through the 5 alloys, with each
                                 candidate's upper energy-window edge marked (all 6 shown)
  07_cdte_interaction.png     -- CdTe interaction probability P(E) at each candidate's native
                                 thickness, with each chip's upper-window cut marked (all 6 shown)

Run:  PYTHONPATH=. ./venv/bin/python analysis/scripts/phase2_physics_figures.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import analysis.scripts.phase2_selection_experiment as p2

BASE = Path("/home/victor-pc/itek/senstech-simulation/analysis/results/phase2_selection_framework")
OUT = BASE / "presentation_figures"
OUT.mkdir(exist_ok=True)

INK, INK2, SURF = "#0b0b0b", "#5b5b57", "#fcfcfb"
GRID = "#e8e8e4"
plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "font.size": 13, "axes.titlesize": 15, "axes.titleweight": "normal",
    "axes.edgecolor": GRID, "axes.linewidth": 1.0,
})

NAME = {"medipix3": "Medipix3", "medipix4": "Medipix4", "timepix3_cdte": "Timepix3",
        "timepix4": "Timepix4", "eiger2": "EIGER2", "hexitec_proxy": "HEXITEC"}
# Okabe-Ito colour-blind-safe palette, one per candidate
DCOL = {"medipix3": "#0072B2", "medipix4": "#D55E00", "timepix3_cdte": "#009E73",
        "timepix4": "#CC79A7", "eiger2": "#E69F00", "hexitec_proxy": "#56B4E9"}
ALLOY_SHORT = {"alloy1": "Cu", "alloy2": "Brass", "alloy3": "CuNi", "alloy4": "Al-bronze", "alloy5": "BeCu"}
ACOL = {"alloy1": "#b5651d", "alloy2": "#c9a227", "alloy3": "#5b8a72", "alloy4": "#8d6e63", "alloy5": "#6a8caf"}


def bare(ax, axis="both"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis=axis, color=GRID, lw=1)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


# ---------------------------------------------------------------- 1. CNR matrix
def cnr_matrix(scn="native", fname="05_cnr_matrix_phase2.png"):
    """Per-candidate symmetric 5x5 CNR matrices (Study-A style), 6 chips in a 2x3 grid."""
    cnr = pd.read_csv(BASE / f"data_csv/cnr_{scn}.csv")
    order = ["medipix3", "medipix4", "timepix3_cdte", "timepix4", "eiger2", "hexitec_proxy"]
    alloys = list(ALLOY_SHORT)                      # alloy1..alloy5
    short = [ALLOY_SHORT[a] for a in alloys]        # Cu, Brass, CuNi, Al-bronze, BeCu
    vmax = float(np.nanmax(cnr["CNR_sim"]))

    fig, axes = plt.subplots(2, 3, figsize=(13.5, 8.6))
    fig.subplots_adjust(top=0.88, bottom=0.08, wspace=0.55, hspace=0.35)
    for ax, det in zip(axes.ravel(), order):
        sub = cnr[cnr.detector == det].set_index("pair")["CNR_sim"]
        M = pd.DataFrame(np.nan, index=alloys, columns=alloys)
        for pair, v in sub.items():
            a, b = pair.split("-")
            M.loc[a, b] = v
            M.loc[b, a] = v
        im = ax.imshow(M.to_numpy().astype(float), cmap="magma_r", vmin=0, vmax=vmax)
        ax.set_xticks(np.arange(len(alloys)), short, rotation=45, ha="right", fontsize=10)
        ax.set_yticks(np.arange(len(alloys)), short, fontsize=10)
        ax.set_title(NAME[det], pad=8, fontsize=14)
        for i in range(len(alloys)):
            for j in range(len(alloys)):
                if i == j:
                    continue
                val = M.iloc[i, j]
                if np.isfinite(val):
                    ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=9,
                            color="white" if val > vmax * 0.6 else "black")
        for s in ax.spines.values():
            s.set_visible(False)
        ax.tick_params(length=0)
    fig.colorbar(im, ax=axes, label="CNR (Poisson-limited approximation)", shrink=0.6, pad=0.02)
    fig.suptitle("Alloy Pair Discrimination (CNR) Matrix — 6 candidates", fontsize=17, y=0.955)
    fig.savefig(OUT / fname, dpi=200)
    plt.close(fig)
    return fname


# ----------------------- 2. Alloy attenuation heatmap (Study-A style, 06)
ALLOY_FULL = {"alloy1": "C11000 Cu", "alloy2": "C36000 brass", "alloy3": "CuNi 90/10",
              "alloy4": "C95500 Al bronze", "alloy5": "C17200 BeCu"}


def alloy_attenuation(fname="06_alloy_attenuation.png"):
    """log10(T) heatmap in the Study-A '02' style, with the 6 candidates'
    upper window edges marked as dashed columns."""
    att = pd.read_csv(p2.UNIFORM / "alloy_attenuation.csv")
    with plt.style.context("default"):
        pivot = att.pivot(index="alloy", columns="energy_keV", values="transmission").loc[list(ALLOY_FULL)]
        energies = list(pivot.columns)
        values = np.log10(pivot.replace(0, np.nan).to_numpy())
        fig, ax = plt.subplots(figsize=(11, 5.0))
        im = ax.imshow(values, aspect="auto", cmap="viridis", vmin=-8, vmax=0)
        ax.set_xticks(np.arange(len(energies)), [f"{e:.0f}" for e in energies])
        ax.set_yticks(np.arange(len(ALLOY_FULL)), [ALLOY_FULL[a] for a in pivot.index])
        ax.set_xlabel("Energy (keV)")
        ax.set_title("Alloy transmission: log10(T), 5 mm thickness")
        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label("log10 transmission")
        for i in range(pivot.shape[0]):
            for j in range(pivot.shape[1]):
                val = pivot.iloc[i, j]
                text = f"{val:.2f}" if val >= 1e-3 else (f"{val:.0e}" if val >= 1e-8 else "<1e-8")
                ax.text(j, i, text, ha="center", va="center", fontsize=7,
                        color="white" if values[i, j] < -3 else "black")

        fig.savefig(OUT / fname, dpi=220, bbox_inches="tight")
        plt.close(fig)
    return fname


# ------- 3. CdTe detector response R(E) (Study-A '03' line style, all 6 chips)
def cdte_interaction(scn="native", fname="07_cdte_interaction.png"):
    """Windowed detector response R(E) per candidate (interaction x threshold/window
    acceptance, from the p2_bare ROOTs), plotted like Study-A '03'."""
    weights, T, mu, manifest = p2.load_inputs()
    energies = np.array(sorted(weights))
    thick = p2.SCENARIOS[scn]
    det_by_key = {d.key: d for d in p2.DETS}
    order = ["medipix3", "medipix4", "timepix3_cdte", "timepix4", "eiger2", "hexitec_proxy"]
    styles = {  # colours in the Study-A '03' family; HEXITEC proxy dashed
        "medipix3": ("#1f77b4", "-"), "medipix4": ("#ff7f0e", "-"),
        "timepix3_cdte": ("#d62728", "-"), "timepix4": ("#9467bd", "-"),
        "eiger2": ("#2ca02c", "-"), "hexitec_proxy": ("#7f7f7f", "--"),
    }
    with plt.style.context("default"):
        fig, ax = plt.subplots(figsize=(9, 5))
        for k in order:
            det = det_by_key[k]
            r = np.array([p2.bare_windowed_response(
                det, thick[k], float(E), p2.m.get_events(manifest, "bare", k, float(E), 10000))
                for E in energies])
            resp, se = r[:, 0], r[:, 1]
            color, ls = styles[k]
            ax.errorbar(energies, resp, yerr=se, marker="o", lw=2, ls=ls,
                        color=color, capsize=2, label=NAME[k])
        ax.set_xlabel("Energy (keV)")
        ax.set_ylabel("Photon-equivalent response")
        ax.set_ylim(0, 1.08)
        ax.set_title("CdTe detector response after threshold and energy-window logic\n"
                     "(6 candidates · error bars: binomial SE, 10k-event MC)")
        ax.legend(ncol=2, frameon=True)
        fig.savefig(OUT / fname, dpi=220, bbox_inches="tight")
        plt.close(fig)
    return fname


if __name__ == "__main__":
    written = [cnr_matrix(), alloy_attenuation(), cdte_interaction()]
    print("wrote:", *written)
