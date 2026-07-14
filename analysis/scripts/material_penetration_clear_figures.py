#!/usr/bin/env python3
"""Create presentation-focused figures for the material penetration study."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import spekpy as sp


import argparse

ROOT = Path(__file__).resolve().parents[2]
_parser = argparse.ArgumentParser(description=__doc__)
_parser.add_argument(
    "--base",
    default="material_penetration_fixed",
    help="Results directory under analysis/ to read from (default: the corrected baseline; "
    "use material_penetration_uniform for the 1.0 mm campaign).",
)
_args = _parser.parse_args()
BASE = ROOT / "analysis" / "results" / _args.base
OUT = BASE / "presentation_figures"
SPECTRUM = ROOT / "spectra" / "150kvp_weights.csv"

DETECTOR_LABELS = {
    "medipix3": "Medipix3",
    "eiger2": "EIGER2",
    "hexitec_proxy": "HEXITEC proxy",
    "timepix3_cdte": "Timepix3 CdTe",
}

ALLOY_LABELS = {
    "alloy1": "C11000 Cu",
    "alloy2": "C36000 brass",
    "alloy3": "CuNi 90/10",
    "alloy4": "C95500 Al bronze",
    "alloy5": "C17200 BeCu",
}


def savefig(fig: plt.Figure, name: str) -> None:
    fig.savefig(OUT / name, dpi=220, bbox_inches="tight")
    plt.close(fig)


def add_value_labels(ax: plt.Axes, fmt: str = "{:.0f}", pad: float = 3) -> None:
    for patch in ax.patches:
        height = patch.get_height()
        if not np.isfinite(height):
            continue
        ax.annotate(
            fmt.format(height),
            (patch.get_x() + patch.get_width() / 2, height),
            ha="center",
            va="bottom",
            xytext=(0, pad),
            textcoords="offset points",
            fontsize=8,
        )


def plot_xray_source(weights: pd.DataFrame, spectrum_summary: pd.DataFrame) -> None:
    source = sp.Spek(kvp=150.0, th=12.0)
    source.filter("Al", 1.0)
    source.filter("Al", 1.0)
    k, phi = source.get_spectrum(edges=False)
    phi_norm = phi / np.max(phi)
    continuous = pd.DataFrame({"energy_keV": k, "relative_fluence": phi_norm})
    continuous.to_csv(BASE / "xray_source_model.csv", index=False)

    mean_energy = float(spectrum_summary.loc[0, "mean_energy_keV"])
    peak_energy = float(spectrum_summary.loc[0, "peak_energy_keV"])

    fig, ax1 = plt.subplots(figsize=(9, 4.8))
    ax1.plot(k, phi_norm, color="#1b4f72", lw=2.2, label="Continuous SpekPy model")
    ax1.set_xlabel("Photon energy (keV)")
    ax1.set_ylabel("Relative fluence")
    ax1.set_xlim(0, 155)
    ax1.set_ylim(bottom=0)
    ax1.axvline(mean_energy, color="#b03a2e", ls="--", lw=1.5, label=f"Mean {mean_energy:.1f} keV")
    ax1.axvline(peak_energy, color="#7d3c98", ls=":", lw=1.8, label=f"Discrete peak {peak_energy:.0f} keV")

    ax2 = ax1.twinx()
    ax2.bar(weights["energy_keV"], weights["weight"], width=7, color="#f5b041", alpha=0.45, label="14-bin weights")
    ax2.set_ylabel("Discrete bin weight")

    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="upper right", frameon=True)
    ax1.set_title("X-ray source model: 150 kVp tungsten tube with 2 mm Al filtration")
    ax1.text(
        0.02,
        0.08,
        "Spectral weights for monoenergetic Allpix bins",
        transform=ax1.transAxes,
        fontsize=8,
        va="bottom",
        bbox={"boxstyle": "round,pad=0.25", "fc": "white", "ec": "#cccccc"},
    )
    savefig(fig, "01_xray_source_model.png")


def plot_transmission_heatmap(attenuation: pd.DataFrame) -> None:
    pivot = attenuation.pivot(index="alloy", columns="energy_keV", values="transmission").loc[list(ALLOY_LABELS)]
    labels = pivot.rename(index=ALLOY_LABELS)
    values = np.log10(pivot.replace(0, np.nan).to_numpy())

    fig, ax = plt.subplots(figsize=(10, 4.8))
    im = ax.imshow(values, aspect="auto", cmap="viridis", vmin=-8, vmax=0)
    ax.set_xticks(np.arange(len(pivot.columns)), [f"{e:.0f}" for e in pivot.columns], rotation=0)
    ax.set_yticks(np.arange(len(labels.index)), labels.index)
    ax.set_xlabel("Energy (keV)")
    ax.set_title("Alloy transmission: log10(T), 5 mm thickness")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("log10 transmission")
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = pivot.iloc[i, j]
            if val >= 1e-3:
                text = f"{val:.2f}"
            elif val >= 1e-8:
                text = f"{val:.0e}"
            else:
                text = "<1e-8"
            ax.text(j, i, text, ha="center", va="center", fontsize=7, color="white" if values[i, j] < -3 else "black")
    savefig(fig, "02_alloy_transmission_heatmap.png")


def plot_detector_response(response: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    order = ["medipix3", "eiger2", "timepix3_cdte", "hexitec_proxy"]
    styles = {
        "medipix3": ("#1f77b4", "-"),
        "eiger2": ("#2ca02c", "-"),
        "timepix3_cdte": ("#d62728", "-"),
        "hexitec_proxy": ("#7f7f7f", "--"),
    }
    for detector in order:
        data = response[response["detector"] == detector]
        color, ls = styles[detector]
        ax.errorbar(
            data["energy_keV"], data["windowed_response"], yerr=data["windowed_response_se"],
            marker="o", lw=2, ls=ls, color=color, capsize=2, label=DETECTOR_LABELS[detector],
        )
    ax.axvspan(2.5, 120, color="#d62728", alpha=0.06, label="Timepix3 analysis window")
    ax.set_xlabel("Energy (keV)")
    ax.set_ylabel("Photon-equivalent response")
    ax.set_ylim(0, 1.08)
    ax.set_title("CdTe detector response after threshold and energy-window logic\n(error bars: binomial SE, 10k-event MC)")
    ax.legend(ncol=2, frameon=True)
    savefig(fig, "03_cdte_detector_response.png")


def plot_matrix_heatmap(combined: pd.DataFrame) -> None:
    matrix = combined.pivot(index="detector", columns="alloy", values="detected_total")
    order = ["medipix3", "eiger2", "timepix3_cdte", "hexitec_proxy"]
    matrix = matrix.loc[order, list(ALLOY_LABELS)]

    fig, ax = plt.subplots(figsize=(9, 4.8))
    im = ax.imshow(matrix.to_numpy(), aspect="auto", cmap="YlGnBu")
    ax.set_xticks(np.arange(matrix.shape[1]), [ALLOY_LABELS[c] for c in matrix.columns], rotation=20, ha="right")
    ax.set_yticks(np.arange(matrix.shape[0]), [DETECTOR_LABELS[i] for i in matrix.index])
    ax.set_title("Detector-alloy matrix: detected photons from N0 = 1,000,000")
    cbar = fig.colorbar(im, ax=ax)
    cbar.set_label("Detected photons")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix.iloc[i, j]
            ax.text(j, i, f"{val:,.0f}", ha="center", va="center", fontsize=8, color="white" if val > 16000 else "black")
    savefig(fig, "04_detector_alloy_matrix_heatmap.png")


def plot_real_performance(performance: pd.DataFrame) -> None:
    """Shows all 4 detectors, not just the 3 real photon-counting ones -- HEXITEC
    is included but visually distinguished (hatched, muted) and labeled directly
    on the chart, so its different status is self-explanatory rather than a
    silent omission that invites "where's the 4th chip" questions."""
    real = performance[~performance["proxy_result"]].sort_values("rank_real_photon_counting_detectors")
    proxy = performance[performance["proxy_result"]]

    labels = [DETECTOR_LABELS.get(d, d) for d in real["detector"]] + [
        DETECTOR_LABELS.get(d, d) for d in proxy["detector"]
    ]
    values = pd.concat([real["mean_detected_total"], proxy["mean_detected_total"]])
    errors = pd.concat([real["mean_detected_total_se"], proxy["mean_detected_total_se"]])
    fractions = pd.concat([real["mean_detected_fraction_of_transmitted"], proxy["mean_detected_fraction_of_transmitted"]])
    colors = ["#d62728", "#1f77b4", "#2ca02c", "#9a9a9a"]
    hatches = [None, None, None, "///"]

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    bars = ax.bar(labels, values, yerr=errors, capsize=4, color=colors)
    for bar, hatch in zip(bars, hatches):
        if hatch:
            bar.set_hatch(hatch)
            bar.set_edgecolor("black")
    ax.axvline(len(real) - 0.5, color="black", ls=":", lw=1.2)
    ax.set_title("Performance evaluation: all 4 detectors\n(error bars: propagated binomial SE)")
    ax.set_ylabel("Mean detected photons across alloys")
    ax.set_ylim(0, max(values) * 1.34)
    add_value_labels(ax, "{:,.0f}")
    for bar, frac in zip(bars, fractions):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() * 0.52,
            f"{frac:.1%}\nof transmitted",
            ha="center",
            va="center",
            fontsize=9,
            color="white",
            fontweight="bold",
        )
    ax.text(
        len(real) - 0.5 + 0.05, max(values) * 1.33,
        "HEXITEC: spectroscopic proxy, shown for reference,\nnot a true photon counter -- excluded from rank",
        ha="left", va="top", fontsize=8.5, style="italic",
        bbox=dict(boxstyle="round", facecolor="#f5f5f5", edgecolor="#9a9a9a"),
    )
    savefig(fig, "05_real_detector_performance.png")


def plot_energy_bins(bin_summary: pd.DataFrame) -> None:
    """Includes HEXITEC as a 4th panel (its single wide 2-200 keV bin, since its
    proxy digitizer doesn't sub-divide energy the way the other three do), rather
    than silently dropping the 4th detector from the figure."""
    alloy = "alloy4"
    subset = (
        bin_summary[bin_summary["alloy"] == alloy]
        .groupby(["detector", "detector_energy_bin", "bin_low_keV", "bin_high_keV"], as_index=False)[
            "detected_in_detector_bin"
        ]
        .sum()
    )
    detectors = ["medipix3", "eiger2", "timepix3_cdte", "hexitec_proxy"]

    fig, axes = plt.subplots(1, 4, figsize=(15.5, 4.2), sharey=False)
    for ax, detector in zip(axes, detectors):
        data = subset[subset["detector"] == detector].sort_values("detector_energy_bin")
        labels = [f"{lo:.0f}-{hi:.0f}" for lo, hi in zip(data["bin_low_keV"], data["bin_high_keV"])]
        is_proxy = detector == "hexitec_proxy"
        bars = ax.bar(labels, data["detected_in_detector_bin"], color="#9a9a9a" if is_proxy else "#566573")
        if is_proxy:
            for bar in bars:
                bar.set_hatch("///")
                bar.set_edgecolor("black")
        title = DETECTOR_LABELS[detector] + ("\n(proxy: 1 wide bin)" if is_proxy else "")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Energy bin (keV)")
        ax.tick_params(axis="x", labelrotation=45)
        ymax = float(data["detected_in_detector_bin"].max())
        ax.set_ylim(0, ymax * 1.22 if ymax > 0 else 1)
        add_value_labels(ax, "{:,.0f}", pad=2)
    axes[0].set_ylabel("Detected photons")
    fig.suptitle("Energy discrimination example: Alloy 4 after beam hardening")
    fig.tight_layout()
    savefig(fig, "06_energy_bin_discrimination_alloy4.png")


def plot_transport_validation(transport: pd.DataFrame) -> None:
    medipix3 = transport[(transport["detector"] == "medipix3")].sort_values("energy_keV").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(7.6, 4.5))
    x = np.arange(len(medipix3))
    width = 0.34
    ax.bar(
        x - width / 2, medipix3["analytical_detected_counts"], width,
        yerr=medipix3["analytical_detected_counts_se"], capsize=3, label="Analytical", color="#2874a6",
    )
    ax.bar(
        x + width / 2, medipix3["transport_detected_counts"], width,
        yerr=medipix3["transport_detected_counts_se"], capsize=3, label="Allpix transport", color="#c0392b",
    )
    ax.set_xticks(x, [f"{e:.0f} keV" for e in medipix3["energy_keV"]])
    ax.set_ylabel("Detected counts")
    ax.set_title("Transport cross-check: Medipix3 + 5 mm G4_BRASS slab, like-for-like composition\n(error bars: binomial SE)")
    ax.legend(frameon=True)
    for i, row in medipix3.iterrows():
        if row["analytical_detected_counts"] >= 1 and np.isfinite(row["relative_difference_pct"]):
            ax.text(i, max(row["analytical_detected_counts"], row["transport_detected_counts"]) + 8, f"{row['relative_difference_pct']:+.1f}%", ha="center", fontsize=9)
        else:
            ax.text(i, 6, "near zero", ha="center", fontsize=9)
    savefig(fig, "07_transport_cross_check.png")


def plot_eiger2_correction(transport: pd.DataFrame, response: pd.DataFrame) -> None:
    """Explains *why* the analytic shortcut fails for EIGER2, not just *that*
    it fails: top panel is the bare-detector response cliff at its 80 keV
    upper threshold; bottom panel is the resulting correction factor
    (transport / analytical), plotted on the same energy axis so the cliff
    and the correction visibly line up. Replaces an earlier dual-bar chart
    with 14 crowded percent labels, which showed the discrepancy but not its
    mechanism."""
    eiger2_response = response[response["detector"] == "eiger2"].sort_values("energy_keV")
    eiger2_transport = transport[transport["detector"] == "eiger2"].sort_values("energy_keV").copy()
    # Same >=1-expected-count threshold the pipeline already uses for
    # relative_difference_pct: below that, a ratio is statistical noise
    # (e.g. 0/0-type single-digit Poisson counts), not a meaningful value.
    eiger2_transport["correction_factor"] = np.where(
        eiger2_transport["analytical_detected_counts"] >= 1.0,
        eiger2_transport["transport_detected_fraction"] / eiger2_transport["analytical_detected_fraction"],
        np.nan,
    )
    valid = eiger2_transport.dropna(subset=["correction_factor"])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 7.8), sharex=True, gridspec_kw={"height_ratios": [1, 1.2], "hspace": 0.12})

    ax1.errorbar(
        eiger2_response["energy_keV"], eiger2_response["windowed_response"],
        yerr=eiger2_response["windowed_response_se"], marker="o", capsize=2, color="#2874a6",
    )
    ax1.axvline(80, color="#c0392b", ls="--", lw=1.5, label="EIGER2 upper threshold (80 keV)")
    ax1.set_ylabel("Bare-detector\nwindowed response")
    ax1.set_title("Why the analytic shortcut fails above EIGER2's 80 keV threshold")
    ax1.legend(frameon=True, loc="upper right")

    ax2.plot(valid["energy_keV"], valid["correction_factor"], marker="o", color="#c0392b", label="Transport / analytical ratio")
    ax2.axhline(1.0, color="gray", ls=":", lw=1.2, label="No correction needed (ratio = 1)")
    ax2.axvline(80, color="#c0392b", ls="--", lw=1.5)
    ax2.set_ylabel("Correction factor\n(transport / analytical)")
    ax2.set_xlabel("Energy (keV)")
    ax2.legend(frameon=True, loc="upper left")

    savefig(fig, "08_eiger2_transport_correction.png")


def plot_alloy_discrimination(discrimination: pd.DataFrame) -> None:
    """Pairwise material-discrimination CNR per detector: the practical
    inspection question ("can this detector tell alloy A from alloy B apart"),
    as opposed to figure 4/5's "which combo detects the most photons"."""
    order = ["medipix3", "eiger2", "timepix3_cdte", "hexitec_proxy"]
    alloy_order = list(ALLOY_LABELS)
    short_labels = [ALLOY_LABELS[a].split(" ")[1] for a in alloy_order]

    vmax = discrimination["cnr"].max()
    fig, axes = plt.subplots(
        1, len(order), figsize=(5.2 * len(order), 5.0),
        gridspec_kw={"wspace": 0.75},
    )
    fig.subplots_adjust(top=0.82, bottom=0.2)
    for ax, detector in zip(axes, order):
        subset = discrimination[discrimination["detector"] == detector]
        matrix = pd.DataFrame(np.nan, index=alloy_order, columns=alloy_order)
        for _, row in subset.iterrows():
            matrix.loc[row["alloy_a"], row["alloy_b"]] = row["cnr"]
            matrix.loc[row["alloy_b"], row["alloy_a"]] = row["cnr"]

        im = ax.imshow(matrix.to_numpy(), cmap="magma_r", vmin=0, vmax=vmax)
        ax.set_xticks(np.arange(len(alloy_order)), short_labels, rotation=45, ha="right")
        ax.set_yticks(np.arange(len(alloy_order)), short_labels)
        ax.set_title(DETECTOR_LABELS[detector], pad=12)
        for i in range(len(alloy_order)):
            for j in range(len(alloy_order)):
                if i == j:
                    continue
                val = matrix.iloc[i, j]
                ax.text(j, i, f"{val:.0f}", ha="center", va="center", fontsize=8,
                         color="white" if val > vmax * 0.6 else "black")
    fig.colorbar(im, ax=axes, label="CNR (Poisson-limited approximation)", shrink=0.8, pad=0.02)
    fig.suptitle("Alloy Pair Discrimination (CNR) Matrix")
    savefig(fig, "09_alloy_discrimination_cnr.png")


def write_visual_summary(performance: pd.DataFrame, discrimination: pd.DataFrame) -> None:
    real = performance[~performance["proxy_result"]].sort_values("rank_real_photon_counting_detectors")
    ranked_labels = [DETECTOR_LABELS.get(d, d) for d in real["detector"]]
    ranking_text = " > ".join(ranked_labels)
    second_vs_third = (
        "EIGER2's position depends on the G4_BRASS-calibrated scatter/window correction (figure 8); "
        "it is the only detector whose numbers include the measured scatter boost, so its margin over "
        "the uncorrected chips is partly a method artifact -- see the report's scatter-consistency estimate."
        if len(ranked_labels) >= 3
        else ""
    )
    real_disc = discrimination[discrimination["detector"].isin(real["detector"])]
    hardest = real_disc.loc[real_disc["cnr"].idxmin()]
    easiest = real_disc.loc[real_disc["cnr"].idxmax()]
    hardest_pair = f"{ALLOY_LABELS[hardest['alloy_a']]} vs {ALLOY_LABELS[hardest['alloy_b']]}"
    easiest_pair = f"{ALLOY_LABELS[easiest['alloy_a']]} vs {ALLOY_LABELS[easiest['alloy_b']]}"

    lines = [
        "# Presentation Figure Guide",
        "",
        "Use these figures instead of the older crowded plots when presenting the experiment.",
        "",
        "| Figure | What it proves | File |",
        "| --- | --- | --- |",
        "| 1 | The incident source is a 150 kVp filtered tungsten spectrum, discretised into 14 weighted energy bins. | `presentation_figures/01_xray_source_model.png` |",
        "| 2 | Low-energy photons are almost fully removed by 5 mm copper alloys; useful signal comes from the hardened high-energy tail. | `presentation_figures/02_alloy_transmission_heatmap.png` |",
        "| 3 | Bare-detector response is energy dependent; each chip's upper window edge (EIGER2 80 keV, Medipix3 & Timepix3 120 keV) decides how much of the hardened beam it can count. | `presentation_figures/03_cdte_detector_response.png` |",
        "| 4 | The detector-alloy matrix shows the final (EIGER2-corrected) result for all 20 combinations. | `presentation_figures/04_detector_alloy_matrix_heatmap.png` |",
        f"| 5 | Among real photon-counting detectors, ranked by mean detected signal: {ranking_text}. | `presentation_figures/05_real_detector_performance.png` |",
        "| 6 | Energy-bin counts show how beam-hardened photons fall into detector discrimination windows (EIGER2 bars include its transport correction). | `presentation_figures/06_energy_bin_discrimination_alloy4.png` |",
        "| 7 | Compared like-for-like against the true G4_BRASS composition (9.07% Pb), the full transport simulation exceeds the analytic shortcut by +69%/+103% for Medipix3 at 80/120 keV -- the near-contact slab geometry lets Compton-scattered photons reach the detector; 40 keV is effectively zero counts either way. | `presentation_figures/07_transport_cross_check.png` |",
        "| 8 | EIGER2 amplifies that scatter effect by an order of magnitude: its like-for-like transport excess reaches ~+845% at 120 keV (peak ~+880% at 90 keV), because Compton-downscattered photons re-enter its sub-80 keV window. All five EIGER2 alloys use this G4_BRASS-calibrated correction (`g4brass_calibrated_correction` in the tables); the transport run itself measured G4_BRASS, not C36000, so it is calibration data, not a production number. | `presentation_figures/08_eiger2_transport_correction.png` |",
        f"| 9 | Detected-count ranking isn't the same as material discrimination: {hardest_pair} are nearly indistinguishable (lowest CNR) with every detector, while {easiest_pair} is the easiest pair to tell apart. | `presentation_figures/09_alloy_discrimination_cnr.png` |",
        "",
        "Main presentation statement:",
        "",
        f"> The alloy strongly hardens the spectrum, so the detector that keeps useful response in the 80-120 keV range performs best. Ranked by mean detected signal: {ranking_text}. HEXITEC remains a proxy spectroscopic result, excluded from this ranking. "
        f"{second_vs_third} Raw detected-photon counts (figures 4-5) and pairwise material discrimination (figure 9) are "
        f"different questions -- the best detector for one is not automatically the best for the other.",
        "",
        "Known limitations:",
        "",
        "- All five EIGER2 alloys use a correction factor calibrated on G4_BRASS transport data, not "
        "independently validated per alloy -- see `detection_methods_used` in `performance_evaluation.csv` and "
        "`analysis/scripts/material_penetration_experiment.py:build_eiger2_alloy2_correction` for the derivation and its assumptions. "
        "The other three detectors receive no scatter correction despite a measured +59-103% transport excess at "
        "80-120 keV, so cross-detector margins involving EIGER2 are partly a method artifact.",
        "- CNR in figure 9 and `alloy_discrimination_cnr.csv` is a Poisson shot-noise-limited approximation "
        "(electronic noise not included), so it's an upper bound on achievable discrimination, not a full "
        "detector-noise model.",
        "- Error bars throughout are binomial standard errors from the underlying 10k-event Monte Carlo runs, "
        "propagated with energy bins treated as independent -- a labeled approximation, not an exact covariance "
        "propagation (see `binomial_se()` in `analysis/scripts/material_penetration_experiment.py`).",
        "",
    ]
    (BASE / "presentation_figure_guide.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    weights = pd.read_csv(SPECTRUM)
    spectrum_summary = pd.read_csv(BASE / "spectrum_summary.csv")
    attenuation = pd.read_csv(BASE / "alloy_attenuation.csv")
    response = pd.read_csv(BASE / "detector_response.csv")
    combined = pd.read_csv(BASE / "combined_results.csv")
    performance = pd.read_csv(BASE / "performance_evaluation.csv")
    bin_summary = pd.read_csv(BASE / "per_detector_energy_bin_results.csv")
    transport = pd.read_csv(BASE / "transport_validation.csv")
    discrimination = pd.read_csv(BASE / "alloy_discrimination_cnr.csv")

    plot_xray_source(weights, spectrum_summary)
    plot_transmission_heatmap(attenuation)
    plot_detector_response(response)
    plot_matrix_heatmap(combined)
    plot_real_performance(performance)
    plot_energy_bins(bin_summary)
    plot_transport_validation(transport)
    plot_eiger2_correction(transport, response)
    plot_alloy_discrimination(discrimination)
    write_visual_summary(performance, discrimination)
    print(f"Wrote presentation figures to {OUT}")


if __name__ == "__main__":
    main()
