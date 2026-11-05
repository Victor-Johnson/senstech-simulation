"""Run identity: the single source of truth for ROOT filenames.

The repo currently reconstructs ROOT filenames in three independent places
(material_penetration_experiment.root_file_name, phase2_selection_experiment.
bare_root_path, phase2_energy_spectra.windowed_R). Each knows one convention
and none can parse. This module does both directions for every convention in
data/, so a run can be discovered from disk as well as addressed by name.

The round-trip property build_name(parse_name(x)) == x is enforced by
tests/test_registry.py over every file in data/, which is what stops the
template and the regex from drifting apart.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SCENARIO_ROOT = REPO_ROOT / "simulation" / "configs" / "scenarios"

# Detector keys as they appear in filenames. Order matters: the alternation is
# sorted longest-first so timepix3_cdte wins over a hypothetical timepix3.
DETECTOR_KEYS = (
    "medipix3", "medipix4", "timepix3_cdte", "timepix4", "eiger2",
    "hexitec_proxy", "hexitec", "cdte", "si",
)
_DET = "|".join(sorted(DETECTOR_KEYS, key=len, reverse=True))


@dataclass(frozen=True)
class RunKey:
    """Identity of one simulation run == one ROOT file."""

    campaign: str
    mode: str
    detector: str
    energy_keV: float | None = None
    variant: tuple[tuple[str, str], ...] = ()   # hashable; use .var for a dict

    @property
    def var(self) -> dict[str, str]:
        return dict(self.variant)

    @property
    def run_id(self) -> str:
        """Stable slug. Equals the driver's output_name where one exists."""
        return build_name(self)

    def with_variant(self, **kw: str) -> "RunKey":
        merged = {**self.var, **{k: v for k, v in kw.items() if v is not None}}
        return RunKey(self.campaign, self.mode, self.detector, self.energy_keV,
                      tuple(sorted(merged.items())))

    def __str__(self) -> str:
        return self.run_id


@dataclass(frozen=True)
class NamePattern:
    """One filename convention.

    `template` builds a name from fields; `regex` parses one back. Both use the
    same field names, which is what makes the round-trip checkable.
    """

    mode: str
    template: str
    regex: re.Pattern
    # Fields that are neither detector nor energy end up in RunKey.variant.
    optional: tuple[str, ...] = ()


@dataclass(frozen=True)
class CampaignSpec:
    name: str
    patterns: tuple[NamePattern, ...]
    scenario_dir: str | None = None       # under simulation/configs/scenarios/
    manifest: str | None = None           # under data/
    driver: str | None = None             # under simulation/
    detector_source: str = "none"         # "study_a" | "phase2" | "none"
    description: str = ""

    @property
    def config_dir(self) -> Path | None:
        return SCENARIO_ROOT / self.scenario_dir if self.scenario_dir else None

    @property
    def manifest_path(self) -> Path | None:
        return DATA_DIR / self.manifest if self.manifest else None

    @property
    def driver_path(self) -> Path | None:
        return REPO_ROOT / "simulation" / self.driver if self.driver else None


def _p(mode: str, template: str, regex: str, optional: tuple[str, ...] = ()) -> NamePattern:
    return NamePattern(mode, template, re.compile("^" + regex + "$"), optional)


# --------------------------------------------------------------------------
# Campaign declarations. Adding a campaign means adding an entry here -- never
# another hardcoded f-string somewhere in an analysis script.
# --------------------------------------------------------------------------
CAMPAIGNS: dict[str, CampaignSpec] = {
    "material_penetration": CampaignSpec(
        name="material_penetration",
        description="Study A, original run at native sensor thicknesses (mp_).",
        scenario_dir="material_penetration",
        manifest="material_penetration_run_manifest.csv",
        driver="run_material_penetration.sh",
        detector_source="study_a",
        patterns=(
            _p("bare", "mp_bare_{detector}_{energy:.0f}keV",
               rf"mp_bare_(?P<detector>{_DET})_(?P<energy>\d+)keV"),
            _p("transport", "mp_transport_{detector}_{alloy}_{energy:.0f}keV",
               rf"mp_transport_(?P<detector>{_DET})_(?P<alloy>alloy\d)_(?P<energy>\d+)keV"),
        ),
    ),
    "material_penetration_uniform": CampaignSpec(
        name="material_penetration_uniform",
        description="Study A rerun with all sensors at 1.0 mm CdTe (mpu_).",
        scenario_dir="material_penetration_uniform",
        manifest="material_penetration_uniform_run_manifest.csv",
        driver="run_material_penetration_uniform.sh",
        detector_source="study_a",
        patterns=(
            _p("bare", "mpu_bare_{detector}_{energy:.0f}keV",
               rf"mpu_bare_(?P<detector>{_DET})_(?P<energy>\d+)keV"),
            _p("transport", "mpu_transport_{detector}_{alloy}_{energy:.0f}keV",
               rf"mpu_transport_(?P<detector>{_DET})_(?P<alloy>alloy\d)_(?P<energy>\d+)keV"),
        ),
    ),
    "phase2_selection": CampaignSpec(
        name="phase2_selection",
        description="Phase 2 six-ASIC selection framework (p2_).",
        scenario_dir="phase2_selection",
        manifest="phase2_selection_run_manifest.csv",
        driver="run_phase2_selection.sh",
        detector_source="phase2",
        patterns=(
            # thickness_tag is the driver's OUTPUT_TAG, e.g. "_075mm". Absent
            # means the 1 mm run. These two must never collide -- that they
            # once did is why the 1 mm manifest rows were lost.
            # variant_tag carries the 2026-09 claim-confirmation audit's reruns
            # (CdTe transport arms and the per-event object batch). Longest
            # alternatives first so _cdte075 wins over _cdte. The detector
            # alternation is itself longest-first, so timepix3_cdte still binds
            # greedily and p2_bare_timepix3_cdte_cdte_80keV parses correctly.
            # `objects` marks the companion per-event ROOTObjectWriter file.
            _p("bare",
               "p2_bare_{detector}{thickness_tag}{variant_tag}_{energy:.0f}keV{objects}",
               rf"p2_bare_(?P<detector>{_DET})(?P<thickness_tag>_\d+mm)?"
               r"(?P<variant_tag>_cdteh075|_cdte075|_cdteh|_cdte|_obj)?"
               r"_(?P<energy>\d+)keV(?P<objects>_objects)?",
               optional=("thickness_tag", "variant_tag", "objects")),
            _p("transport", "p2_transport_{detector}_{alloy}_{energy:.0f}keV",
               rf"p2_transport_(?P<detector>{_DET})_(?P<alloy>alloy\d)_(?P<energy>\d+)keV"),
        ),
    ),
    "chip_comparison": CampaignSpec(
        name="chip_comparison",
        description="Three-chip comparison categories cat1-cat4.",
        scenario_dir="chip_comparison",
        detector_source="study_a",
        patterns=(
            _p("material", "cat{cat}_{detector}_{energy:.0f}keV_{material}",
               rf"cat(?P<cat>\d)_(?P<detector>{_DET})_(?P<energy>\d+)keV_(?P<material>[a-z]+)"),
            _p("occlusion", "cat{cat}_{detector}_occl_{scene}_{content}",
               rf"cat(?P<cat>\d)_(?P<detector>{_DET})_occl_(?P<scene>[a-z]+)_(?P<content>[a-z]+)"),
            _p("degradation", "cat{cat}_{detector}_degr_{level}",
               rf"cat(?P<cat>\d)_(?P<detector>{_DET})_degr_(?P<level>[a-z]+)"),
            _p("background", "cat{cat}_{detector}_clean_background",
               rf"cat(?P<cat>\d)_(?P<detector>{_DET})_clean_background"),
        ),
    ),
    "food_inspection": CampaignSpec(
        name="food_inspection",
        description="Food contaminant detection scenarios.",
        scenario_dir="food_inspection",
        driver="run_food_inspection.sh",
        patterns=(
            # thickness uses 'p' as the decimal point, e.g. 0p5mm.
            _p("food", "food_{sample}_{energy:.0f}keV_{thickness}mm",
               r"food_(?P<sample>[a-z]+)_(?P<energy>\d+)keV_(?P<thickness>\d+(?:p\d+)?)mm"),
        ),
    ),
    "baggage_inspection": CampaignSpec(
        name="baggage_inspection",
        description="Baggage threat detection under clutter.",
        scenario_dir="baggage_inspection",
        driver="run_baggage_occlusion.sh",
        patterns=(
            _p("occlusion", "baggage_{content}_{energy:.0f}keV_{scene}",
               r"baggage_(?P<content>occl|clutteronly)_(?P<energy>\d+)keV_(?P<scene>[a-z]+)"),
        ),
    ),
    "sweeps": CampaignSpec(
        name="sweeps",
        description="Single-parameter sweeps s1-s8 (energy, degradation, "
                    "threshold, bias, temperature, pitch, flux, thickness).",
        patterns=(
            _p("energy", "{sweep}_{detector}_{energy:.0f}keV",
               rf"(?P<sweep>s\d)_(?P<detector>{_DET})_(?P<energy>\d+)keV"),
            _p("threshold", "{sweep}_{detector}_thresh{threshold_e}e",
               rf"(?P<sweep>s\d)_(?P<detector>{_DET})_thresh(?P<threshold_e>\d+)e"),
            _p("thickness", "{sweep}_{detector}_thick{thickness_um}um",
               rf"(?P<sweep>s\d)_(?P<detector>{_DET})_thick(?P<thickness_um>\d+)um"),
            _p("bias", "{sweep}_{detector}_bias{bias_V}V",
               rf"(?P<sweep>s\d)_(?P<detector>{_DET})_bias(?P<bias_V>\d+)V"),
            _p("temperature", "{sweep}_{detector}_{temperature_K}K",
               rf"(?P<sweep>s\d)_(?P<detector>{_DET})_(?P<temperature_K>\d+)K"),
            _p("flux", "{sweep}_{detector}_flux{flux}",
               rf"(?P<sweep>s\d)_(?P<detector>{_DET})_flux(?P<flux>\d+)"),
            _p("pitch", "{sweep}_{detector}_pitch{pitch}",
               rf"(?P<sweep>s\d)_(?P<detector>{_DET})_pitch(?P<pitch>[a-z]+)"),
            _p("degradation", "{sweep}_{detector}_{age}",
               rf"(?P<sweep>s\d)_(?P<detector>{_DET})_(?P<age>fresh|\d+(?:year|years|months))"),
            _p("degradation", "{sweep}_v{version}_{age}",
               r"(?P<sweep>s\d)_v(?P<version>\d)_(?P<age>fresh|extreme|heavy|light|"
               r"moderate|severe|\d+(?:year|years|months))"),
            _p("timing", "{sweep}_test_{window_ns}ns",
               r"(?P<sweep>s\d)_test_(?P<window_ns>\d+)ns"),
        ),
    ),
    "legacy": CampaignSpec(
        name="legacy",
        description="Early one-off baselines kept for provenance.",
        patterns=(
            _p("baseline", "{detector}_{material}_REAL",
               rf"(?P<detector>{_DET})_(?P<material>[a-z]+)_REAL"),
            _p("baseline", "{detector}_{material}_v{version}",
               rf"(?P<detector>{_DET})_(?P<material>[a-z]+)_v(?P<version>\d+)"),
        ),
    ),
}

# Fields that are RunKey attributes rather than variant entries.
_STRUCTURAL = {"detector", "energy"}


def parse_name(stem: str) -> RunKey | None:
    """Parse a ROOT file stem into a RunKey, or None if no convention matches.

    Callers must treat None as "report this file", never as "skip it" -- silent
    skipping is how runs go missing.
    """
    for spec in CAMPAIGNS.values():
        for pat in spec.patterns:
            m = pat.regex.match(stem)
            if not m:
                continue
            groups = m.groupdict()
            energy = groups.get("energy")
            variant = {k: v for k, v in groups.items()
                       if k not in _STRUCTURAL and v is not None}
            return RunKey(
                campaign=spec.name,
                mode=pat.mode,
                detector=groups.get("detector") or "",
                energy_keV=float(energy) if energy is not None else None,
                variant=tuple(sorted(variant.items())),
            )
    return None


def build_name(key: RunKey) -> str:
    """Render a RunKey back to its ROOT file stem."""
    spec = CAMPAIGNS.get(key.campaign)
    if spec is None:
        raise KeyError(f"unknown campaign: {key.campaign}")

    fields: dict[str, object] = dict(key.var)
    fields["detector"] = key.detector
    if key.energy_keV is not None:
        fields["energy"] = key.energy_keV

    candidates: list[str] = []
    for pat in spec.patterns:
        if pat.mode != key.mode:
            continue
        # Optional fields render as "" when absent, which is what makes the
        # tagged and untagged phase-2 names share one template.
        rendered = dict(fields)
        for opt in pat.optional:
            rendered.setdefault(opt, "")
        try:
            name = pat.template.format(**rendered)
        except (KeyError, IndexError):
            continue
        if not pat.regex.match(name):
            continue
        # Require the rendered name to parse back to the same key. Several
        # campaigns have more than one pattern per mode (legacy _REAL vs _vN,
        # the two sweep degradation shapes), and rendering with the first
        # regex-compatible template would silently produce a different run's
        # name. This makes the round-trip property self-enforcing.
        if parse_name(name) == key:
            return name
        candidates.append(name)

    if candidates:
        return candidates[0]
    raise ValueError(f"no pattern in campaign {key.campaign!r} renders {key!r}")


def root_path(key: RunKey, data_dir: Path | None = None) -> Path:
    return (data_dir or DATA_DIR) / f"{build_name(key)}.root"


def config_path(key: RunKey) -> Path | None:
    """Host path of the per-run sim config (the driver writes container paths)."""
    spec = CAMPAIGNS.get(key.campaign)
    if spec is None or spec.config_dir is None:
        return None
    return spec.config_dir / f"{build_name(key)}.conf"


def to_host_path(container_path: str) -> Path:
    """Manifest config_path values are container paths; map them to the host."""
    s = str(container_path)
    prefix = "/data/simulation"
    if s.startswith(prefix):
        return REPO_ROOT / "simulation" / s[len(prefix):].lstrip("/")
    return Path(s)


@dataclass
class Discovery:
    runs: list[RunKey] = field(default_factory=list)
    unparsed: list[Path] = field(default_factory=list)

    def by_campaign(self) -> dict[str, list[RunKey]]:
        out: dict[str, list[RunKey]] = {}
        for k in self.runs:
            out.setdefault(k.campaign, []).append(k)
        return out


def discover(data_dir: Path | None = None, campaign: str | None = None) -> Discovery:
    """Enumerate every ROOT file on disk.

    Files that match no pattern are returned in `unparsed` rather than dropped,
    so a new naming convention shows up as a visible gap instead of silently
    shrinking the run count.
    """
    data_dir = data_dir or DATA_DIR
    result = Discovery()
    if not data_dir.is_dir():
        return result
    for path in sorted(data_dir.glob("*.root")):
        key = parse_name(path.stem)
        if key is None:
            result.unparsed.append(path)
        elif campaign is None or key.campaign == campaign:
            result.runs.append(key)
    return result


def sort_key(key: RunKey) -> tuple:
    """Deterministic ordering: campaign, detector, energy, then variant."""
    return (key.campaign, key.mode, key.detector,
            key.energy_keV if key.energy_keV is not None else -1.0,
            key.variant)
