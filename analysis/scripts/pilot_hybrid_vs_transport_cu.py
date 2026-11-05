#!/usr/bin/env python3
"""Pure-Cu (C11000 / alloy1) cross-check: hybrid vs full-transport.

Now computes BOTH:
  * no-window (intrinsic) fractions  -- isolates raw slab scatter, and
  * WINDOWED (production-consistent) fractions -- applies each detector's
    energy window to the transport clusters exactly as the ranking pipeline
    does to the bare detectors, so the hybrid baseline matches the ranking
    (critical for EIGER2, whose 4-80 keV window is the only one that bites the
    hardened beam) AND the transport captures downscattered photons that refill
    that window.

  hybrid_win(E)    = T_Cu(E) * bare_windowed_response(E)          [production]
  transport_win(E) = intrinsic_transport(E) * window_acceptance_transport(E)

window_acceptance_transport is built from the transport cluster_charge spectrum
via the identical logic in read_detector_response (charge*4.43eV in [lower,upper]).
"""
from pathlib import Path
import numpy as np
import pandas as pd

import analysis.scripts.material_penetration_experiment as m

ROOT = Path("/home/victor-pc/itek/senstech-simulation")
BASE = ROOT / "analysis/results/material_penetration_uniform"
DATA = ROOT / "data"
N0 = 1_000_000

spectrum = pd.read_csv(ROOT / "spectra/150kvp_weights.csv")
weights = dict(zip(spectrum["energy_keV"].astype(float), spectrum["weight"]))
att = pd.read_csv(BASE / "alloy_attenuation.csv")
cu_T = att[att["alloy"] == "alloy1"].set_index("energy_keV")["transmission"].to_dict()
resp = pd.read_csv(BASE / "detector_response.csv")
manifest = m.load_manifest(DATA / "material_penetration_uniform_run_manifest.csv")


def transport_fractions(root_path: Path, det, events: int) -> tuple[float, float]:
    """Return (intrinsic_fraction, windowed_fraction) for a transport ROOT,
    replicating read_detector_response's window logic exactly."""
    counts, charge_ke = m.read_cluster_charge(root_path, det.root_detector)
    cluster_count = float(np.sum(counts))
    detected_event_count = m.read_detected_event_count(root_path, det.root_detector)
    charge_energy_keV = charge_ke * m.EPSILON_CDTE_EV
    window_count = 0.0
    for bin_index, low, high in m.detector_bin_ranges(det):
        if bin_index == det.bins:
            in_bin = (charge_energy_keV >= low) & (charge_energy_keV <= high)
        else:
            in_bin = (charge_energy_keV >= low) & (charge_energy_keV < high)
        window_count += float(np.sum(counts[in_bin]))
    window_acceptance = window_count / cluster_count if cluster_count > 0 else 0.0
    intrinsic = min(detected_event_count / events, 1.0)
    windowed = min(intrinsic * window_acceptance, intrinsic)
    return intrinsic, windowed


rows = []
for det in m.DETECTORS:
    ridx = resp[resp["detector"] == det.key].set_index("energy_keV")
    for E in sorted(weights):
        events = m.get_events(manifest, "transport", det.key, E, 10000)
        rpath = DATA / f"mpu_transport_{det.key}_alloy1_{E:.0f}keV.root"
        if not rpath.exists():
            continue
        t_intr, t_win = transport_fractions(rpath, det, events)
        bare_intr = float(ridx.loc[E, "intrinsic_response"])
        bare_win = float(ridx.loc[E, "windowed_response"])
        h_intr = cu_T[E] * bare_intr
        h_win = cu_T[E] * bare_win
        w = weights[E]
        rows.append({
            "detector": det.key, "energy_keV": E, "weight": w, "T_Cu": cu_T[E],
            # no-window (raw scatter)
            "hybrid_fraction": h_intr, "transport_fraction": t_intr,
            "hybrid_counts": N0 * w * h_intr, "transport_counts": N0 * w * t_intr,
            "delta_pct": 100 * (t_intr - h_intr) / h_intr if h_intr > 1e-9 else np.nan,
            # windowed (production-consistent)
            "hybrid_win_fraction": h_win, "transport_win_fraction": t_win,
            "hybrid_win_counts": N0 * w * h_win, "transport_win_counts": N0 * w * t_win,
            "delta_win_pct": 100 * (t_win - h_win) / h_win if h_win > 1e-9 else np.nan,
        })

df = pd.DataFrame(rows)
df.to_csv(BASE / "pilot_cu_hybrid_vs_transport.csv", index=False)

lbl = {"medipix3": "Medipix3", "eiger2": "EIGER2", "hexitec_proxy": "HEXITEC proxy", "timepix3_cdte": "Timepix3"}
print("=" * 86)
print("PURE-Cu HYBRID vs TRANSPORT -- WINDOWED (production-consistent) vs no-window")
print("=" * 86)
print(f"{'detector':15}{'hyb(win)':>10}{'tr(win)':>10}{'build(win)':>11}   |  {'hyb(raw)':>9}{'build(raw)':>11}")
for det in m.DETECTORS:
    d = df[df.detector == det.key]
    if d.empty:
        continue
    hw, tw = d.hybrid_win_counts.sum(), d.transport_win_counts.sum()
    hr, tr = d.hybrid_counts.sum(), d.transport_counts.sum()
    print(f"{lbl[det.key]:15}{hw:>10,.0f}{tw:>10,.0f}{tw/hw:>10.2f}x   |  {hr:>9,.0f}{tr/hr:>10.2f}x")

print("\nEIGER2 note: hyb(win) should now match the ranking's pure-Cu number (~6,259).")

# ---- windowed figure (production-consistent) ----
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
order = ["medipix3", "timepix3_cdte", "eiger2", "hexitec_proxy"]
tot_h = df.groupby("detector")["hybrid_win_counts"].sum()
tot_t = df.groupby("detector")["transport_win_counts"].sum()
x = np.arange(len(order))
fig, ax = plt.subplots(figsize=(9, 5))
ax.bar(x - 0.2, [tot_h[k] for k in order], 0.4, label="Hybrid (windowed = production)", color="#b9c6d6")
ax.bar(x + 0.2, [tot_t[k] for k in order], 0.4, label="Full transport (windowed, incl. scatter)", color="#2f7f74")
for xi, k in enumerate(order):
    ax.text(xi + 0.2, tot_t[k], f"{tot_t[k]/tot_h[k]:.2f}x", ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.text(xi - 0.2, tot_h[k], f"{tot_h[k]:,.0f}", ha="center", va="bottom", fontsize=8)
ax.set_xticks(x, [lbl[k] for k in order])
ax.set_ylabel("Pure-Cu detected counts (N0=1e6)")
ax.set_title("Pure-Cu hybrid vs transport -- WINDOWED (production-consistent)\n"
             "EIGER2's 4-80 keV window applied; its buildup is highest as downscatter refills the window")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(BASE / "pilot_cu_hybrid_vs_transport.png", dpi=170)
print("Saved windowed figure: pilot_cu_hybrid_vs_transport.png")
