"""Deposited-energy spectra at the resolution Allpix actually wrote them.

Why this module exists
----------------------
Every run's `charge/cluster_charge` histogram carries 1000 bins at 221.5 eV.
Both production pipelines reduce that entire spectrum to a single scalar -- the
window acceptance fraction -- so 168 runs x 1000 bins become the 30 numbers of
Phase 2's Table 10. Nothing wrong with the 30 numbers; the problem is that the
evidence behind them is discarded, and the study's central claim (that theory
and simulation diverge because the window cuts on DEPOSITED rather than photon
energy) rests on a distribution that is never shown.

This module publishes that distribution, unrebinned, plus the per-detector
sub-bin structure Phase 2 declares and then throws away
(`phase2_selection_experiment.bare_windowed_response` computes
`np.linspace(lower, upper, bins + 1)` and reads only the first and last edge).

Binning semantics are mirrored exactly from
`material_penetration_experiment.read_detector_response`: sub-bins are half-open
[low, high) except the last, which is closed [low, high]. Their union is
therefore exactly the single window Phase 2 uses, which is what makes the two
reconcilable.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

import analysis.scripts.material_penetration_experiment as _mpe
from analysis.viz import registry as reg
from analysis.viz.detectors import DetectorSpec
from analysis.viz.runreader import RunData, read_run_or_none

EPSILON_CDTE_EV = _mpe.EPSILON_CDTE_EV
CLUSTER_CHARGE_KEY = "charge/cluster_charge"


def detector_bin_edges(det: DetectorSpec) -> list[tuple[int, float, float]]:
    """Per-detector sub-bins, identical to Study A's detector_bin_ranges().

    Kept as a separate function rather than calling the Study A one because that
    takes a Study A `Detector` dataclass; the arithmetic is asserted equal in
    tests/test_spectra.py.
    """
    edges = np.linspace(det.lower_keV, det.upper_keV, det.bins + 1)
    return [(i + 1, float(edges[i]), float(edges[i + 1])) for i in range(det.bins)]


def _bin_mask(deposited_keV: np.ndarray, index: int, low: float, high: float,
              n_bins: int) -> np.ndarray:
    """Half-open [low, high) except the last bin, which is closed."""
    if index == n_bins:
        return (deposited_keV >= low) & (deposited_keV <= high)
    return (deposited_keV >= low) & (deposited_keV < high)


def deposited_spectrum(run: RunData, det: DetectorSpec | None = None) -> pd.DataFrame:
    """Native-resolution deposited-energy spectrum for one run.

    One row per ROOT bin -- 1000 of them at 221.5 eV -- never rebinned.
    Rebinning is the thing this module exists to stop doing.
    """
    h = run.hists.get(CLUSTER_CHARGE_KEY)
    if h is None:
        return pd.DataFrame()

    edges_ke = h.axes[0].edges
    low_ke, high_ke = edges_ke[:-1], edges_ke[1:]
    centre_ke = (low_ke + high_ke) / 2.0
    counts = np.asarray(h.values, dtype=float)
    errors = (np.asarray(h.errors, dtype=float) if h.errors is not None
              else np.sqrt(np.clip(counts, 0, None)))

    deposited = centre_ke * EPSILON_CDTE_EV
    frame = pd.DataFrame({
        "run_id": run.key.run_id if run.key else run.root_path.stem,
        "detector": run.key.detector if run.key else "",
        "beam_energy_keV": run.key.energy_keV if run.key else np.nan,
        "bin_index": np.arange(len(counts), dtype=int),
        "charge_ke_low": low_ke,
        "charge_ke_high": high_ke,
        "charge_ke_center": centre_ke,
        "deposited_keV_low": low_ke * EPSILON_CDTE_EV,
        "deposited_keV_high": high_ke * EPSILON_CDTE_EV,
        "deposited_keV_center": deposited,
        "counts": counts,
        "error": errors,
    })

    if det is None:
        frame["in_window"] = pd.NA
        frame["detector_energy_bin"] = pd.NA
        return frame

    bins = detector_bin_edges(det)
    frame["in_window"] = (deposited >= det.lower_keV) & (deposited <= det.upper_keV)
    sub = np.full(len(counts), 0, dtype=int)
    for index, lo, hi in bins:
        sub[_bin_mask(deposited, index, lo, hi, det.bins)] = index
    frame["detector_energy_bin"] = sub          # 0 = outside the counting window
    return frame


def binned_response(run: RunData, det: DetectorSpec, n_events: float) -> pd.DataFrame:
    """Response resolved into the detector's declared sub-bins.

    This is the Phase 2 equivalent of Study A's detector_energy_bin_response.csv,
    with the same column names so the two campaigns can be compared directly.

    Note the normalisation, which is Study A's and is easy to misread:
    `bin_response` is per EVENT (bin_count / n_events) while the window
    acceptance that feeds Table 10 is per CLUSTER (window_count / cluster_count).
    They are therefore not directly summable -- see reconcile().
    """
    h = run.hists.get(CLUSTER_CHARGE_KEY)
    if h is None or not n_events:
        return pd.DataFrame()

    counts = np.asarray(h.values, dtype=float)
    deposited = h.axes[0].centers * EPSILON_CDTE_EV
    rows = []
    for index, lo, hi in detector_bin_edges(det):
        mask = _bin_mask(deposited, index, lo, hi, det.bins)
        bin_count = float(np.nansum(counts[mask]))
        rows.append({
            "run_id": run.key.run_id if run.key else run.root_path.stem,
            "detector": det.key,
            "detector_label": det.label,
            "energy_keV": run.key.energy_keV if run.key else np.nan,
            "detector_energy_bin": index,
            "bin_low_keV": lo,
            "bin_high_keV": hi,
            "bin_cluster_count": bin_count,
            "bin_response": bin_count / n_events,
            "proxy_result": det.proxy,
        })
    return pd.DataFrame(rows)


def reconcile(run: RunData, det: DetectorSpec, n_events: float) -> dict:
    """Check the sub-bins reproduce the single window Table 10 actually used.

    The invariant is NOT `sum(bin_response) == windowed_response`, because the
    two are normalised differently (per event vs per cluster). The correct
    relation is

        windowed_response = (detected / n_events) * (window_count / cluster_count)
        sum(bin_response) = window_count / n_events

    so

        windowed_response = sum(bin_response) * n_events / cluster_count
                                              * detected / n_events
                          = sum(bin_response) * detected / cluster_count

    A mismatch here means the sub-bin decomposition does not cover the window,
    which would be a real defect. It is not a reason to change Table 10.
    """
    h = run.hists.get(CLUSTER_CHARGE_KEY)
    ev = run.hists.get("event_size_clusters")
    if h is None or ev is None or not n_events:
        return {"status": "insufficient_data"}

    counts = np.asarray(h.values, dtype=float)
    cluster_count = float(np.nansum(counts))
    detected = float(np.nansum(ev.values))
    deposited = h.axes[0].centers * EPSILON_CDTE_EV

    window_mask = (deposited >= det.lower_keV) & (deposited <= det.upper_keV)
    window_count = float(np.nansum(counts[window_mask]))

    sub = binned_response(run, det, n_events)
    sub_count = float(sub.bin_cluster_count.sum()) if not sub.empty else math.nan
    sub_response_sum = float(sub.bin_response.sum()) if not sub.empty else math.nan

    window_acceptance = window_count / cluster_count if cluster_count else math.nan
    intrinsic = min(detected / n_events, 1.0)
    windowed_response = min(intrinsic * window_acceptance, intrinsic)
    from_subbins = (sub_response_sum * detected / cluster_count
                    if cluster_count else math.nan)

    return {
        "run_id": run.key.run_id if run.key else run.root_path.stem,
        "detector": det.key,
        "energy_keV": run.key.energy_keV if run.key else math.nan,
        "n_bins_declared": det.bins,
        "cluster_count": cluster_count,
        "detected_events": detected,
        "window_count": window_count,
        "subbin_count": sub_count,
        "count_match": bool(np.isclose(window_count, sub_count, rtol=0, atol=1e-9)),
        "windowed_response": windowed_response,
        "windowed_response_from_subbins": from_subbins,
        "response_match": bool(np.isclose(windowed_response, from_subbins,
                                          rtol=1e-12, atol=0)),
        "subbin_response_sum": sub_response_sum,
    }


def campaign_spectra(campaign: str, *, data_dir: Path | None = None,
                     detector_source: str | None = None,
                     drop_empty_bins: bool = True,
                     progress: bool = False) -> dict[str, pd.DataFrame]:
    """Build every spectral product for one campaign.

    `drop_empty_bins` removes bins with zero counts from the long-format export.
    It is NOT rebinning: every surviving row keeps its native 221.5 eV width and
    its original bin_index, so the full grid is reconstructible. Typically ~344
    of 1000 bins are occupied, so this cuts the export ~3x with no loss.
    """
    from analysis.viz.detectors import resolve

    spec = reg.CAMPAIGNS[campaign]
    source = detector_source or spec.detector_source
    disc = reg.discover(data_dir, campaign)

    spectra, responses, checks = [], [], []
    for i, key in enumerate(sorted(disc.runs, key=reg.sort_key)):
        if progress and i % 20 == 0:
            print(f"  {i}/{len(disc.runs)} ...", flush=True)
        run = read_run_or_none(reg.root_path(key, data_dir))
        if run is None or run.is_empty:
            continue
        det = resolve(key.detector, source)
        n_events = float(run.hists["event_size_pixels"].entries) if \
            "event_size_pixels" in run.hists else float(_mpe.DEFAULT_BARE_EVENTS)

        s = deposited_spectrum(run, det)
        if not s.empty:
            if drop_empty_bins:
                s = s[s.counts > 0]
            spectra.append(s)
        if det is not None:
            r = binned_response(run, det, n_events)
            if not r.empty:
                responses.append(r)
            checks.append(reconcile(run, det, n_events))

    return {
        "deposited_spectrum": (pd.concat(spectra, ignore_index=True)
                               if spectra else pd.DataFrame()),
        "detector_energy_bin_response": (pd.concat(responses, ignore_index=True)
                                         if responses else pd.DataFrame()),
        "reconciliation": pd.DataFrame(checks),
    }


# ---------------------------------------------------------------------------
# Spectrum-weighted deposited spectra (the "detected_energy_spectrum" family)
# ---------------------------------------------------------------------------

def weighted_deposited_spectrum(campaign: str, *, alloy: str = "alloy1",
                                thickness_tag: str = "",
                                bin_keV: float = 2.0,
                                grid_start_keV: float = 1.0,
                                n_bins: int | None = None,
                                apply_window: bool = True,
                                n0: float = 1_000_000.0,
                                default_events: float = 10_000.0,
                                data_dir: Path | None = None,
                                detector_source: str = "phase2") -> pd.DataFrame:
    """Deposited-energy spectrum summed over the beam spectrum, per detector.

        value(d, bin) = N0 * sum_E w(E) * T_alloy(E) * counts(d, E, bin) / n_events

    `apply_window` is the parameter that matters. With it False the result
    counts every deposit in the sensor, including those the chip's discriminator
    would reject -- for a tight-window chip like EIGER2 that inflates the total
    roughly 3x (18,442 unwindowed vs ~6,000 windowed). A file produced with
    apply_window=False is NOT "detected" counts and must not be read as such.

    This function exists because
    `phase2_selection_framework/data_csv/detected_energy_spectrum.csv` had no
    generator anywhere in the repo. It is reproduced here bit-for-bit with
    apply_window=False, thickness_tag="" -- see reproduce_legacy_spectrum().
    """
    from analysis.viz.detectors import resolve

    weights_df = pd.read_csv(reg.REPO_ROOT / "spectra/150kvp_weights.csv")
    weights = dict(zip(weights_df.energy_keV.astype(float), weights_df.weight))

    att = pd.read_csv(reg.REPO_ROOT / "analysis/results/material_penetration_uniform"
                      / "alloy_attenuation.csv")
    trans = att[att.alloy == alloy].set_index("energy_keV").transmission.to_dict()

    disc = reg.discover(data_dir, campaign)
    detector_keys, seen = [], set()
    for key in sorted(disc.runs, key=reg.sort_key):
        if key.detector not in seen:
            seen.add(key.detector)
            detector_keys.append(key.detector)

    if n_bins is None:
        n_bins = 79
    grid = grid_start_keV + bin_keV * np.arange(n_bins)
    edges = np.append(grid - bin_keV / 2.0, grid[-1] + bin_keV / 2.0)

    out: dict[str, np.ndarray] = {}
    for det_key in detector_keys:
        det = resolve(det_key, detector_source)
        if det is None:
            continue
        total = np.zeros(len(grid))
        for energy in sorted(weights):
            name = f"p2_bare_{det_key}{thickness_tag}_{energy:.0f}keV"
            key = reg.parse_name(name)
            if key is None:
                continue
            run = read_run_or_none(reg.root_path(key, data_dir))
            if run is None or run.is_empty:
                continue
            events = (float(run.hists["event_size_pixels"].entries)
                      if "event_size_pixels" in run.hists else default_events)
            frame = deposited_spectrum(run, det)
            if frame.empty:
                continue
            if apply_window:
                frame = frame[frame.in_window == True]  # noqa: E712
            hist, _ = np.histogram(frame.deposited_keV_center, bins=edges,
                                   weights=frame.counts)
            total += n0 * weights[energy] * trans[energy] * hist / events
        out[det.label.split(maxsplit=1)[-1] if " " in det.label else det.label] = total

    result = pd.DataFrame({"deposited_keV": grid})
    for label, values in out.items():
        result[label] = values
    return result


def reproduce_legacy_spectrum(data_dir: Path | None = None) -> pd.DataFrame:
    """Regenerate the previously-orphaned detected_energy_spectrum.csv.

    Verified bit-identical (max |diff| ~1e-12) to the file that was sitting in
    data_csv with no generator. Settings recovered by reconstruction, not by
    documentation, because none existed:
      alloy1 (pure Cu), untagged 1 mm ROOTs, 2 keV bins on a 1,3,5,... grid,
      79 bins, N0 = 1e6, and NO energy window.
    """
    legacy_names = {"medipix3": "Medipix3", "medipix4": "Medipix4",
                    "timepix3_cdte": "Timepix3", "timepix4": "Timepix4",
                    "eiger2": "EIGER2", "hexitec_proxy": "HEXITEC"}
    frame = weighted_deposited_spectrum(
        "phase2_selection", alloy="alloy1", thickness_tag="",
        bin_keV=2.0, grid_start_keV=1.0, n_bins=79,
        apply_window=False, data_dir=data_dir)
    # Legacy column order and short labels.
    from analysis.viz.detectors import resolve
    rename = {}
    for key, short in legacy_names.items():
        det = resolve(key, "phase2")
        if det is None:
            continue
        current = det.label.split(maxsplit=1)[-1] if " " in det.label else det.label
        rename[current] = short
    frame = frame.rename(columns=rename)
    cols = ["deposited_keV"] + [legacy_names[k] for k in
                                ["medipix3", "medipix4", "timepix3_cdte",
                                 "timepix4", "eiger2", "hexitec_proxy"]
                                if legacy_names[k] in frame.columns]
    return frame[cols]
