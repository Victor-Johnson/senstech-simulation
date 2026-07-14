#!/usr/bin/env python3
"""
Analyze the hybrid-validated material penetration experiment.

The production result is Beer-Lambert alloy attenuation multiplied by
bare-detector Allpix response. The passive-alloy Allpix runs are handled
as a small transport cross-check only.
"""

from __future__ import annotations

import argparse
import itertools
import math
import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    import uproot
except ImportError as exc:  # pragma: no cover - dependency check
    raise SystemExit("uproot is required. Run this with the project venv.") from exc

try:
    from spekpy.DataTables import MuData
except ImportError as exc:  # pragma: no cover - dependency check
    raise SystemExit("spekpy is required for NIST attenuation tables.") from exc


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SPECTRUM_CSV = REPO_ROOT / "spectra" / "150kvp_weights.csv"
OUT_DIR = REPO_ROOT / "analysis" / "results" / "material_penetration"
MANIFEST_CSV = DATA_DIR / "material_penetration_run_manifest.csv"

EPSILON_CDTE_EV = 4.43
FINAL_N0 = 1_000_000
DEFAULT_BARE_EVENTS = 10_000
DEFAULT_VALIDATION_EVENTS = 10_000


def binomial_se(p: np.ndarray | float, n: np.ndarray | float) -> np.ndarray | float:
    """Standard error of a rate p measured as k/n successes out of n MC trials.
    Used throughout as an approximate, clearly-labeled uncertainty band: every
    rate in this pipeline (windowed_response, transport_detected_fraction, ...)
    ultimately comes from a finite (10k-event) Monte Carlo run, so it carries
    real statistical noise that the plots didn't previously show."""
    p = np.clip(np.asarray(p, dtype=float), 0.0, 1.0)
    n = np.asarray(n, dtype=float)
    return np.sqrt(p * (1.0 - p) / np.where(n > 0, n, np.nan))

ELEMENT_Z = {
    "Be": 4,
    "O": 8,
    "Al": 13,
    "Fe": 26,
    "Ni": 28,
    "Cu": 29,
    "Zn": 30,
    "Pb": 82,
}


@dataclass(frozen=True)
class Detector:
    key: str
    label: str
    thickness_mm: float
    pixel_pitch_um: float
    lower_threshold_keV: float
    upper_threshold_keV: float
    bins: int
    proxy: bool
    note: str

    @property
    def root_detector(self) -> str:
        return f"{self.key}_detector"


@dataclass(frozen=True)
class Alloy:
    key: str
    label: str
    density_g_cm3: float
    thickness_mm: float
    composition: tuple[tuple[str, float], ...]

    @property
    def thickness_cm(self) -> float:
        return self.thickness_mm / 10.0


DETECTORS = [
    Detector(
        "medipix3",
        "D1 Medipix3 CdTe",
        0.30,
        55,
        5,
        120,
        2,
        False,
        "0.30 mm CdTe; 2x2 charge-summing photon-counting model; 5-120 keV counting window.",
    ),
    Detector(
        "eiger2",
        "D2 EIGER2 CdTe",
        0.75,
        75,
        4,
        80,
        2,
        False,
        "0.75 mm CdTe; photon-counting response with upper threshold in post-processing.",
    ),
    Detector(
        "hexitec_proxy",
        "D3 HEXITEC CdTe proxy",
        1.00,
        250,
        2,
        200,
        1,
        True,
        "Spectroscopic ASIC proxy; not defended as a true threshold-counter simulation.",
    ),
    Detector(
        "timepix3_cdte",
        "D4 Timepix3 CdTe",
        1.00,
        55,
        2.88,
        120,
        4,
        False,
        "Timepix3 ASIC bonded to 1.0 mm CdTe; ToT-derived energy discrimination represented with 4 analysis bins. "
        "Lower threshold is 650e (2.88 keV at 4.43 eV/e-h), the value actually digitized in Allpix; datasheet quotes "
        "a per-pixel-calibrated 600-700e single-particle threshold (~1.5-2.5 keV nominal, not directly consistent "
        "with the electron-count spec), so the simulated 650e value is used as source of truth.",
    ),
]

ALLOYS = [
    Alloy("alloy1", "Alloy 1 C11000 ETP copper", 8.94, 5.0, (("Cu", 0.999), ("O", 0.001))),
    Alloy("alloy2", "Alloy 2 C36000 free-machining brass", 8.50, 5.0, (("Cu", 0.615), ("Zn", 0.355), ("Pb", 0.030))),
    Alloy("alloy3", "Alloy 3 CuNi 90/10 C70600", 8.94, 5.0, (("Cu", 0.886), ("Ni", 0.100), ("Fe", 0.014))),
    Alloy("alloy4", "Alloy 4 C95500 aluminum bronze", 7.53, 5.0, (("Cu", 0.810), ("Al", 0.110), ("Fe", 0.040), ("Ni", 0.040))),
    Alloy("alloy5", "Alloy 5 C17200 beryllium copper", 8.25, 5.0, (("Cu", 0.981), ("Be", 0.019))),
]

# The passive slab actually placed in the Allpix transport runs is Geant4's
# NIST material G4_BRASS. Queried directly from G4NistManager in the container
# image used for the runs: density 8.52 g/cm3, mass fractions Cu 0.57513,
# Zn 0.334122, Pb 0.0907477. NOTE: this is NOT lead-free and NOT C36000 --
# it carries 3x the lead of the alloy2 recipe (9.07% vs 3.0%), which above the
# Pb K-edge (88 keV) suppresses its transmission to ~0.18-0.63x of C36000's.
# All transport-vs-analytic comparisons must therefore use THIS composition
# on the analytic side, otherwise the comparison conflates the composition
# mismatch with the scatter/window physics it is meant to isolate.
G4_BRASS = Alloy(
    "g4_brass",
    "G4_BRASS transport slab (Geant4 NIST, 9.07% Pb)",
    8.52,
    5.0,
    (("Cu", 0.57513), ("Zn", 0.334122), ("Pb", 0.0907477)),
)


def detector_bin_ranges(detector: Detector) -> list[tuple[int, float, float]]:
    edges = np.linspace(detector.lower_threshold_keV, detector.upper_threshold_keV, detector.bins + 1)
    return [(idx + 1, float(edges[idx]), float(edges[idx + 1])) for idx in range(detector.bins)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spectrum", type=Path, default=SPECTRUM_CSV)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_CSV)
    parser.add_argument("--n0", type=int, default=FINAL_N0)
    parser.add_argument("--bare-events", type=int, default=DEFAULT_BARE_EVENTS)
    parser.add_argument("--validation-events", type=int, default=DEFAULT_VALIDATION_EVENTS)
    parser.add_argument(
        "--root-prefix",
        default="mp",
        help="ROOT file name prefix: 'mp' (baseline) or 'mpu' (uniform 1.0 mm thickness rerun).",
    )
    parser.add_argument(
        "--uniform-thickness-mm",
        type=float,
        default=None,
        help="If set, relabel every detector with this sensor thickness (use with --root-prefix mpu; "
        "the physics comes from the ROOT files, this only fixes metadata/labels).",
    )
    parser.add_argument(
        "--medipix3-upper-kev",
        type=float,
        default=None,
        help="Override Medipix3's upper counting-window edge (keV). The upper window is an "
        "analysis-level cut on measured cluster energy, so no new Allpix runs are needed.",
    )
    parser.add_argument(
        "--allow-missing-root",
        action="store_true",
        help="Write attenuation/spectrum outputs even if Allpix ROOT files are missing.",
    )
    return parser.parse_args()


def load_spectrum(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing spectrum CSV: {path}. Run scripts/make_spectrum.py first.")

    spectrum = pd.read_csv(path)
    spectrum["energy_keV"] = spectrum["energy_keV"].astype(float)
    spectrum["weight"] = spectrum["weight"].astype(float)
    weight_sum = spectrum["weight"].sum()
    if not np.isclose(weight_sum, 1.0, atol=1e-5):
        raise ValueError(f"Spectrum weights must sum to 1; got {weight_sum:.8f}")
    return spectrum


def load_manifest(path: Path) -> dict[tuple[str, str, float], int]:
    if not path.exists():
        return {}
    manifest = pd.read_csv(path)
    result: dict[tuple[str, str, float], int] = {}
    for row in manifest.itertuples(index=False):
        result[(row.mode, row.detector, float(row.energy_keV))] = int(row.n_events)
    return result


def get_events(manifest: dict[tuple[str, str, float], int], mode: str, detector: str, energy: float, default: int) -> int:
    return manifest.get((mode, detector, float(energy)), default)


def root_file_name(mode: str, detector: str, energy: float, prefix: str = "mp") -> str:
    if mode == "bare":
        return f"{prefix}_bare_{detector}_{energy:.0f}keV.root"
    if mode == "transport":
        return f"{prefix}_transport_{detector}_alloy2_{energy:.0f}keV.root"
    raise ValueError(mode)


def read_cluster_charge(root_path: Path, detector_name: str) -> tuple[np.ndarray, np.ndarray]:
    with uproot.open(root_path) as root:
        hist = root[f"DetectorHistogrammer/{detector_name}/charge/cluster_charge;1"]
        counts, edges = hist.to_numpy()
    centers = (edges[:-1] + edges[1:]) / 2.0
    return counts.astype(float), centers.astype(float)


def read_detected_event_count(root_path: Path, detector_name: str) -> float:
    """Return the number of events with at least one reconstructed cluster."""
    with uproot.open(root_path) as root:
        key = f"DetectorHistogrammer/{detector_name}/event_size_clusters;1"
        if key not in root:
            counts, _ = root[f"DetectorHistogrammer/{detector_name}/charge/cluster_charge;1"].to_numpy()
            return float(np.sum(counts))
        counts, _ = root[key].to_numpy()
    return float(np.sum(counts))


def read_detector_response(
    spectrum: pd.DataFrame,
    manifest: dict[tuple[str, str, float], int],
    data_dir: Path,
    bare_events_default: int,
    allow_missing_root: bool,
    root_prefix: str = "mp",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    bin_rows: list[dict[str, object]] = []
    missing: list[Path] = []

    for detector in DETECTORS:
        for energy in spectrum["energy_keV"]:
            events = get_events(manifest, "bare", detector.key, float(energy), bare_events_default)
            root_path = data_dir / root_file_name("bare", detector.key, float(energy), root_prefix)

            if not root_path.exists():
                missing.append(root_path)
                if allow_missing_root:
                    for bin_index, low, high in detector_bin_ranges(detector):
                        bin_rows.append(
                            {
                                "detector": detector.key,
                                "detector_label": detector.label,
                                "energy_keV": energy,
                                "detector_energy_bin": bin_index,
                                "bin_low_keV": low,
                                "bin_high_keV": high,
                                "bin_cluster_count": np.nan,
                                "bin_response": np.nan,
                                "proxy_result": detector.proxy,
                            }
                        )
                    rows.append(
                        {
                            "detector": detector.key,
                            "detector_label": detector.label,
                            "energy_keV": energy,
                            "bare_events": events,
                            "cluster_count": np.nan,
                            "intrinsic_response": np.nan,
                            "threshold_window_acceptance": np.nan,
                            "windowed_response": np.nan,
                            "windowed_response_se": np.nan,
                            "mean_cluster_energy_keV": np.nan,
                            "proxy_result": detector.proxy,
                            "note": detector.note,
                            "root_file": str(root_path),
                        }
                    )
                    continue
                raise FileNotFoundError(f"Missing required Allpix ROOT file: {root_path}")

            counts, charge_ke = read_cluster_charge(root_path, detector.root_detector)
            cluster_count = float(np.sum(counts))
            detected_event_count = read_detected_event_count(root_path, detector.root_detector)
            charge_energy_keV = charge_ke * EPSILON_CDTE_EV
            detector_bins = detector_bin_ranges(detector)
            window_count = 0.0
            dominant_bin = np.nan
            dominant_bin_count = -1.0
            for bin_index, low, high in detector_bins:
                if bin_index == detector.bins:
                    in_bin = (charge_energy_keV >= low) & (charge_energy_keV <= high)
                else:
                    in_bin = (charge_energy_keV >= low) & (charge_energy_keV < high)
                bin_count = float(np.sum(counts[in_bin]))
                window_count += bin_count
                if bin_count > dominant_bin_count:
                    dominant_bin = bin_index
                    dominant_bin_count = bin_count
                bin_rows.append(
                    {
                        "detector": detector.key,
                        "detector_label": detector.label,
                        "energy_keV": energy,
                        "detector_energy_bin": bin_index,
                        "bin_low_keV": low,
                        "bin_high_keV": high,
                        "bin_cluster_count": bin_count,
                        "bin_response": bin_count / events,
                        "proxy_result": detector.proxy,
                    }
                )
            window_acceptance = window_count / cluster_count if cluster_count > 0 else 0.0
            mean_cluster_energy = (
                float(np.average(charge_energy_keV, weights=counts)) if cluster_count > 0 else np.nan
            )
            raw_cluster_response = cluster_count / events
            event_detection_efficiency = min(detected_event_count / events, 1.0)
            windowed_response = min(event_detection_efficiency * window_acceptance, event_detection_efficiency)
            # Approximate: treats windowed_response as a single k/n rate out of
            # `events` MC trials, rather than fully propagating through its three
            # constituent ratios. Good enough for a visual noise-vs-signal check.
            windowed_response_se = float(binomial_se(windowed_response, events))

            rows.append(
                {
                    "detector": detector.key,
                    "detector_label": detector.label,
                    "energy_keV": energy,
                    "bare_events": events,
                    "cluster_count": cluster_count,
                    "detected_event_count": detected_event_count,
                    "raw_cluster_response": raw_cluster_response,
                    "intrinsic_response": event_detection_efficiency,
                    "threshold_window_acceptance": window_acceptance,
                    "windowed_response": windowed_response,
                    "windowed_response_se": windowed_response_se,
                    "dominant_detector_energy_bin": dominant_bin,
                    "mean_cluster_energy_keV": mean_cluster_energy,
                    "proxy_result": detector.proxy,
                    "note": detector.note,
                    "root_file": str(root_path),
                }
            )

    if missing and allow_missing_root:
        print(f"WARNING: {len(missing)} bare-detector ROOT files are missing; response fields are NaN.")
    return pd.DataFrame(rows), pd.DataFrame(bin_rows)


def attenuation_table(spectrum: pd.DataFrame) -> pd.DataFrame:
    mu_data = MuData("nist_mu.dat")
    energies = spectrum["energy_keV"].to_numpy(dtype=float)
    rows: list[dict[str, object]] = []

    # G4_BRASS is appended as a reference material for the transport
    # validation only; it is not one of the five production alloys.
    for alloy in ALLOYS + [G4_BRASS]:
        mu_over_rho_mix = np.zeros_like(energies, dtype=float)
        for symbol, fraction in alloy.composition:
            mu_over_rho_mix += fraction * np.asarray(mu_data.get_mu_over_rho(ELEMENT_Z[symbol], energies), dtype=float)

        mu_linear = alloy.density_g_cm3 * mu_over_rho_mix
        transmission = np.exp(-mu_linear * alloy.thickness_cm)
        for energy, mu_rho, mu, trans in zip(energies, mu_over_rho_mix, mu_linear, transmission):
            rows.append(
                {
                    "alloy": alloy.key,
                    "alloy_label": alloy.label,
                    "energy_keV": energy,
                    "density_g_cm3": alloy.density_g_cm3,
                    "thickness_mm": alloy.thickness_mm,
                    "mu_over_rho_cm2_g": mu_rho,
                    "mu_linear_cm_inv": mu,
                    "transmission": trans,
                    "composition": "; ".join(f"{sym}:{frac:.4f}" for sym, frac in alloy.composition),
                }
            )

    return pd.DataFrame(rows)


def build_eiger2_alloy2_correction(validation: pd.DataFrame) -> pd.DataFrame:
    """EIGER2 is the only detector whose hard upper-threshold cliff makes the
    analytic Beer-Lambert x bare-response shortcut miss Compton-downscattered
    photons re-entering its high-efficiency window.

    correction_factor(E) = transport / analytic, where BOTH sides now describe
    the same G4_BRASS slab, so the factor isolates scatter + window physics
    (plus the near-contact slab-detector geometry) rather than mixing in the
    C36000-vs-G4_BRASS lead-content difference as the earlier pipeline did.
    The factor is applied to all five production alloys -- including alloy2,
    whose direct transport run measured G4_BRASS (9.07% Pb), not C36000, and
    therefore cannot be used as a production number for C36000 itself. The
    transplant to other copper-family alloys assumes the scatter effect is
    governed mainly by electron density; NOT independently validated per alloy.
    """
    eiger2 = validation[validation["detector"] == "eiger2"].copy()
    eiger2["correction_factor"] = np.where(
        eiger2["analytical_detected_fraction"] > 1e-12,
        eiger2["transport_detected_fraction"] / eiger2["analytical_detected_fraction"],
        1.0,
    )
    # Relative-variance addition for a ratio of two approximately independent
    # quantities. transport_detected_fraction and analytical_detected_fraction
    # share the same underlying bare-detector run indirectly, so this slightly
    # understates the true (correlated) uncertainty -- a labeled approximation,
    # not an exact propagation.
    rel_var_transport = (eiger2["transport_detected_fraction_se"] / eiger2["transport_detected_fraction"]) ** 2
    rel_var_analytical = (eiger2["analytical_detected_fraction_se"] / eiger2["analytical_detected_fraction"]) ** 2
    eiger2["correction_factor_se"] = eiger2["correction_factor"] * np.sqrt(
        rel_var_transport.fillna(0) + rel_var_analytical.fillna(0)
    )
    return eiger2.set_index("energy_keV")[
        [
            "transport_detected_fraction",
            "transport_detected_fraction_se",
            "analytical_detected_fraction",
            "analytical_detected_fraction_se",
            "correction_factor",
            "correction_factor_se",
        ]
    ]


def combine_results(
    spectrum: pd.DataFrame,
    response: pd.DataFrame,
    attenuation: pd.DataFrame,
    n0: int,
    eiger2_correction: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    per_energy_rows: list[dict[str, object]] = []
    energy_weights = spectrum.set_index("energy_keV")["weight"].to_dict()

    for detector in DETECTORS:
        det_response = response[response["detector"] == detector.key].set_index("energy_keV")
        for alloy in ALLOYS:
            alloy_att = attenuation[attenuation["alloy"] == alloy.key].set_index("energy_keV")
            for energy in spectrum["energy_keV"]:
                weight = energy_weights[energy]
                incident = n0 * weight
                trans = float(alloy_att.loc[energy, "transmission"])
                transmitted = incident * trans
                windowed_response = float(det_response.loc[energy, "windowed_response"])
                windowed_response_se = float(det_response.loc[energy, "windowed_response_se"])
                detected = transmitted * windowed_response if not math.isnan(windowed_response) else np.nan
                # trans is exact (Beer-Lambert); all uncertainty comes from windowed_response.
                detected_se = transmitted * windowed_response_se if not math.isnan(windowed_response_se) else np.nan
                detection_method = "analytic"

                if detector.key == "eiger2" and eiger2_correction is not None and energy in eiger2_correction.index:
                    correction_factor = float(eiger2_correction.loc[energy, "correction_factor"])
                    correction_factor_se = float(eiger2_correction.loc[energy, "correction_factor_se"])
                    if np.isfinite(correction_factor) and not math.isnan(detected):
                        # Relative-variance addition (approximate independence).
                        rel_var = 0.0
                        if windowed_response > 0 and np.isfinite(windowed_response_se):
                            rel_var += (windowed_response_se / windowed_response) ** 2
                        if correction_factor > 0 and np.isfinite(correction_factor_se):
                            rel_var += (correction_factor_se / correction_factor) ** 2
                        detected_se = detected * correction_factor * np.sqrt(rel_var) if rel_var > 0 else 0.0
                        detected = detected * correction_factor
                        detection_method = "g4brass_calibrated_correction"

                per_energy_rows.append(
                    {
                        "detector": detector.key,
                        "detector_label": detector.label,
                        "alloy": alloy.key,
                        "alloy_label": alloy.label,
                        "energy_keV": energy,
                        "spectrum_weight": weight,
                        "incident_bin": incident,
                        "transmission": trans,
                        "transmitted_bin": transmitted,
                        "intrinsic_detector_response": float(det_response.loc[energy, "intrinsic_response"]),
                        "threshold_window_acceptance": float(det_response.loc[energy, "threshold_window_acceptance"]),
                        "detected_bin": detected,
                        "detected_bin_se": detected_se,
                        "detection_method": detection_method,
                        "proxy_result": detector.proxy,
                    }
                )

    per_energy = pd.DataFrame(per_energy_rows)
    summary_rows: list[dict[str, object]] = []

    mean_incident_energy = float(np.average(spectrum["energy_keV"], weights=spectrum["weight"]))
    for (detector_key, alloy_key), group in per_energy.groupby(["detector", "alloy"], sort=False):
        transmitted_total = float(group["transmitted_bin"].sum())
        detected_total = float(group["detected_bin"].sum(skipna=False))
        # Energy bins treated as independent MC draws for this sum (a labeled
        # approximation -- see binomial_se docstring).
        detected_total_se = float(np.sqrt((group["detected_bin_se"] ** 2).sum())) if group["detected_bin_se"].notna().all() else np.nan
        mean_transmitted = (
            float(np.average(group["energy_keV"], weights=group["transmitted_bin"]))
            if transmitted_total > 0
            else np.nan
        )
        mean_detected = (
            float(np.average(group["energy_keV"], weights=group["detected_bin"]))
            if np.isfinite(detected_total) and detected_total > 0
            else np.nan
        )
        first = group.iloc[0]
        summary_rows.append(
            {
                "detector": detector_key,
                "detector_label": first["detector_label"],
                "alloy": alloy_key,
                "alloy_label": first["alloy_label"],
                "incident_total": n0,
                "transmitted_total": transmitted_total,
                "detected_total": detected_total,
                "detected_total_se": detected_total_se,
                "transmission_fraction": transmitted_total / n0,
                "detected_fraction_of_incident": detected_total / n0 if np.isfinite(detected_total) else np.nan,
                "detected_fraction_of_transmitted": detected_total / transmitted_total
                if np.isfinite(detected_total) and transmitted_total > 0
                else np.nan,
                "mean_incident_energy_keV": mean_incident_energy,
                "mean_transmitted_energy_keV": mean_transmitted,
                "mean_detected_energy_keV": mean_detected,
                "beam_hardening_shift_keV": mean_transmitted - mean_incident_energy,
                "proxy_result": bool(first["proxy_result"]),
                "detection_method": "/".join(sorted(group["detection_method"].unique())),
            }
        )

    summary = pd.DataFrame(summary_rows)
    return per_energy, summary


def combine_detector_bin_results(
    spectrum: pd.DataFrame,
    attenuation: pd.DataFrame,
    detector_bins: pd.DataFrame,
    n0: int,
    eiger2_correction: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Same G4_BRASS-calibrated EIGER2 correction as combine_results, applied
    uniformly across bins (there's no bin-resolved transport measurement to
    decompose it further, so this is the same documented approximation applied
    one level down)."""
    rows: list[dict[str, object]] = []
    weights = spectrum.set_index("energy_keV")["weight"].to_dict()

    for alloy in ALLOYS:
        alloy_att = attenuation[attenuation["alloy"] == alloy.key].set_index("energy_keV")
        for bin_row in detector_bins.itertuples(index=False):
            energy = float(bin_row.energy_keV)
            incident = n0 * weights[energy]
            transmission = float(alloy_att.loc[energy, "transmission"])
            transmitted = incident * transmission
            detected_in_bin = transmitted * float(bin_row.bin_response) if not math.isnan(float(bin_row.bin_response)) else np.nan
            detection_method = "analytic"

            if bin_row.detector == "eiger2" and eiger2_correction is not None and energy in eiger2_correction.index:
                correction_factor = float(eiger2_correction.loc[energy, "correction_factor"])
                if np.isfinite(correction_factor) and not math.isnan(detected_in_bin):
                    detected_in_bin = detected_in_bin * correction_factor
                    detection_method = "g4brass_calibrated_correction"

            rows.append(
                {
                    "detector": bin_row.detector,
                    "detector_label": bin_row.detector_label,
                    "alloy": alloy.key,
                    "alloy_label": alloy.label,
                    "energy_keV": energy,
                    "detector_energy_bin": int(bin_row.detector_energy_bin),
                    "bin_low_keV": float(bin_row.bin_low_keV),
                    "bin_high_keV": float(bin_row.bin_high_keV),
                    "incident_bin": incident,
                    "transmission": transmission,
                    "transmitted_bin": transmitted,
                    "detector_bin_response": float(bin_row.bin_response),
                    "detected_in_detector_bin": detected_in_bin,
                    "detection_method": detection_method,
                    "proxy_result": bool(bin_row.proxy_result),
                }
            )

    return pd.DataFrame(rows)


def transport_validation(
    spectrum: pd.DataFrame,
    response: pd.DataFrame,
    attenuation: pd.DataFrame,
    manifest: dict[tuple[str, str, float], int],
    data_dir: Path,
    validation_events_default: int,
    root_prefix: str = "mp",
) -> pd.DataFrame:
    """3-point spot-check (40/80/120 keV) for every detector, plus the full
    14-energy EIGER2 curve that its analytic-vs-transport gap (see
    eiger2_alloy2_transport_curve) requires.

    The analytic side of the comparison uses the G4_BRASS composition
    (9.07% Pb) because that is the material actually simulated in the
    transport runs. Comparing against C36000 (3% Pb) -- as an earlier
    version of this pipeline did -- conflates a factor 0.18-0.63x
    composition-driven transmission difference (above the Pb K-edge at
    88 keV) with the scatter/window physics the check is meant to isolate."""
    rows: list[dict[str, object]] = []
    alloy_att = attenuation[attenuation["alloy"] == "g4_brass"].set_index("energy_keV")

    for det in DETECTORS:
        response_idx = response[response["detector"] == det.key].set_index("energy_keV")
        energies = spectrum["energy_keV"].tolist() if det.key == "eiger2" else [40.0, 80.0, 120.0]
        for energy in energies:
            events = get_events(manifest, "transport", det.key, energy, validation_events_default)
            root_path = data_dir / root_file_name("transport", det.key, energy, root_prefix)
            analytical_transmission = float(alloy_att.loc[energy, "transmission"])
            bare_windowed_response = float(response_idx.loc[energy, "windowed_response"])
            bare_windowed_response_se = float(response_idx.loc[energy, "windowed_response_se"])
            analytical_detected_fraction = analytical_transmission * bare_windowed_response
            # trans is an exact Beer-Lambert value (no MC noise); all the
            # uncertainty comes from the bare-detector windowed_response.
            analytical_detected_fraction_se = analytical_transmission * bare_windowed_response_se

            row = {
                "detector": det.key,
                "alloy": "g4_brass",
                "energy_keV": energy,
                "validation_events": events,
                "analytical_transmission": analytical_transmission,
                "analytical_detected_fraction": analytical_detected_fraction,
                "analytical_detected_fraction_se": analytical_detected_fraction_se,
                "analytical_detected_counts": analytical_detected_fraction * events,
                "analytical_detected_counts_se": analytical_detected_fraction_se * events,
                "transport_detected_counts": np.nan,
                "transport_detected_counts_se": np.nan,
                "transport_detected_fraction": np.nan,
                "transport_detected_fraction_se": np.nan,
                "relative_difference_pct": np.nan,
                "root_file": str(root_path),
                "status": "missing_root",
            }

            if root_path.exists():
                transport_count = read_detected_event_count(root_path, det.root_detector)
                transport_fraction = transport_count / events
                transport_fraction_se = float(binomial_se(transport_fraction, events))
                analytical_detected_counts = analytical_detected_fraction * events
                rel_diff = (
                    100.0 * (transport_fraction - analytical_detected_fraction) / analytical_detected_fraction
                    if analytical_detected_counts >= 1.0
                    else np.nan
                )
                row.update(
                    {
                        "transport_detected_counts": transport_count,
                        "transport_detected_counts_se": transport_fraction_se * events,
                        "transport_detected_fraction": transport_fraction,
                        "transport_detected_fraction_se": transport_fraction_se,
                        "relative_difference_pct": rel_diff,
                        "status": "ok",
                    }
                )

            rows.append(row)

    return pd.DataFrame(rows)


def build_performance_evaluation(summary: pd.DataFrame, response: pd.DataFrame) -> pd.DataFrame:
    """Per-detector ranking table, derived directly from combined_results (summary)
    and detector_response so it can never drift out of sync with the rest of the
    pipeline the way the old hand-maintained performance_evaluation.csv did."""
    rows: list[dict[str, object]] = []
    for detector in DETECTORS:
        det_summary = summary[summary["detector"] == detector.key]
        det_response = response[response["detector"] == detector.key].set_index("energy_keV")

        detected = det_summary["detected_total"]
        best_row = det_summary.loc[det_summary["detected_total"].idxmax()]
        worst_row = det_summary.loc[det_summary["detected_total"].idxmin()]

        def response_at(energy: float) -> float:
            return float(det_response.loc[energy, "windowed_response"]) if energy in det_response.index else np.nan

        rows.append(
            {
                "detector": detector.key,
                "proxy_result": detector.proxy,
                "mean_detected_total": float(detected.mean()),
                "mean_detected_total_se": float(np.sqrt((det_summary["detected_total_se"] ** 2).sum())) / len(det_summary),
                "mean_detected_fraction_of_incident": float(det_summary["detected_fraction_of_incident"].mean()),
                "mean_detected_fraction_of_transmitted": float(
                    det_summary["detected_fraction_of_transmitted"].mean()
                ),
                "best_alloy_by_detected_total": best_row["alloy"],
                "best_detected_total": float(best_row["detected_total"]),
                "worst_alloy_by_detected_total": worst_row["alloy"],
                "worst_detected_total": float(worst_row["detected_total"]),
                "alloy_variation_cv": float(detected.std(ddof=0) / detected.mean()) if detected.mean() else np.nan,
                "response_60keV": response_at(60.0),
                "response_80keV": response_at(80.0),
                "response_120keV": response_at(120.0),
                "mean_raw_cluster_multiplicity_response": float(det_response["raw_cluster_response"].mean()),
                "mean_beam_hardening_shift_keV": float(det_summary["beam_hardening_shift_keV"].mean()),
                "detection_methods_used": "/".join(sorted(set(det_summary["detection_method"]))),
                "note": detector.note,
            }
        )

    performance = pd.DataFrame(rows)
    performance["rank_all_detectors_by_mean_detected"] = (
        performance["mean_detected_total"].rank(ascending=False, method="min").astype(int)
    )
    real_detectors = performance.loc[~performance["proxy_result"]].copy()
    real_detectors["rank_real_photon_counting_detectors"] = real_detectors["mean_detected_total"].rank(
        ascending=False, method="min"
    )
    performance = performance.merge(
        real_detectors[["detector", "rank_real_photon_counting_detectors"]], on="detector", how="left"
    )
    return performance.sort_values("rank_all_detectors_by_mean_detected").reset_index(drop=True)


def build_alloy_discrimination(summary: pd.DataFrame) -> pd.DataFrame:
    """Pairwise material-discrimination CNR between alloys, per detector.

    combined_results.csv answers "which detector-alloy combo detects the most
    photons" (figure 4/5); this answers the more directly useful inspection
    question, "can this detector tell alloy A from alloy B apart at all."
    CNR = |N_a - N_b| / sqrt(N_a + N_b), a standard Poisson-limited
    contrast-to-noise formula using each alloy's detected_total as the signal
    and combined shot noise as the reference noise. Electronic noise is not
    included, so this is an upper bound on achievable discrimination, not a
    full detector-noise model.
    """
    rows: list[dict[str, object]] = []
    for detector in DETECTORS:
        det_summary = summary[summary["detector"] == detector.key].set_index("alloy")
        for alloy_a, alloy_b in itertools.combinations(ALLOYS, 2):
            n_a = float(det_summary.loc[alloy_a.key, "detected_total"])
            n_b = float(det_summary.loc[alloy_b.key, "detected_total"])
            cnr = abs(n_a - n_b) / math.sqrt(n_a + n_b) if (n_a + n_b) > 0 else np.nan
            rows.append(
                {
                    "detector": detector.key,
                    "detector_label": detector.label,
                    "alloy_a": alloy_a.key,
                    "alloy_b": alloy_b.key,
                    "detected_total_a": n_a,
                    "detected_total_b": n_b,
                    "cnr": cnr,
                    "proxy_result": detector.proxy,
                }
            )
    return pd.DataFrame(rows)


def write_spectrum_summary(spectrum: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    mean_energy = float(np.average(spectrum["energy_keV"], weights=spectrum["weight"]))
    peak_energy = float(spectrum.loc[spectrum["weight"].idxmax(), "energy_keV"])
    summary = pd.DataFrame(
        [
            {
                "weights_sum": spectrum["weight"].sum(),
                "mean_energy_keV": mean_energy,
                "peak_energy_keV": peak_energy,
                "energy_count": len(spectrum),
            }
        ]
    )
    summary.to_csv(out_dir / "spectrum_summary.csv", index=False)
    return summary


def save_plots(
    spectrum: pd.DataFrame,
    response: pd.DataFrame,
    attenuation: pd.DataFrame,
    per_energy: pd.DataFrame,
    summary: pd.DataFrame,
    validation: pd.DataFrame,
    out_dir: Path,
) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(spectrum["energy_keV"], spectrum["weight"], width=7, color="#3b6ea8")
    ax.set_title("150 kVp source spectrum weights")
    ax.set_xlabel("Energy (keV)")
    ax.set_ylabel("Relative weight")
    fig.tight_layout()
    fig.savefig(out_dir / "source_spectrum.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    for alloy in ALLOYS:
        data = attenuation[attenuation["alloy"] == alloy.key]
        ax.plot(data["energy_keV"], data["transmission"], marker="o", label=alloy.key)
    ax.set_title("Analytical alloy transmission, 5 mm thickness")
    ax.set_xlabel("Energy (keV)")
    ax.set_ylabel("Transmission")
    ax.set_yscale("log")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "alloy_transmission.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    for detector in DETECTORS:
        data = response[response["detector"] == detector.key]
        ax.errorbar(
            data["energy_keV"], data["windowed_response"], yerr=data["windowed_response_se"],
            marker="o", capsize=2, label=detector.key,
        )
    ax.set_title("Bare-detector windowed response (error bars: binomial SE, 10k-event MC)")
    ax.set_xlabel("Energy (keV)")
    ax.set_ylabel("Detected clusters per incident photon")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "detector_response.png", dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharex=True)
    for ax, detector in zip(axes.ravel(), DETECTORS):
        subset = per_energy[per_energy["detector"] == detector.key]
        for alloy in ALLOYS:
            data = subset[subset["alloy"] == alloy.key]
            ax.plot(data["energy_keV"], data["detected_bin"], marker="o", label=alloy.key)
        ax.set_title(detector.label)
        ax.set_ylabel("Detected photons/bin")
    for ax in axes[-1, :]:
        ax.set_xlabel("Energy (keV)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=5)
    fig.suptitle("Detected spectra after alloy attenuation")
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
    fig.savefig(out_dir / "detected_spectra.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    pivot = summary.pivot(index="alloy", columns="detector", values="beam_hardening_shift_keV")
    pivot.plot(kind="bar", ax=ax)
    ax.set_title("Beam hardening shift")
    ax.set_xlabel("Alloy")
    ax.set_ylabel("Mean transmitted energy shift (keV)")
    ax.legend(title="Detector")
    fig.tight_layout()
    fig.savefig(out_dir / "beam_hardening.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.8))
    ranking = summary.sort_values("detected_total", ascending=False)
    labels = [f"{row.detector}\n{row.alloy}" for row in ranking.itertuples()]
    colors = ["#9a6b24" if row.proxy_result else "#2f7f74" for row in ranking.itertuples()]
    ax.bar(labels, ranking["detected_total"], yerr=ranking["detected_total_se"], capsize=3, color=colors)
    ax.set_title("Detector-alloy ranking by detected photons (error bars: propagated binomial SE)")
    ax.set_ylabel("Detected photons, N0=1,000,000")
    ax.tick_params(axis="x", labelrotation=75)
    fig.tight_layout()
    fig.savefig(out_dir / "detector_alloy_ranking.png", dpi=180)
    plt.close(fig)

    if not validation.empty:
        fig, axes = plt.subplots(1, len(DETECTORS), figsize=(4.0 * len(DETECTORS), 4.5), sharey=False)
        width = 0.35
        for ax, detector in zip(np.atleast_1d(axes), DETECTORS):
            subset = validation[validation["detector"] == detector.key]
            x = np.arange(len(subset))
            ax.bar(
                x - width / 2, subset["analytical_detected_counts"], width,
                yerr=subset["analytical_detected_counts_se"], capsize=2, label="analytical",
            )
            ax.bar(
                x + width / 2, subset["transport_detected_counts"], width,
                yerr=subset["transport_detected_counts_se"], capsize=2, label="transport",
            )
            ax.set_xticks(x, [f"{e:.0f} keV" for e in subset["energy_keV"]])
            ax.set_title(detector.label)
            ax.set_ylabel("Detected counts")
        axes_list = np.atleast_1d(axes)
        handles, labels = axes_list[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=2)
        fig.suptitle("Alloy 2 transport cross-check, all detectors (error bars: binomial SE)")
        fig.tight_layout(rect=(0, 0.08, 1, 0.95))
        fig.savefig(out_dir / "transport_validation.png", dpi=180)
        plt.close(fig)


def validate_outputs(
    spectrum: pd.DataFrame,
    response: pd.DataFrame,
    detector_bins: pd.DataFrame,
    per_energy: pd.DataFrame,
    summary: pd.DataFrame,
    validation: pd.DataFrame,
    discrimination: pd.DataFrame,
) -> pd.DataFrame:
    checks = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    add("spectrum_weights_sum_to_1", np.isclose(spectrum["weight"].sum(), 1.0, atol=1e-5), f"{spectrum['weight'].sum():.8f}")
    peak = spectrum.loc[spectrum["weight"].idxmax(), "energy_keV"]
    mean = np.average(spectrum["energy_keV"], weights=spectrum["weight"])
    add("spectrum_peak_and_mean_from_make_spectrum", True, f"peak={peak:.1f} keV, mean={mean:.1f} keV")
    missing_response = int(response["windowed_response"].isna().sum())
    add(
        "bare_detector_responses_present",
        missing_response == 0,
        f"{missing_response} missing response rows out of {len(response)}",
    )
    expected_bin_rows = len(spectrum) * sum(detector.bins for detector in DETECTORS)
    add(
        "detector_energy_bin_logic_present",
        len(detector_bins) == expected_bin_rows,
        f"{len(detector_bins)} detector-bin rows, expected {expected_bin_rows}",
    )
    add(
        "transmitted_never_exceeds_incident",
        bool((per_energy["transmitted_bin"] <= per_energy["incident_bin"] + 1e-9).all()),
        "checked all per-energy bins",
    )
    # EIGER2 rows using direct transport or the alloy2-calibrated correction are
    # deliberately allowed to exceed the analytic Beer-Lambert "transmitted_bin"
    # figure: that figure only counts zero-interaction photons, while transport
    # (correctly) also counts Compton-downscattered photons that still reach the
    # detector. This check is only meaningful for the pure-analytic rows.
    analytic_rows = per_energy["detection_method"] == "analytic"
    finite_detected = per_energy["detected_bin"].notna() & analytic_rows
    detected_ok = (
        per_energy.loc[finite_detected, "detected_bin"]
        <= per_energy.loc[finite_detected, "transmitted_bin"] + 1e-9
    ).all()
    add(
        "detected_never_exceeds_transmitted",
        bool(detected_ok),
        f"checked {int(finite_detected.sum())} analytic-method per-energy bins "
        f"({int((~analytic_rows).sum())} EIGER2 transport/corrected rows exempted by design)",
    )
    add(
        "beam_hardening_nonnegative",
        bool((summary["beam_hardening_shift_keV"] >= -1e-9).all()),
        "attenuating alloys should shift mean transmitted energy upward",
    )
    add("all_20_detector_alloy_combinations_present", len(summary) == 20, f"{len(summary)} combinations")
    add(
        "hexitec_labelled_as_proxy",
        bool(summary[summary["detector"] == "hexitec_proxy"]["proxy_result"].all()),
        "HEXITEC rows carry proxy_result=True",
    )
    if not validation.empty:
        non_eiger2_detectors = len(DETECTORS) - 1
        expected_validation_rows = non_eiger2_detectors * 3 + len(spectrum)
        add(
            "transport_validation_rows_present",
            len(validation) == expected_validation_rows,
            f"{len(validation)} rows, expected {expected_validation_rows} "
            f"({non_eiger2_detectors} detectors x 3 spot-check energies + {len(spectrum)}-energy EIGER2 curve)",
        )
        missing_transport = int((validation["status"] != "ok").sum())
        add(
            "transport_validation_roots_present",
            missing_transport == 0,
            f"{missing_transport} missing transport rows out of {len(validation)}",
        )
        eiger2_corrected = per_energy[per_energy["detector"] == "eiger2"]
        add(
            "eiger2_all_alloys_use_g4brass_calibrated_correction",
            bool((eiger2_corrected["detection_method"] == "g4brass_calibrated_correction").all()),
            "All EIGER2 alloys must use the G4_BRASS-calibrated correction "
            "(the direct transport run measured G4_BRASS, not C36000, so it is calibration -- not production -- data)",
        )
    expected_discrimination_rows = len(DETECTORS) * len(list(itertools.combinations(ALLOYS, 2)))
    add(
        "alloy_discrimination_rows_present",
        len(discrimination) == expected_discrimination_rows and discrimination["cnr"].notna().all(),
        f"{len(discrimination)} rows, expected {expected_discrimination_rows}",
    )
    return pd.DataFrame(checks)


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.uniform_thickness_mm is not None:
        from dataclasses import replace

        globals()["DETECTORS"] = [
            replace(
                det,
                thickness_mm=args.uniform_thickness_mm,
                label=f"{det.label} ({args.uniform_thickness_mm:.2f} mm uniform)",
                note=f"UNIFORM-THICKNESS RERUN: sensor set to {args.uniform_thickness_mm:.2f} mm CdTe. {det.note}",
            )
            for det in DETECTORS
        ]

    if args.medipix3_upper_kev is not None:
        from dataclasses import replace

        globals()["DETECTORS"] = [
            replace(
                det,
                upper_threshold_keV=args.medipix3_upper_kev,
                label=f"{det.label} [upper window {args.medipix3_upper_kev:.0f} keV]",
                note=f"WINDOW SENSITIVITY VARIANT: Medipix3 upper window set to {args.medipix3_upper_kev:.0f} keV "
                f"(analysis-level cut; same ROOT files as the standard run). {det.note}",
            )
            if det.key == "medipix3"
            else det
            for det in DETECTORS
        ]

    spectrum = load_spectrum(args.spectrum)
    manifest = load_manifest(args.manifest)
    spectrum_summary = write_spectrum_summary(spectrum, args.out_dir)

    response, detector_bins = read_detector_response(
        spectrum=spectrum,
        manifest=manifest,
        data_dir=args.data_dir,
        bare_events_default=args.bare_events,
        allow_missing_root=args.allow_missing_root,
        root_prefix=args.root_prefix,
    )
    attenuation = attenuation_table(spectrum)
    validation = transport_validation(
        spectrum=spectrum,
        response=response,
        attenuation=attenuation,
        manifest=manifest,
        data_dir=args.data_dir,
        validation_events_default=args.validation_events,
        root_prefix=args.root_prefix,
    )
    eiger2_correction = build_eiger2_alloy2_correction(validation)
    per_energy, summary = combine_results(spectrum, response, attenuation, args.n0, eiger2_correction)
    detector_bin_results = combine_detector_bin_results(
        spectrum, attenuation, detector_bins, args.n0, eiger2_correction
    )
    performance = build_performance_evaluation(summary, response)
    discrimination = build_alloy_discrimination(summary)
    checks = validate_outputs(spectrum, response, detector_bins, per_energy, summary, validation, discrimination)

    response.to_csv(args.out_dir / "detector_response.csv", index=False)
    detector_bins.to_csv(args.out_dir / "detector_energy_bin_response.csv", index=False)
    attenuation.to_csv(args.out_dir / "alloy_attenuation.csv", index=False)
    per_energy.to_csv(args.out_dir / "per_energy_results.csv", index=False)
    detector_bin_results.to_csv(args.out_dir / "per_detector_energy_bin_results.csv", index=False)
    summary.to_csv(args.out_dir / "combined_results.csv", index=False)
    validation.to_csv(args.out_dir / "transport_validation.csv", index=False)
    performance.to_csv(args.out_dir / "performance_evaluation.csv", index=False)
    discrimination.to_csv(args.out_dir / "alloy_discrimination_cnr.csv", index=False)
    checks.to_csv(args.out_dir / "validation_checks.csv", index=False)

    save_plots(spectrum, response, attenuation, per_energy, summary, validation, args.out_dir)

    print(f"Wrote outputs to {args.out_dir}")
    print(
        "Spectrum:",
        f"peak={spectrum_summary.loc[0, 'peak_energy_keV']:.1f} keV,",
        f"mean={spectrum_summary.loc[0, 'mean_energy_keV']:.1f} keV",
    )
    failed = checks[~checks["passed"]]
    if failed.empty:
        print("Validation checks passed.")
    else:
        print("Validation checks with warnings/failures:")
        print(failed.to_string(index=False))


if __name__ == "__main__":
    main()
