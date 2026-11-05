"""Run-manifest schema v1/v2.

v1 (six columns) is what the drivers wrote historically:
    mode,detector,energy_keV,n_events,output_name,config_path
v2 appends provenance the drivers now record. The first six columns keep their
exact order and spelling so material_penetration_experiment.load_manifest()
continues to work untouched -- verified in tests/test_manifest.py.

The v1 key (mode, detector, energy) could not distinguish thickness variants,
which is why the 1 mm phase-2 rows were overwritable. v2 keys on output_name,
which is unique by construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

V1_COLUMNS = ["mode", "detector", "energy_keV", "n_events", "output_name", "config_path"]

V2_EXTRA = [
    "campaign", "output_tag", "sensor_thickness", "pixel_pitch", "n_pixels",
    "threshold_e", "noise_e", "bias_V", "depletion_V", "random_seed",
    "passive_material", "alloy", "gap_mm", "detector_config_path",
    "image_ref", "image_digest", "allpix_version",
    "driver_name", "driver_git_rev",
    "started_utc", "finished_utc", "status", "root_sha256", "root_bytes",
    "schema_version", "provenance_source",
]

V2_COLUMNS = V1_COLUMNS + V2_EXTRA

# Values that mean "this field was never recorded".
_EMPTY = {"", "unknown", "nan", "None", "NaN"}


def is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return str(value).strip() in _EMPTY


@dataclass
class Manifest:
    path: Path
    frame: pd.DataFrame
    schema_version: int

    def row_for(self, output_name: str) -> dict | None:
        if "output_name" not in self.frame.columns:
            return None
        hit = self.frame[self.frame["output_name"] == output_name]
        if hit.empty:
            return None
        return {k: v for k, v in hit.iloc[0].to_dict().items()}

    def recorded_fields(self, output_name: str) -> set[str]:
        """Which v2 fields this row actually carries a value for."""
        row = self.row_for(output_name)
        if row is None:
            return set()
        return {k for k, v in row.items() if not is_blank(v)}

    def __len__(self) -> int:
        return len(self.frame)


def read(path: Path) -> Manifest:
    """Read a v1 or v2 manifest into a frame with the full v2 column set."""
    path = Path(path)
    if not path.exists():
        return Manifest(path, pd.DataFrame(columns=V2_COLUMNS), 0)

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    version = 2 if set(V2_EXTRA) <= set(frame.columns) else 1

    for col in V2_COLUMNS:
        if col not in frame.columns:
            frame[col] = ""
    if version == 1:
        frame["schema_version"] = "1"
        frame["provenance_source"] = "legacy"

    return Manifest(path, frame[V2_COLUMNS + [
        c for c in frame.columns if c not in V2_COLUMNS]], version)


def write(manifest: Manifest, path: Path | None = None) -> Path:
    target = Path(path or manifest.path)
    manifest.frame.to_csv(target, index=False)
    return target


def migrate_v1_file(path: Path, backup_suffix: str = ".v1.bak") -> bool:
    """Upgrade a v1 manifest on disk to the v2 column set.

    Mirrors migrate_manifest_v1() in the bash drivers so the two agree. Returns
    True if a migration happened.
    """
    path = Path(path)
    if not path.exists():
        return False
    header = path.read_text().splitlines()[0] if path.stat().st_size else ""
    if header == ",".join(V2_COLUMNS):
        return False
    if header != ",".join(V1_COLUMNS):
        return False
    backup = path.with_suffix(backup_suffix)
    backup.write_bytes(path.read_bytes())
    write(read(path), path)
    return True
