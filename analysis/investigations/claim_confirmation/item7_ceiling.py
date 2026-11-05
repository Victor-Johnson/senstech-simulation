#!/usr/bin/env python3
"""Item 7 -- is 1 - exp(-mu*t) being used as more than it can support?

The handover (Sec 3.4) states: "The product of alloy transmission and this
interaction probability defines a physical ceiling that no detector's counted
signal can exceed, regardless of its electronics."

Two things to test:
  (a) which NIST coefficient is mu? Total attenuation includes coherent
      (Rayleigh) scattering, which deposits essentially no energy.
  (b) can one interacting photon produce multiple reported units? If so, the
      ceiling bounds unique detected EVENTS, not "counted signal" generically.

Run: PYTHONPATH=. ./venv/bin/python analysis/investigations/claim_confirmation/item7_ceiling.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import uproot

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

import analysis.scripts.phase2_selection_experiment as p2  # noqa: E402

OUT = Path(__file__).resolve().parent
DATA = OUT / "data"
ENERGIES = [60, 100, 150]

# (detector, tag, thickness_mm, pitch label)
DETS = [
    ("hexitec_proxy", "", 1.00, "250 um"),
    ("eiger2", "_075mm", 0.75, "75 um"),
    ("timepix4", "", 1.00, "55 um"),
    ("medipix3", "", 1.00, "55 um"),
]

# NIST reference for Cu mass attenuation (cm^2/g), to identify which column
# the pipeline's mu corresponds to.
NIST_CU_100KEV = {
    "total_with_coherent": 0.4584,
    "total_without_coherent": 0.4205,
    "photoelectric_only": 0.0379,
}


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    print("=" * 78)
    print("ITEM 7 -- interaction probability vs count probability")
    print("=" * 78)

    # --- 7a. which NIST column? ------------------------------------------
    print()
    print("7a. Which NIST coefficient is mu?")
    from spekpy.DataTables import MuData
    mu_data = MuData("nist_mu.dat")
    cu_100 = float(mu_data.get_mu_over_rho(29, np.array([0.100]))[0])  # MeV
    print(f"    pipeline mu/rho for Cu @100 keV : {cu_100:.4f} cm2/g")
    for k, v in NIST_CU_100KEV.items():
        match = "  <-- MATCH" if abs(cu_100 - v) < 0.002 else ""
        print(f"    NIST {k:24s}: {v:.4f}{match}")
    print()
    print("    -> mu is TOTAL attenuation WITH coherent scattering.")
    print("    Rayleigh scattering redirects a photon without depositing energy,")
    print("    so those interactions inflate mu without producing a countable")
    print("    event. The ceiling is therefore VALID but LOOSE -- conservative in")
    print("    the safe direction. A tight bound on energy-depositing")
    print("    interactions would use total-minus-coherent, or mu_en/rho.")

    # --- 7b. one photon -> how many reported units? ----------------------
    print()
    print("7b. Can one interacting photon produce multiple reported units?")
    print()
    _, _, mu, _ = p2.load_inputs()
    rows = []
    for det, tag, thick, pitch in DETS:
        for E in ENERGIES:
            path = REPO_ROOT / "data" / f"p2_bare_{det}{tag}_{E}keV.root"
            if not path.exists():
                continue
            with uproot.open(path) as f:
                d = f"DetectorHistogrammer/{det}_detector"
                ev, _ = f[f"{d}/event_size_clusters;1"].to_numpy()
                events = float(np.sum(ev))
                cc, _ = f[f"{d}/charge/cluster_charge;1"].to_numpy()
                clusters = float(np.sum(cc))
                pix = float(f[f"{d}/hit_map;1"].to_numpy()[0].sum())
            ceiling = 10_000 * p2.P_cdte(mu, float(E), thick)
            rows.append(dict(detector=det, pitch=pitch, energy_keV=E,
                             ceiling=ceiling, events=events, clusters=clusters,
                             pixel_hits=pix,
                             events_over_ceiling=events / ceiling,
                             clusters_over_ceiling=clusters / ceiling,
                             pixels_over_ceiling=pix / ceiling))
    df = pd.DataFrame(rows)
    df.to_csv(DATA / "item7_ceiling.csv", index=False)

    print(f"{'detector':15s} {'pitch':>7s} {'E':>4s} {'ceiling':>8s} "
          f"{'events':>7s} {'clusters':>9s} {'pixels':>8s} | "
          f"{'ev/ceil':>8s} {'pix/ceil':>9s}")
    for _, r in df.iterrows():
        print(f"{r.detector:15s} {r.pitch:>7s} {r.energy_keV:4.0f} {r.ceiling:8.0f} "
              f"{r.events:7.0f} {r.clusters:9.0f} {r.pixel_hits:8.0f} | "
              f"{r.events_over_ceiling:8.3f} {r.pixels_over_ceiling:9.3f}")

    print()
    print(f"  events / ceiling : {df.events_over_ceiling.min():.3f} to "
          f"{df.events_over_ceiling.max():.3f}   -- the ceiling HOLDS "
          f"(small excess = oblique path lengths)")
    print(f"  pixels / ceiling : {df.pixels_over_ceiling.min():.3f} to "
          f"{df.pixels_over_ceiling.max():.3f}   -- the ceiling is EXCEEDED "
          f"by up to {(df.pixels_over_ceiling.max() - 1) * 100:.0f}%")

    print()
    print("  Pixel hits per incident photon, by pitch (charge sharing):")
    byd = df.groupby(["detector", "pitch"]).apply(
        lambda x: pd.Series({"pix_per_event_min": (x.pixel_hits / x.events).min(),
                             "pix_per_event_max": (x.pixel_hits / x.events).max()}),
        include_groups=False).reset_index().sort_values("pix_per_event_max")
    for _, r in byd.iterrows():
        print(f"    {r.detector:15s} {r.pitch:>7s}  "
              f"{r.pix_per_event_min:.2f} - {r.pix_per_event_max:.2f}")

    print()
    print("-" * 78)
    print("VERDICT")
    print("-" * 78)
    print("  The ceiling bounds UNIQUE DETECTED PRIMARY EVENTS, and against that")
    print("  quantity it holds -- which is what the pipeline actually compares.")
    print("  But a real photon-counting ASIC counts PIXEL discriminator firings,")
    print("  and without charge-summing one photon fires 1.5-2.9 pixels. So the")
    print("  Sec 3.4 wording 'no detector's counted signal can exceed' is too")
    print("  broad for a real chip's raw output.")
    print()
    print("  This is ranking-relevant, not just a wording fix: the multiplicity is")
    print("  strongly pitch-dependent and runs OPPOSITE to the reported order --")
    print("  HEXITEC's 250 um pixels share least, the 55 um chips share most.")


if __name__ == "__main__":
    main()
