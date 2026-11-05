#!/usr/bin/env python3
"""Item 2 -- CdTe charge transport: does the silicon mobility model matter?

What the published campaign actually ran: mobility_model = "jacoboni" in 566
occurrences with zero alternatives -- the Jacoboni-Canali parameterisation fitted
to SILICON, applied unchanged to every CdTe sensor. No trapping, no
recombination, linear field. Hole trapping is CdTe's dominant real-world
artefact and is absent from every published number.

Allpix v3.2.0 (confirmed in-container) offers only silicon-fitted mobility
parameterisations by name, but DOES accept mobility_model="constant" with
explicit values -- which is the one route to CdTe-appropriate transport.

CdTe literature values used here (Owens & Peacock 2004, already reference [6] of
the handover report):
    mu_e = 1100 cm^2/Vs   vs silicon's ~1450
    mu_h =  100 cm^2/Vs   vs silicon's ~505   <- the 5x difference that matters
    tau_e = 3000 ns, tau_h = 500 ns           <- trapping, previously absent

Compares the three quantities the checklist asks for -- count probability,
collected charge, cluster size -- not just the final total.

Run: PYTHONPATH=. ./venv/bin/python analysis/investigations/claim_confirmation/item2_cdte_transport.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import uproot

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

OUT = Path(__file__).resolve().parent
DATA = OUT / "data"
EPS = 4.43  # eV per e-h pair in CdTe
ENERGIES = [80, 100, 150]

# (detector key, silicon-baseline tag, CdTe-transport tag)
# EIGER2 is compared at a MATCHED 0.75 mm, because its untagged 1 mm runs are the
# known-corrupt set -- comparing against those would confound transport with a
# broken configuration.
# Allpix propagates ELECTRONS ONLY by default (propagate_holes defaults false).
# So the "_cdte" arm changes electron mobility and adds trapping, but hole
# mobility and hole trapping cannot influence it at all -- by construction.
# The "_cdteh" arm additionally sets propagate_holes = true, which is the only
# configuration in which CdTe's dominant artefact (slow, heavily-trapped holes)
# can actually express itself. Both arms are reported.
PAIRS = [
    ("medipix3", "", "_cdte"),
    ("medipix4", "", "_cdte"),
    ("timepix3_cdte", "", "_cdte"),
    ("timepix4", "", "_cdte"),
    ("hexitec_proxy", "", "_cdte"),
    ("eiger2", "_075mm", "_cdte075"),
]

PAIRS_HOLES = [
    ("medipix3", "", "_cdteh"),
    ("medipix4", "", "_cdteh"),
    ("timepix3_cdte", "", "_cdteh"),
    ("timepix4", "", "_cdteh"),
    ("hexitec_proxy", "", "_cdteh"),
    ("eiger2", "_075mm", "_cdteh075"),   # matched 0.75 mm -- NOT the 1 mm default
]


def read_metrics(det: str, tag: str, energy: int) -> dict | None:
    path = REPO_ROOT / "data" / f"p2_bare_{det}{tag}_{energy}keV.root"
    if not path.exists():
        return None
    with uproot.open(path) as f:
        d = f"DetectorHistogrammer/{det}_detector"
        ev, _ = f[f"{d}/event_size_clusters;1"].to_numpy()
        detected = float(np.sum(ev))

        cc_obj = f[f"{d}/charge/cluster_charge;1"]
        cc, edges = cc_obj.to_numpy()
        centers = (edges[:-1] + edges[1:]) / 2.0
        clusters = float(np.sum(cc))
        mean_charge_ke = float(np.average(centers, weights=cc)) if clusters else np.nan

        cs_obj = f[f"{d}/cluster_size/cluster_size;1"]
        cs, cs_edges = cs_obj.to_numpy()
        cs_centers = (cs_edges[:-1] + cs_edges[1:]) / 2.0
        mean_cluster_size = (float(np.average(cs_centers, weights=cs))
                             if cs.sum() else np.nan)

        sc_obj = f[f"{d}/charge/seed_charge;1"]
        sc, sc_edges = sc_obj.to_numpy()
        sc_centers = (sc_edges[:-1] + sc_edges[1:]) / 2.0
        mean_seed_ke = float(np.average(sc_centers, weights=sc)) if sc.sum() else np.nan

    return {
        "count_probability": detected / 10_000.0,
        "mean_cluster_charge_ke": mean_charge_ke,
        "mean_cluster_charge_keV": mean_charge_ke * EPS,
        "mean_seed_charge_ke": mean_seed_ke,
        "seed_fraction": mean_seed_ke / mean_charge_ke if mean_charge_ke else np.nan,
        "mean_cluster_size_px": mean_cluster_size,
        "clusters": clusters,
    }


def build(pairs) -> pd.DataFrame:
    rows = []
    for det, si_tag, cdte_tag in pairs:
        for E in ENERGIES:
            si = read_metrics(det, si_tag, E)
            cd = read_metrics(det, cdte_tag, E)
            if si is None or cd is None:
                print(f"  SKIP {det} {E} keV (missing: "
                      f"{'silicon' if si is None else ''}{'cdte' if cd is None else ''})")
                continue
            row = {"detector": det, "energy_keV": E,
                   "si_tag": si_tag or "(untagged)", "cdte_tag": cdte_tag}
            for k in si:
                row[f"si_{k}"] = si[k]
                row[f"cdte_{k}"] = cd[k]
                row[f"ratio_{k}"] = cd[k] / si[k] if si[k] else np.nan
            rows.append(row)

    return pd.DataFrame(rows)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    df = build(PAIRS)
    df["arm"] = "electrons_only"
    dfh = build(PAIRS_HOLES)
    dfh["arm"] = "electrons_and_holes"
    pd.concat([df, dfh], ignore_index=True).to_csv(
        DATA / "item2_cdte_transport.csv", index=False)

    print("=" * 78)
    print("ITEM 2 -- silicon (jacoboni, no trapping) vs CdTe transport")
    print("  CdTe: mu_e=1100, mu_h=100 cm2/Vs; tau_e=3000ns, tau_h=500ns")
    print("=" * 78)
    print()
    print("COUNT PROBABILITY (detected events / 10,000 fired)")
    print(f"{'detector':16s} {'E':>4s} {'silicon':>9s} {'CdTe':>9s} {'ratio':>8s} {'change':>9s}")
    for _, r in df.iterrows():
        ch = (r.ratio_count_probability - 1) * 100
        print(f"{r.detector:16s} {r.energy_keV:4.0f} {r.si_count_probability:9.4f} "
              f"{r.cdte_count_probability:9.4f} {r.ratio_count_probability:8.4f} "
              f"{ch:+8.2f}%")

    print()
    print("MEAN COLLECTED CLUSTER CHARGE (keV)")
    print(f"{'detector':16s} {'E':>4s} {'silicon':>9s} {'CdTe':>9s} {'ratio':>8s}")
    for _, r in df.iterrows():
        print(f"{r.detector:16s} {r.energy_keV:4.0f} {r.si_mean_cluster_charge_keV:9.3f} "
              f"{r.cdte_mean_cluster_charge_keV:9.3f} {r.ratio_mean_cluster_charge_keV:8.4f}")

    print()
    print("MEAN CLUSTER SIZE (pixels)  +  seed-charge fraction (charge-sharing proxy)")
    print(f"{'detector':16s} {'E':>4s} {'si size':>8s} {'CdTe sz':>8s} {'ratio':>7s} "
          f"{'si seed':>8s} {'CdTe seed':>10s}")
    for _, r in df.iterrows():
        print(f"{r.detector:16s} {r.energy_keV:4.0f} {r.si_mean_cluster_size_px:8.4f} "
              f"{r.cdte_mean_cluster_size_px:8.4f} {r.ratio_mean_cluster_size_px:7.4f} "
              f"{r.si_seed_fraction:8.4f} {r.cdte_seed_fraction:10.4f}")

    print()
    print("-" * 78)
    print("VERDICT")
    print("-" * 78)
    cp = df.ratio_count_probability
    print(f"  count probability   : ratio {cp.min():.4f} to {cp.max():.4f}  "
          f"(max |change| {abs(cp - 1).max() * 100:.2f}%)")
    q = df.ratio_mean_cluster_charge_keV
    print(f"  collected charge    : ratio {q.min():.4f} to {q.max():.4f}  "
          f"(max |change| {abs(q - 1).max() * 100:.2f}%)")
    z = df.ratio_mean_cluster_size_px
    print(f"  cluster size        : ratio {z.min():.4f} to {z.max():.4f}  "
          f"(max |change| {abs(z - 1).max() * 100:.2f}%)")

    # Does the ranking survive? Compare detector ordering at each energy.
    print()
    print("  RANKING CHECK -- detector order by count probability, per energy:")
    flipped = False
    for E in ENERGIES:
        sub = df[df.energy_keV == E]
        si_order = list(sub.sort_values("si_count_probability", ascending=False).detector)
        cd_order = list(sub.sort_values("cdte_count_probability", ascending=False).detector)
        same = si_order == cd_order
        flipped |= not same
        print(f"    {E} keV: {'UNCHANGED' if same else 'CHANGED'}")
        if not same:
            print(f"        silicon: {' > '.join(si_order)}")
            print(f"        CdTe   : {' > '.join(cd_order)}")
    print()
    print(f"  ranking altered by transport model at any energy: {flipped}")
    print()
    print("=" * 78)
    print("ARM 2 -- same CdTe parameters, but WITH hole propagation enabled")
    print("  (propagate_holes defaults to FALSE, so arm 1 could not see hole")
    print("   mobility or hole trapping at all)")
    print("=" * 78)
    print()
    print(f"{'detector':16s} {'E':>4s} {'count prob':>11s} {'charge keV':>11s} "
          f"{'cluster px':>11s}")
    print(f"{'':16s} {'':>4s} {'ratio':>11s} {'ratio':>11s} {'ratio':>11s}")
    for _, r in dfh.iterrows():
        print(f"{r.detector:16s} {r.energy_keV:4.0f} "
              f"{r.ratio_count_probability:11.4f} "
              f"{r.ratio_mean_cluster_charge_keV:11.4f} "
              f"{r.ratio_mean_cluster_size_px:11.4f}")
    print()
    for nm, col in (("count probability", "ratio_count_probability"),
                    ("collected charge", "ratio_mean_cluster_charge_keV"),
                    ("cluster size", "ratio_mean_cluster_size_px")):
        v = dfh[col]
        print(f"  {nm:20s}: ratio {v.min():.4f} to {v.max():.4f}  "
              f"(max |change| {abs(v - 1).max() * 100:.2f}%)")
    print()
    flipped_h = False
    for E in ENERGIES:
        sub = dfh[dfh.energy_keV == E]
        si = list(sub.sort_values("si_count_probability", ascending=False).detector)
        cd = list(sub.sort_values("cdte_count_probability", ascending=False).detector)
        if si != cd:
            flipped_h = True
            print(f"    {E} keV ranking CHANGED:")
            print(f"        silicon: {' > '.join(si)}")
            print(f"        CdTe+h : {' > '.join(cd)}")
    print(f"  ranking altered with holes propagated: {flipped_h}")
    print()
    print(f"Wrote {DATA}/item2_cdte_transport.csv")


if __name__ == "__main__":
    main()
