"""Read Stage-A phase-space files written by simulation/stageA_g4/stagea.cc.

Record: <7f2B> = E_keV, x_mm, y_mm, ux, uy, uz, t_ns (float32), origin, last_volume (uint8).
origin: 0 primary, 1 Rayleigh only, 2 Compton, 3 secondary photon (fluorescence/brems), 4 other
last_volume: 0 none, 1 Object, 2 Belt, 3 Rail, 4 Cabinet, 5 Collimator/Slit, 6 Housing, 7 other
Normalisation: photons represented per mAs = sum(spectrum weight [photons/keV/cm2/mAs at 1 m] * 1 keV)
  * (aim rectangle area at z_aim, projected to 1 m, in cm2). Divide counts by n_primaries and multiply by
  this number to get photons per mAs.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

DTYPE = np.dtype([("E_keV", "<f4"), ("x_mm", "<f4"), ("y_mm", "<f4"), ("ux", "<f4"), ("uy", "<f4"),
                  ("uz", "<f4"), ("t_ns", "<f4"), ("origin", "u1"), ("last_volume", "u1")])
ORIGIN = {0: "primary", 1: "rayleigh", 2: "compton", 3: "secondary_photon", 4: "other"}
VOLUME = {0: "none", 1: "object", 2: "belt", 3: "rail", 4: "cabinet", 5: "collimator_slit", 6: "housing", 7: "other"}


def read(prefix: str | Path) -> tuple[pd.DataFrame, dict]:
    prefix = str(prefix)
    meta = json.loads(Path(prefix + ".json").read_text())
    arr = np.fromfile(prefix + ".bin", dtype=DTYPE)
    if len(arr) != meta["written"]:
        raise ValueError(f"{prefix}: {len(arr)} records but header says {meta['written']}")
    return pd.DataFrame(arr), meta


def photons_per_mAs_represented(meta: dict, spectrum_csv: str | Path) -> float:
    s = pd.read_csv(spectrum_csv)
    ax, ay, az = meta["aim_rect_mm"]
    area_cm2_at_1m = (ax / 10) * (ay / 10) * (1000.0 / az) ** 2
    return float(s.weight.sum()) * area_cm2_at_1m
