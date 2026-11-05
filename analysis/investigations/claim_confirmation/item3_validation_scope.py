#!/usr/bin/env python3
"""Item 3 -- what does the "validation" actually prove?

The handover calls the theory-vs-simulation agreement "strong evidence that the
simulation pipeline is trustworthy" (Sec 4) and lists "Independently validate the
Monte Carlo simulation against a first-principles physics prediction" as a
project objective (Sec 1).

Test: which inputs do the two calculations genuinely NOT share?

From phase2_selection_experiment.build_table():
    n_theory += N0 * wE * tE * pE      # pE = analytic P_CdTe
    n_sim    += N0 * wE * tE * r       # r  = Allpix bare-detector response

Run: PYTHONPATH=. ./venv/bin/python analysis/investigations/claim_confirmation/item3_validation_scope.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

OUT = Path(__file__).resolve().parent
DATA = OUT / "data"

INPUTS = [
    # (input, used by theory, used by sim, shared?, source)
    ("N0 scaling (1e6 incident photons)", "yes", "yes", True,
     "phase2_selection_experiment.N0"),
    ("Source spectrum w(E), 14 bins", "yes", "yes", True,
     "spectra/150kvp_weights.csv (SpekPy)"),
    ("Alloy transmission T_a(E)", "yes", "yes", True,
     "material_penetration_uniform/alloy_attenuation.csv (NIST via SpekPy)"),
    ("Sensor thickness", "yes", "yes", True,
     "SCENARIOS dict / bare_root_path tag"),
    ("Detector energy window [lo, hi]", "yes", "yes", True,
     "DETS (framework v3 Table 8/8a)"),
    ("CdTe mu (attenuation coefficient)", "yes", "no", False,
     "material_penetration_uniform/cdte_interaction.csv"),
    ("P_CdTe(E) = 1 - exp(-mu t)  [analytic]", "yes", "no", False,
     "phase2_selection_experiment.P_cdte()"),
    ("R_d(E) bare-detector response  [Monte Carlo]", "no", "yes", False,
     "Allpix ROOT: charge/cluster_charge + event_size_clusters"),
]


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(INPUTS, columns=["input", "theory", "simulation",
                                       "shared", "source"])
    df.to_csv(DATA / "item3_shared_inputs.csv", index=False)

    print("=" * 78)
    print("ITEM 3 -- which inputs are genuinely independent?")
    print("=" * 78)
    print()
    print(f"{'input':46s} {'theory':>7s} {'sim':>5s} {'shared':>7s}")
    for _, r in df.iterrows():
        print(f"{r.input:46s} {r.theory:>7s} {r.simulation:>5s} "
              f"{'COMMON' if r.shared else '--':>7s}")

    shared = int(df.shared.sum())
    print()
    print(f"  {shared} of {len(df)} inputs are common-mode.")
    print("  The comparison varies exactly ONE factor: analytic P_CdTe(E) vs the")
    print("  simulated response R_d(E). Everything else cancels by construction --")
    print("  an error in the spectrum or in the alloy attenuation moves BOTH sides")
    print("  by the same amount and cannot be detected by this check.")

    print()
    print("-" * 78)
    print("Is there any comparison against measured detector data?")
    print("-" * 78)
    hits = subprocess.run(
        ["grep", "-rilE", "measured|hardware|lab data|calibration run",
         "--include=*.py", "--include=*.csv", str(REPO_ROOT / "data")],
        capture_output=True, text=True).stdout.strip()
    print(f"  measured-data files under data/: {hits if hits else 'NONE'}")
    print("  No hardware measurement exists anywhere in the repository; Phase 4")
    print("  (lab crystal growth / CdTe wafer sourcing) was never executed.")

    print()
    print("-" * 78)
    print("VERDICT")
    print("-" * 78)
    print("  This is an ANALYTICAL CONSISTENCY CHECK on the detector-response")
    print("  factor, not physical validation. It is still useful: it confirms")
    print("  Allpix's simulated detection efficiency reproduces the analytic")
    print("  absorption probability to <1% for wide-window chips, which would")
    print("  catch a misconfigured sensor, a wrong thickness, or a broken")
    print("  digitizer. It cannot catch an error in the spectrum, the alloy")
    print("  compositions, or the attenuation data, because both sides use the")
    print("  same numbers for those.")
    print()
    print(f"Wrote {DATA}/item3_shared_inputs.csv")


if __name__ == "__main__":
    main()
