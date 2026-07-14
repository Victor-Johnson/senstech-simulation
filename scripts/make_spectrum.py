#!/usr/bin/env python3
"""
make_spectrum.py  —  Table 4.1 fixed X-ray source, discretised for Route B.

Runs on the HOST in your venv (where uproot/numpy already live):
    pip install spekpy
    python scripts/make_spectrum.py

Produces: spectra/150kvp_weights.csv  (columns: energy_keV, weight)

The weights are RELATIVE (they sum to 1) — they encode the SHAPE of the
incident spectrum. Absolute photon count N0 is set separately in Allpix
via number_of_events, so normalisation here is irrelevant to that.
"""
import os, csv
from pathlib import Path
import numpy as np
import spekpy as sp

# ---------------- Table 4.1 parameters ----------------
KVP         = 150.0                 # tube voltage (spectrum endpoint)
ANODE_ANGLE = 12.0                  # degrees (typical tube anode angle)
FILTERS     = [("Al", 1.0),         # inherent filtration  (Table 4.1)
               ("Al", 1.0)]         # additional filtration (Table 4.1)
SWEEP_MIN   = 20.0                  # keV  — matches your S1 sweep grid
SWEEP_MAX   = 150.0                 # keV
SWEEP_STEP  = 10.0                  # keV  — 14 energies; use 5.0 for finer
                                    #        beam-hardening fidelity (27 energies)
OUT_CSV     = Path(__file__).resolve().parents[1] / "spectra" / "150kvp_weights.csv"
# ------------------------------------------------------

# 1. build the tungsten-tube spectrum
s = sp.Spek(kvp=KVP, th=ANODE_ANGLE)
for material, mm in FILTERS:
    s.filter(material, mm)

# 2. pull the continuous spectrum (k in keV, phi ~ photons/keV, relative)
#    use edges=False so k and phi are equal-length midpoint arrays
k, phi = s.get_spectrum(edges=False)

# 3. integrate fluence over each sweep bin -> the weight for that energy
sweep_E = np.arange(SWEEP_MIN, SWEEP_MAX + SWEEP_STEP, SWEEP_STEP)
weights = []
for E in sweep_E:
    lo, hi = E - SWEEP_STEP / 2.0, E + SWEEP_STEP / 2.0
    m = (k >= lo) & (k < hi)
    w = np.trapezoid(phi[m], k[m]) if m.sum() > 1 else 0.0
    weights.append(w)

weights = np.array(weights)
weights = weights / weights.sum()          # relative incident weights

# 4. write the handoff file
os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
with open(OUT_CSV, "w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["energy_keV", "weight"])
    for E, w in zip(sweep_E, weights):
        wr.writerow([f"{E:.1f}", f"{w:.6e}"])

mean_E = np.average(sweep_E, weights=weights)
peak_E = sweep_E[np.argmax(weights)]
print(f"Wrote {OUT_CSV}")
print(f"  {len(sweep_E)} energies, {SWEEP_MIN:.0f}-{SWEEP_MAX:.0f} keV")
print(f"  spectrum mean energy = {mean_E:.1f} keV")
print(f"  spectrum peak energy = {peak_E:.1f} keV")
