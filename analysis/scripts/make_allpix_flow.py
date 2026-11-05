#!/usr/bin/env python3
"""Build a defensible flow diagram of the Allpix2/Geant4 simulation pipeline."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = Path("/home/victor-pc/itek/senstech-simulation/analysis/reports/assets")
OUT.mkdir(parents=True, exist_ok=True)

INK, SUB, SURF = "#0b0b0b", "#43433f", "#fcfcfb"
# stage: (title, module, physics line, fill, edge)
STAGES = [
    ("X-ray photon", "beam source", "one energy at a time,\n1 mm pencil beam", "#eef1f4", "#98a4b0"),
    ("Transport &\ndeposit", "DepositionGeant4", "Geant4 QGSP_BERT:\nphotoelectric / Compton /\nfluorescence  →  e–h pairs\n(4.43 eV each)", "#dce9f9", "#2a78d6"),
    ("Drift &\ndiffusion", "ElectricFieldReader\n+ GenericPropagation", "bias → linear field;\nJacoboni mobility, 293 K\n→ charge sharing", "#d7efe4", "#1baf7a"),
    ("Pixel readout", "SimpleTransfer\n+ DefaultDigitizer", "collect charge; add noise;\ncount if over threshold\n(each chip's identity)", "#fbe4d6", "#eb6834"),
    ("ROOT output", "DetectorHistogrammer", "detected events +\ndeposited-energy spectrum", "#e7e3f3", "#4a3aa7"),
    ("Analysis →\nN_sim", "hybrid bridge", "response R(E) ×\nanalytic transmission T(E),\nsum over spectrum", "#e9e9e5", "#5b5b57"),
]

fig, ax = plt.subplots(figsize=(15, 4.6))
fig.patch.set_facecolor(SURF); ax.set_facecolor(SURF)
ax.set_xlim(0, len(STAGES) * 2.5); ax.set_ylim(0, 4.6); ax.axis("off")
bw, bh, y0 = 2.05, 3.0, 0.7
for i, (title, mod, phys, fill, edge) in enumerate(STAGES):
    x = i * 2.5 + 0.12
    box = FancyBboxPatch((x, y0), bw, bh, boxstyle="round,pad=0.04,rounding_size=0.12",
                         linewidth=2, edgecolor=edge, facecolor=fill)
    ax.add_patch(box)
    cx = x + bw / 2
    ax.text(cx, y0 + bh - 0.42, title, ha="center", va="center", fontsize=13, fontweight="bold", color=INK)
    ax.text(cx, y0 + bh - 1.06, mod, ha="center", va="center", fontsize=9.5, style="italic",
            family="monospace", color=edge)
    ax.text(cx, y0 + 0.95, phys, ha="center", va="center", fontsize=9, color=SUB)
    if i < len(STAGES) - 1:
        ax.add_patch(FancyArrowPatch((x + bw + 0.02, y0 + bh / 2), (x + bw + 0.43, y0 + bh / 2),
                                     arrowstyle="-|>", mutation_scale=18, linewidth=2, color="#7a7a75"))
# phase band labels
ax.text(0.12 + bw / 2, 4.15, "PHYSICS  (what really happens)", ha="left", fontsize=10, color="#2a78d6", fontweight="bold")
ax.text(len(STAGES) * 2.5 - 0.3, 4.15, "→  ONE NUMBER PER DETECTOR × ALLOY", ha="right", fontsize=10, color=INK, fontweight="bold")
ax.text(len(STAGES) * 1.25, 0.28, "Every box is a real physical stage AND a configuration module — the pipeline you can walk and defend.",
        ha="center", fontsize=10, style="italic", color=SUB)
fig.tight_layout()
fig.savefig(OUT / "allpix_flow.png", dpi=190, bbox_inches="tight")
print("saved", OUT / "allpix_flow.png")
