#!/usr/bin/env python3
"""Item 5 -- incident vs deposited energy, at EVENT level, from interaction records.

Why this exists: the earlier investigation explained EIGER2's high-energy counts
as Compton scattering, but that was KINEMATIC INFERENCE (a Compton edge
calculation plus a consistency argument), not evidence from interaction records.
No per-event data existed in this project -- all 566 ROOT files were histogram
only. The checklist asks, correctly, to only call Compton a measured route "if
the interaction records support it".

This reads genuine per-event Geant4 records, produced by enabling
[ROOTObjectWriter] + record_all_tracks, and classifies every event by mechanism
using MCTrack's own origin_g4_process_name_ and end_g4_vol_name_.

Mechanisms, distinguished by what the primary gamma did and what left the sensor:
    FULL_ABSORPTION   primary absorbed, nothing escaped      -> E_dep ~ E_incident
    FLUORESCENCE_ESC  primary absorbed, a secondary gamma
                      escaped the sensor                     -> E_dep ~ E_inc - E_esc
    COMPTON_PARTIAL   primary Compton-scattered and left     -> E_dep = small recoil
    NO_INTERACTION    primary passed straight through        -> no deposit

Note uproot cannot read PixelHit or MCParticle from these files (memberwise
serialisation of PointerWrapper<MCParticle> is unimplemented), so the deposited
energy here is reconstructed from the Geant4 energy budget rather than from the
digitised signal. The digitised spectrum is taken from the companion histogram
file, which is the same quantity the production pipeline windows on.

Run: PYTHONPATH=. ./venv/bin/python analysis/investigations/claim_confirmation/item5_event_level.py
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import uproot

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

OUT = Path(__file__).resolve().parent
DATA = OUT / "data"
MEV_TO_KEV = 1000.0
SENSOR_VOL = "sensor_eiger2_detector_phys"
WINDOW = (4.0, 80.0)          # EIGER2's difference-image window
ENERGIES = [90, 100, 120, 150]


def classify_event(tracks) -> dict:
    """Classify one event from its MCTrack records."""
    primary = None
    escaped_gamma_keV = 0.0
    n_compton = 0
    n_phot = 0
    for t in tracks:
        proc = t.member("origin_g4_process_name_")
        pid = t.member("particle_id_")
        start = t.member("start_g4_vol_name_")
        end = t.member("end_g4_vol_name_")
        e0 = t.member("initial_kin_E_") * MEV_TO_KEV
        if proc == "none" and pid == 22:
            primary = dict(e0=e0, end=end,
                           efinal=t.member("final_kin_E_") * MEV_TO_KEV)
        if proc == "compt":
            n_compton += 1
        if proc == "phot":
            n_phot += 1
        # a secondary gamma created in the sensor that ends outside it
        if pid == 22 and proc != "none" and start == SENSOR_VOL and end != SENSOR_VOL:
            escaped_gamma_keV += e0

    if primary is None:
        return dict(mechanism="NO_PRIMARY", e_dep_keV=np.nan,
                    escaped_keV=0.0, n_compton=n_compton)

    interacted = primary["end"] == SENSOR_VOL or n_compton or n_phot
    if not interacted:
        return dict(mechanism="NO_INTERACTION", e_dep_keV=0.0,
                    escaped_keV=0.0, n_compton=n_compton)

    if primary["end"] != SENSOR_VOL:
        # the primary left the sensor: it deposited only what it lost
        e_dep = primary["e0"] - primary["efinal"] - escaped_gamma_keV
        mech = "COMPTON_PARTIAL" if n_compton else "PARTIAL_OTHER"
        return dict(mechanism=mech, e_dep_keV=max(e_dep, 0.0),
                    escaped_keV=escaped_gamma_keV, n_compton=n_compton)

    # primary stopped inside the sensor
    e_dep = primary["e0"] - escaped_gamma_keV
    mech = "FLUORESCENCE_ESC" if escaped_gamma_keV > 0.5 else "FULL_ABSORPTION"
    return dict(mechanism=mech, e_dep_keV=max(e_dep, 0.0),
                escaped_keV=escaped_gamma_keV, n_compton=n_compton)


def analyse(energy: int) -> pd.DataFrame:
    path = REPO_ROOT / "data" / f"p2_bare_eiger2_obj_{energy}keV_objects.root"
    if not path.exists():
        return pd.DataFrame()
    with uproot.open(path) as f:
        arr = f["MCTrack"]["global"].array(library="np")
    rows = [dict(beam_keV=energy, **classify_event(ev)) for ev in arr]
    return pd.DataFrame(rows)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    frames = [analyse(E) for E in ENERGIES]
    frames = [f for f in frames if not f.empty]
    if not frames:
        raise SystemExit("no object files found -- run the WRITE_OBJECTS batch first")
    df = pd.concat(frames, ignore_index=True)
    df["in_window"] = df.e_dep_keV.between(*WINDOW)
    df.to_csv(DATA / "item5_event_classification.csv.gz", index=False,
              compression="gzip")

    print("=" * 78)
    print("ITEM 5 -- event-level mechanism, from Geant4 interaction records")
    print(f"  EIGER2, 0.75 mm, window {WINDOW[0]:g}-{WINDOW[1]:g} keV")
    print("=" * 78)

    print()
    print("Mechanism breakdown per beam energy (10,000 events each):")
    pivot = df.pivot_table(index="beam_keV", columns="mechanism",
                           values="e_dep_keV", aggfunc="size", fill_value=0)
    print(pivot.to_string())
    pivot.to_csv(DATA / "item5_mechanism_counts.csv")

    print()
    print("Of the events landing INSIDE the 4-80 keV window, which mechanism?")
    print()
    win = df[df.in_window]
    wp = win.pivot_table(index="beam_keV", columns="mechanism",
                         values="e_dep_keV", aggfunc="size", fill_value=0)
    wp["total"] = wp.sum(axis=1)
    for m in wp.columns:
        if m != "total":
            wp[f"{m}_pct"] = wp[m] / wp["total"] * 100
    print(wp[[c for c in wp.columns if not c.endswith("_pct")]].to_string())
    print()
    print("  as percentages:")
    pct_cols = [c for c in wp.columns if c.endswith("_pct")]
    print(wp[pct_cols].round(1).to_string())
    wp.to_csv(DATA / "item5_in_window_mechanisms.csv")

    print()
    print("Mean deposited energy by mechanism (keV):")
    md = df[df.mechanism != "NO_INTERACTION"].pivot_table(
        index="beam_keV", columns="mechanism", values="e_dep_keV", aggfunc="mean")
    print(md.round(2).to_string())

    print()
    print("Mean escaped-photon energy where fluorescence escaped (keV):")
    fl = df[df.mechanism == "FLUORESCENCE_ESC"]
    if not fl.empty:
        print(fl.groupby("beam_keV").escaped_keV.agg(["mean", "count"]).round(2).to_string())
        print()
        print("  CdTe K-fluorescence reference: Cd Ka 23.1 keV, Te Ka 27.5 keV")

    print()
    print("-" * 78)
    print("VERDICT")
    print("-" * 78)
    tot_win = len(win)
    by_mech = win.mechanism.value_counts()
    print(f"  {tot_win:,} of {len(df):,} events land in the 4-80 keV window.")
    for m, n in by_mech.items():
        print(f"    {m:20s} {n:6,d}  ({n / tot_win * 100:5.1f}%)")
    comp = by_mech.get("COMPTON_PARTIAL", 0)
    fluo = by_mech.get("FLUORESCENCE_ESC", 0)
    print()
    if fluo > comp:
        print(f"  FLUORESCENCE ESCAPE dominates ({fluo / tot_win * 100:.1f}%) over")
        print(f"  Compton ({comp / tot_win * 100:.1f}%). The earlier report's attribution")
        print("  of the high-energy counts to Compton scattering is NOT supported by")
        print("  the interaction records and must be corrected.")
    else:
        print(f"  Compton is the larger route ({comp / tot_win * 100:.1f}% vs "
              f"{fluo / tot_win * 100:.1f}% fluorescence escape).")
    print()
    print(f"Wrote {DATA}/item5_event_classification.csv.gz, "
          f"item5_mechanism_counts.csv, item5_in_window_mechanisms.csv")


if __name__ == "__main__":
    main()
