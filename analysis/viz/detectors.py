"""Detector parameters, sourced -- deliberately NOT unified.

Two tables exist in the repo and they disagree:

  material_penetration_experiment.DETECTORS  (Study A, 4 chips)
      medipix3 5.0-120 keV, timepix3_cdte 2.88-120 keV
  phase2_selection_experiment.DETS           (Phase 2, 6 chips, framework v3)
      medipix3 3.10-110 keV, timepix3_cdte 2.21-120 keV

Unifying them would silently change published numbers, so instead each campaign
declares which table it uses (CampaignSpec.detector_source) and every threshold
rendered on a page carries the origin of the table it came from. Showing both,
sourced, is the honest presentation; silently picking one is the worst outcome.
"""
from __future__ import annotations

from dataclasses import dataclass

import analysis.scripts.material_penetration_experiment as _study_a


@dataclass(frozen=True)
class DetectorSpec:
    key: str
    label: str
    lower_keV: float
    upper_keV: float
    bins: int
    proxy: bool
    source: str            # which table
    origin: str            # const: origin string for the page

    @property
    def root_detector(self) -> str:
        return f"{self.key}_detector"


def _study_a_table() -> dict[str, DetectorSpec]:
    out = {}
    for d in _study_a.DETECTORS:
        out[d.key] = DetectorSpec(
            key=d.key, label=d.label,
            lower_keV=float(d.lower_threshold_keV),
            upper_keV=float(d.upper_threshold_keV),
            bins=int(d.bins), proxy=bool(d.proxy), source="study_a",
            origin=f"const:material_penetration_experiment.DETECTORS[{d.key}]",
        )
    return out


def _phase2_table() -> dict[str, DetectorSpec]:
    """Phase 2 framework v3 Table 8/8a.

    Mirrored here rather than imported so that loading this module does not
    execute phase2_selection_experiment's import-time CSV reads.
    Values verified identical to phase2_selection_experiment.DETS.
    """
    rows = [
        ("medipix3", "D1 Medipix3", 3.10, 110.0, 2, False),
        ("medipix4", "D6 Medipix4", 7.85, 150.0, 2, False),
        ("timepix3_cdte", "D4 Timepix3", 2.21, 120.0, 2, False),
        ("timepix4", "D5 Timepix4", 4.43, 150.0, 2, False),
        ("eiger2", "D2 EIGER2", 4.00, 80.0, 2, False),
        ("hexitec_proxy", "D3 HEXITEC", 2.00, 200.0, 2, True),
    ]
    return {
        k: DetectorSpec(k, lbl, lo, hi, b, p, "phase2",
                        f"const:phase2_selection_experiment.DETS[{k}]")
        for k, lbl, lo, hi, b, p in rows
    }


TABLES = {"study_a": _study_a_table(), "phase2": _phase2_table()}


def resolve(detector_key: str, source: str) -> DetectorSpec | None:
    return TABLES.get(source, {}).get(detector_key)


def disagreements() -> list[dict]:
    """Where the two tables differ, for the campaign index's parameter table."""
    out = []
    a, b = TABLES["study_a"], TABLES["phase2"]
    for key in sorted(set(a) & set(b)):
        if (a[key].lower_keV, a[key].upper_keV) != (b[key].lower_keV, b[key].upper_keV):
            out.append({
                "detector": key,
                "study_a": f"{a[key].lower_keV:g}-{a[key].upper_keV:g} keV",
                "phase2": f"{b[key].lower_keV:g}-{b[key].upper_keV:g} keV",
                "study_a_origin": a[key].origin,
                "phase2_origin": b[key].origin,
            })
    return out
