"""What produced a run, and how much of that is recorded vs reconstructed.

The central idea: never present a reconstructed value as a recorded one. Every
field carries a source in `field_sources`, and the run page renders that source
as a badge. "We do not know" is a better answer than a plausible guess.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from analysis.viz import manifest as mf
from analysis.viz import registry as reg

# Ordered by trust, highest first. Rendered as badges on the run page.
SOURCE_ORDER = ("manifest", "conf", "root", "filename", "inferred", "default", "absent")
UNTRUSTED_SOURCES = {"inferred", "default", "absent"}


def sha256_file(path: Path, chunk: int = 1 << 20) -> str | None:
    path = Path(path)
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(("git", *args), cwd=reg.REPO_ROOT,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def git_rev() -> str:
    rev = _git("rev-parse", "HEAD") or "unknown"
    dirty = _git("status", "--porcelain")
    return f"{rev}-dirty" if dirty else rev


@dataclass(frozen=True)
class FileProv:
    path: Path
    exists: bool
    sha256: str | None = None
    bytes: int | None = None
    mtime_utc: str | None = None
    git_tracked: bool = False

    @classmethod
    def capture(cls, path: Path | None, *, hash_it: bool = True) -> "FileProv":
        if path is None:
            return cls(Path("."), False)
        path = Path(path)
        if not path.exists():
            return cls(path, False)
        st = path.stat()
        tracked = _git("ls-files", "--error-unmatch", str(path)) is not None
        return cls(
            path=path, exists=True,
            sha256=sha256_file(path) if hash_it else None,
            bytes=st.st_size,
            mtime_utc=datetime.fromtimestamp(st.st_mtime, timezone.utc)
                              .isoformat(timespec="seconds"),
            git_tracked=tracked,
        )


_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_ENTRY = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*=\s*(.*?)\s*$")


def parse_allpix_conf(text: str) -> dict[str, dict[str, str]]:
    """Minimal Allpix INI parser.

    configparser is not usable here: Allpix allows a bare section with no keys
    ([DetectorHistogrammer]) and duplicate section names across detector files.
    """
    out: dict[str, dict[str, str]] = {}
    section = ""
    for line in text.splitlines():
        line = line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        m = _SECTION.match(line)
        if m:
            section = m.group(1)
            out.setdefault(section, {})
            continue
        m = _ENTRY.match(line)
        if m and section:
            out[section][m.group(1)] = m.group(2).strip().strip('"')
    return out


@dataclass
class RunProvenance:
    run_id: str
    key: reg.RunKey
    root: FileProv
    sim_config: FileProv
    sim_config_text: str | None
    detector_config: FileProv
    detector_config_text: str | None
    detector_config_trustworthy: bool
    parsed_conf: dict[str, dict[str, str]]
    parsed_detector_conf: dict[str, dict[str, str]]
    manifest_row: dict | None
    manifest_source: str
    fields: dict[str, object] = field(default_factory=dict)
    field_sources: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    generated_utc: str = ""
    generator_git_rev: str = ""

    def source_of(self, name: str) -> str:
        return self.field_sources.get(name, "absent")

    def is_trusted(self, name: str) -> bool:
        return self.source_of(name) not in UNTRUSTED_SOURCES

    @property
    def completeness(self) -> float:
        if not self.field_sources:
            return 0.0
        good = sum(1 for s in self.field_sources.values() if s not in UNTRUSTED_SOURCES)
        return good / len(self.field_sources)

    def set(self, name: str, value, source: str) -> None:
        if value is None or (isinstance(value, str) and not value.strip()):
            self.field_sources.setdefault(name, "absent")
            return
        if name not in self.fields:
            self.fields[name] = value
            self.field_sources[name] = source


# Fields we try to establish for every run, in page order.
TRACKED_FIELDS = (
    "n_events", "random_seed", "source_energy", "sensor_thickness",
    "pixel_pitch", "n_pixels", "sensor_material",
    "threshold", "electronics_noise", "threshold_smearing",
    "bias_voltage", "depletion_voltage", "temperature", "physics_list",
    "passive_material", "image_ref", "image_digest", "allpix_version",
    "driver_name", "driver_git_rev", "started_utc", "status",
)


def capture(key: reg.RunKey, *, data_dir: Path | None = None,
            manifest: mf.Manifest | None = None,
            run_geometry: dict[str, float] | None = None) -> RunProvenance:
    """Assemble everything known about one run, recording where each fact came from."""
    run_id = key.run_id
    root_path = reg.root_path(key, data_dir)
    sim_cfg_path = reg.config_path(key)

    root = FileProv.capture(root_path)
    sim_cfg = FileProv.capture(sim_cfg_path)
    sim_text = sim_cfg_path.read_text() if sim_cfg.exists else None
    parsed = parse_allpix_conf(sim_text) if sim_text else {}

    # The detectors_file the sim config points at, mapped back to the host.
    det_cfg_path = None
    ref = parsed.get("Allpix", {}).get("detectors_file")
    if ref:
        det_cfg_path = reg.to_host_path(ref)
    det_cfg = FileProv.capture(det_cfg_path)
    det_text = det_cfg_path.read_text() if det_cfg.exists else None
    parsed_det = parse_allpix_conf(det_text) if det_text else {}

    prov = RunProvenance(
        run_id=run_id, key=key, root=root,
        sim_config=sim_cfg, sim_config_text=sim_text,
        detector_config=det_cfg, detector_config_text=det_text,
        detector_config_trustworthy=True,
        parsed_conf=parsed, parsed_detector_conf=parsed_det,
        manifest_row=None, manifest_source="absent",
        generated_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        generator_git_rev=git_rev(),
    )

    # A detector config written AFTER the ROOT cannot describe this run. The
    # driver used to share one detector_<chip>_<mode>.conf across thickness
    # variants, so the later variant silently rewrote the earlier one's
    # geometry record. This is how that becomes visible instead of invisible.
    if det_cfg.exists and root.exists and det_cfg.mtime_utc and root.mtime_utc:
        if det_cfg.mtime_utc > root.mtime_utc:
            prov.detector_config_trustworthy = False
            prov.warnings.append(
                f"the detectors file {det_cfg.path.name} was last written "
                f"{det_cfg.mtime_utc}, after this ROOT was produced "
                f"({root.mtime_utc}). Sensor geometry shown from it may belong "
                "to a different run."
            )

    # 1. manifest -- highest trust
    if manifest is not None:
        row = manifest.row_for(run_id)
        if row is not None:
            prov.manifest_row = row
            prov.manifest_source = ("manifest" if str(row.get("schema_version", "1")) == "2"
                                    else "legacy")
            mapping = {
                "n_events": "n_events", "random_seed": "random_seed",
                "sensor_thickness": "sensor_thickness", "pixel_pitch": "pixel_pitch",
                "n_pixels": "n_pixels", "threshold": "threshold_e",
                "electronics_noise": "noise_e", "bias_voltage": "bias_V",
                "depletion_voltage": "depletion_V", "passive_material": "passive_material",
                "image_ref": "image_ref", "image_digest": "image_digest",
                "allpix_version": "allpix_version", "driver_name": "driver_name",
                "driver_git_rev": "driver_git_rev", "started_utc": "started_utc",
                "status": "status",
            }
            for fieldname, col in mapping.items():
                val = row.get(col)
                if not mf.is_blank(val):
                    prov.set(fieldname, val, "manifest")

    # 2. the per-run sim config -- survives even when manifest rows do not
    for section, keys in (("Allpix", ("number_of_events", "random_seed")),
                          ("DepositionGeant4", ("source_energy", "physics_list")),
                          ("ElectricFieldReader", ("bias_voltage", "depletion_voltage")),
                          ("GenericPropagation", ("temperature",)),
                          ("DefaultDigitizer", ("threshold", "electronics_noise",
                                                "threshold_smearing"))):
        for k in keys:
            val = parsed.get(section, {}).get(k)
            name = "n_events" if k == "number_of_events" else k
            prov.set(name, val, "conf")

    # 3. the detector config -- only when it can be trusted for this run
    if prov.detector_config_trustworthy:
        for sect in parsed_det.values():
            for k in ("sensor_thickness", "pixel_size", "number_of_pixels",
                      "sensor_material"):
                if k in sect:
                    name = {"pixel_size": "pixel_pitch",
                            "number_of_pixels": "n_pixels"}.get(k, k)
                    prov.set(name, sect[k], "conf")

    # 4. the ROOT's own axes -- geometry that is measured, not declared
    for name, gkey in (("pixel_pitch", "pixel_pitch_x_um"), ("n_pixels", "n_pixels_x")):
        if run_geometry and gkey in run_geometry:
            unit = "um" if "pitch" in gkey else ""
            prov.set(name, f"{run_geometry[gkey]:g}{unit}", "root")

    # 5. the filename
    prov.set("source_energy",
             f"{key.energy_keV:g}keV" if key.energy_keV is not None else None, "filename")
    tag = key.var.get("thickness_tag")
    if tag:
        # "_075mm" -> 750um
        digits = tag.strip("_").replace("mm", "")
        try:
            prov.set("sensor_thickness", f"{float('0.' + digits[1:]) * 1000:g}um"
                     if digits.startswith("0") else f"{float(digits) * 1000:g}um",
                     "filename")
        except ValueError:
            pass

    for name in TRACKED_FIELDS:
        prov.field_sources.setdefault(name, "absent")

    if not root.exists:
        prov.warnings.append(
            f"ROOT file absent on this machine: {root_path.name}. "
            "ROOT files are not in git; regenerate or fetch data/."
        )
    if not sim_cfg.exists:
        prov.warnings.append(
            f"no per-run config found at {sim_cfg_path}; parameters below come "
            "from the manifest or the filename only."
        )
    return prov
