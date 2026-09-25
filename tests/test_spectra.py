"""Spectral-resolution contracts.

The point of this module is that no number is silently rebinned or silently
renormalised, so the tests are mostly about exactness and about units.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import analysis.scripts.material_penetration_experiment as mpe
from analysis.viz import detectors as D
from analysis.viz import registry as reg
from analysis.viz.runreader import read_run_or_none
from analysis.viz.spectra import (binned_response, deposited_spectrum,
                                  detector_bin_edges, reconcile,
                                  reproduce_legacy_spectrum)

SAMPLE = "p2_bare_medipix3_100keV"
pytestmark = pytest.mark.skipif(
    not (reg.DATA_DIR / f"{SAMPLE}.root").exists(), reason="ROOT files absent")


@pytest.fixture(scope="module")
def run():
    return read_run_or_none(reg.root_path(reg.parse_name(SAMPLE)))


@pytest.fixture(scope="module")
def det():
    return D.resolve("medipix3", "phase2")


def test_spectrum_is_native_resolution(run, det):
    """1000 bins at 221.5 eV. If this ever shrinks, something rebinned."""
    s = deposited_spectrum(run, det)
    assert len(s) == 1000
    width = (s.deposited_keV_high - s.deposited_keV_low).iloc[0]
    assert width == pytest.approx(0.2215, abs=1e-4)


def test_spectrum_counts_match_the_raw_histogram(run, det):
    s = deposited_spectrum(run, det)
    assert np.array_equal(s.counts.values, run.hists["charge/cluster_charge"].values)


def test_bin_edges_match_study_a_exactly():
    """Phase 2 and Study A must not disagree about where a bin starts."""
    for key in ("medipix3", "eiger2", "timepix3_cdte", "hexitec_proxy"):
        study_a = next(d for d in mpe.DETECTORS if d.key == key)
        mine = detector_bin_edges(
            D.DetectorSpec(key, study_a.label, study_a.lower_threshold_keV,
                           study_a.upper_threshold_keV, study_a.bins,
                           study_a.proxy, "study_a", ""))
        assert mine == mpe.detector_bin_ranges(study_a)


def test_subbins_partition_the_window(run, det):
    """Union of the sub-bins is exactly the single window Phase 2 uses."""
    r = reconcile(run, det, 10_000.0)
    assert r["count_match"]
    assert r["window_count"] == r["subbin_count"]


def test_subbins_reproduce_the_table10_response(run, det):
    """Not a naive sum: bin_response is per event, window acceptance per cluster."""
    r = reconcile(run, det, 10_000.0)
    assert r["response_match"]
    assert r["windowed_response"] == pytest.approx(
        r["windowed_response_from_subbins"], rel=1e-12)


def test_response_matches_production_pipeline(run, det):
    import analysis.scripts.phase2_selection_experiment as p2
    p2det = next(d for d in p2.DETS if d.key == "medipix3")
    expected, _ = p2.bare_windowed_response(p2det, 1.0, 100.0, 10000)
    assert reconcile(run, det, 10_000.0)["windowed_response"] == pytest.approx(
        expected, rel=1e-12)


def test_bin_response_normalisation_is_per_event(run, det):
    """Guards the units. bin_response = bin_count / n_events, NOT / cluster_count."""
    b = binned_response(run, det, 10_000.0)
    assert np.allclose(b.bin_response, b.bin_cluster_count / 10_000.0)


def test_phase2_bins_are_declared_but_unused_upstream():
    """Documents the defect this module works around.

    phase2_selection_experiment declares bins=2 and then reads only the outer
    edges. If that is ever fixed upstream, this test fails and the workaround
    can be reconsidered deliberately.
    """
    import inspect

    import analysis.scripts.phase2_selection_experiment as p2
    src = inspect.getsource(p2.bare_windowed_response)
    assert "linspace(det.lower_keV, det.upper_keV, det.bins + 1)" in src
    assert "edges[0]" in src and "edges[-1]" in src
    assert all(d.bins == 2 for d in p2.DETS)


class TestLegacyOrphan:
    """detected_energy_spectrum.csv had no generator anywhere in the repo."""

    LEGACY = (reg.REPO_ROOT / "analysis/results/phase2_selection_framework"
              / "data_csv/detected_energy_spectrum.csv")

    @pytest.mark.skipif(not LEGACY.exists(), reason="legacy file removed")
    def test_reproduced_bit_for_bit(self):
        original = pd.read_csv(self.LEGACY)
        mine = reproduce_legacy_spectrum()
        assert list(mine.columns) == list(original.columns)
        assert np.nanmax(np.abs(mine[original.columns].values
                                - original.values)) < 1e-6

    @pytest.mark.skipif(not LEGACY.exists(), reason="legacy file removed")
    def test_legacy_file_is_unwindowed(self):
        """The recovered settings include apply_window=False, which is why the
        file must not be read as 'detected' counts: EIGER2 is inflated ~3x."""
        original = pd.read_csv(self.LEGACY)
        # EIGER2 unwindowed lands on the unrestricted theoretical total.
        assert original.EIGER2.sum() == pytest.approx(18442, abs=5)
