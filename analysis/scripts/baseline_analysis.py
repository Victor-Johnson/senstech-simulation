import uproot
import numpy as np
import matplotlib.pyplot as plt
import os
os.environ["QT_QPA_PLATFORM"] = "xcb"

# ── File paths ────────────────────────────────────────────────────────────
BASE = "/home/sally/Desktop/itek/senstech-detector-sim"

SILICON_PATH = "/home/sally/Desktop/itek/senstech-detector-sim/data/modules.root"
CDTE_PATH    = "/home/sally/Desktop/itek/senstech-detector-sim/data/modules.root"

# ── Load ROOT files ───────────────────────────────────────────────────────
print("Loading ROOT files...")
silicon = uproot.open(SILICON_PATH)
cdte    = uproot.open(CDTE_PATH)
print("Loaded successfully.")

# ── Charge spectrum comparison ────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

datasets = [
    (silicon, "Silicon 300μm",  "#0D9488", 1000),
    (cdte,    "CdTe 1000μm",    "#0369A1", 5000),
]

for ax, (f, label, color, n_events) in zip(axes, datasets):
    pixel_charge = f["DetectorHistogrammer/cdte_detector/charge/pixel_charge;1"]
    vals = pixel_charge.to_numpy()
    ax.bar(vals[1][:-1], vals[0],
           width=np.diff(vals[1]),
           color=color, alpha=0.8)
    ax.set_title(f"Charge Spectrum — {label}")
    ax.set_xlabel("Pixel Charge (electrons)")
    ax.set_ylabel("Counts")
    total_hits = vals[0].sum()
    efficiency = (total_hits / n_events) * 100
    ax.text(0.97, 0.95,
            f"Hits: {total_hits:.0f}\nEfficiency: {efficiency:.1f}%",
            transform=ax.transAxes,
            ha='right', va='top', fontsize=11, color=color,
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

plt.suptitle("Silicon vs CdTe — Baseline Comparison @ 60keV",
             fontsize=14, fontweight='bold')
plt.tight_layout()
output_path = os.path.join(BASE, "analysis/notebooks/baseline_comparison.png")
plt.savefig(output_path, dpi=150)
plt.show()
print(f"Plot saved to {output_path}")

# ── Hit map side by side ──────────────────────────────────────────────────
fig2, axes2 = plt.subplots(1, 2, figsize=(12, 5))

for ax, (f, label, color, _) in zip(axes2, datasets):
    hit_map = f["DetectorHistogrammer/medipix/hit_map;1"]
    hm = hit_map.to_numpy()
    im = ax.imshow(hm[0], cmap="hot", origin="lower")
    plt.colorbar(im, ax=ax, label="Hit count")
    ax.set_title(f"Hit Map — {label}")
    ax.set_xlabel("Pixel X")
    ax.set_ylabel("Pixel Y")

plt.suptitle("Pixel Hit Maps — Silicon vs CdTe @ 60keV",
             fontsize=14, fontweight='bold')
plt.tight_layout()
hitmap_path = os.path.join(BASE, "analysis/notebooks/hitmap_comparison.png")
plt.savefig(hitmap_path, dpi=150)
plt.show()
print(f"Hit map saved to {hitmap_path}")

# ── Summary stats ─────────────────────────────────────────────────────────
print("\n── Baseline Comparison Summary ──────────────────────────")
for f, label, color, n_events in datasets:
    vals  = f["DetectorHistogrammer/medipix/charge/pixel_charge;1"].to_numpy()
    hits  = vals[0].sum()
    eff   = (hits / n_events) * 100
    mean_charge = np.average(vals[1][:-1], weights=vals[0] + 1e-9)

    cs_vals = f["DetectorHistogrammer/medipix/cluster_size/cluster_size;1"].to_numpy()
    mean_cluster = np.average(cs_vals[1][:-1], weights=cs_vals[0] + 1e-9)

    print(f"\n  {label}:")
    print(f"    Events simulated:     {n_events}")
    print(f"    Pixel hits detected:  {hits:.0f}")
    print(f"    Detection efficiency: {eff:.1f}%")
    print(f"    Mean pixel charge:    {mean_charge:.0f} electrons")
    print(f"    Mean cluster size:    {mean_cluster:.2f} pixels")
print("\n─────────────────────────────────────────────────────────")