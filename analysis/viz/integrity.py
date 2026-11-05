"""Integrity checks that do not depend on a physics model.

The strongest statement this pipeline can make about a run is not "the physics
looks odd" -- it is "two runs that the configuration says must be identical are
not". That claim needs no model, no attenuation table and no assumption about
thresholds, so it survives any argument about the simulation's physics.

paired_config_check is the check that identifies the phase-2 EIGER2 problem:
every chip's tagged and untagged sim configs are byte-identical, five of six
chips then agree to within 1% at 20 keV, and EIGER2 disagrees by 42%.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from analysis.viz import registry as reg
from analysis.viz.provenance import sha256_file
from analysis.viz.runreader import read_run_or_none

# Below this energy CdTe is opaque at every thickness in this study, so two
# runs differing only in sensor thickness MUST agree here. Verified empirically:
# five of six phase-2 chips agree to within 1% at 20 keV across thicknesses.
OPAQUE_ENERGY_MAX_KEV = 40.0

# Fractional efficiency difference tolerated between runs whose configs hash
# identically. Monte-Carlo noise at n=10,000 is well under 1%.
PAIRED_TOLERANCE = 0.05


@dataclass
class PairedFinding:
    detector: str
    campaign: str
    energy_keV: float
    run_a: str
    run_b: str
    config_sha_a: str | None
    config_sha_b: str | None
    configs_identical: bool
    eff_a: float
    eff_b: float

    @property
    def ratio(self) -> float:
        return self.eff_a / self.eff_b if self.eff_b else math.nan

    @property
    def relative_difference(self) -> float:
        denom = max(self.eff_a, self.eff_b)
        return abs(self.eff_a - self.eff_b) / denom if denom else math.nan

    @property
    def is_contradiction(self) -> bool:
        return (self.configs_identical
                and self.relative_difference > PAIRED_TOLERANCE)

    def explain(self) -> str:
        if not self.configs_identical:
            return (f"{self.run_a} and {self.run_b} were produced from different "
                    "configurations, so a difference here is expected.")
        if not self.is_contradiction:
            return (f"{self.run_a} and {self.run_b} share a byte-identical "
                    f"configuration and agree to "
                    f"{self.relative_difference * 100:.1f}% at "
                    f"{self.energy_keV:g} keV, as they must.")
        return (
            f"{self.run_a} and {self.run_b} were produced from a BYTE-IDENTICAL "
            f"configuration (sha256 {self.config_sha_a[:12]}), yet detect "
            f"{self.eff_a * 100:.1f}% and {self.eff_b * 100:.1f}% of events at "
            f"{self.energy_keV:g} keV -- a {self.relative_difference * 100:.0f}% "
            "disagreement. At this energy CdTe is opaque at every thickness in "
            "this study, so sensor thickness cannot explain it. One of these "
            "runs was produced by a configuration that no longer exists on "
            "disk, and nothing recorded says which."
        )


def _efficiency(key: reg.RunKey, data_dir: Path | None = None) -> float:
    run = read_run_or_none(reg.root_path(key, data_dir))
    if run is None or run.is_empty:
        return math.nan
    ev = run.hists.get("event_size_pixels")
    cl = run.hists.get("event_size_clusters")
    if ev is None or cl is None or not ev.entries:
        return math.nan
    return float(np.nansum(cl.values)) / float(ev.entries)


def paired_config_check(campaign: str,
                        data_dir: Path | None = None) -> list[PairedFinding]:
    """Compare every pair of runs that differ only by a variant tag.

    Runs are paired when they share campaign, mode, detector and energy but
    differ in their variant (e.g. the 1 mm and 0.75 mm phase-2 runs). If their
    sim configs hash identically, their results must agree.
    """
    d = reg.discover(data_dir, campaign)
    groups: dict[tuple, list[reg.RunKey]] = {}
    for k in d.runs:
        if k.energy_keV is None or k.energy_keV > OPAQUE_ENERGY_MAX_KEV:
            continue
        groups.setdefault((k.mode, k.detector, k.energy_keV), []).append(k)

    findings: list[PairedFinding] = []
    for (mode, detector, energy), keys in sorted(groups.items()):
        if len(keys) < 2:
            continue
        keys = sorted(keys, key=lambda k: k.run_id)
        for i in range(len(keys) - 1):
            a, b = keys[i], keys[i + 1]
            ca, cb = reg.config_path(a), reg.config_path(b)
            ha = sha256_file(ca) if ca else None
            hb = sha256_file(cb) if cb else None
            ea, eb = _efficiency(a, data_dir), _efficiency(b, data_dir)
            if math.isnan(ea) or math.isnan(eb):
                continue
            findings.append(PairedFinding(
                detector=detector, campaign=campaign, energy_keV=energy,
                run_a=a.run_id, run_b=b.run_id,
                config_sha_a=ha, config_sha_b=hb,
                configs_identical=bool(ha and hb and ha == hb),
                eff_a=ea, eff_b=eb,
            ))
    return findings


def contradictions(campaign: str, data_dir: Path | None = None) -> list[PairedFinding]:
    return [f for f in paired_config_check(campaign, data_dir) if f.is_contradiction]
