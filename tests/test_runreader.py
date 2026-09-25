"""Reader contracts, including the uproot-version tripwires.

If a future uproot fixes the TProfile/TProfile2D bugs, the two tripwire tests
fail. That is deliberate: the workaround in runreader must then be removed on
purpose, rather than silently shifting every profile bin by one.
"""
from __future__ import annotations

import numpy as np
import pytest
import uproot

from analysis.viz import registry as reg
from analysis.viz.runreader import read_run

SAMPLE = reg.DATA_DIR / "p2_bare_medipix3_100keV.root"
pytestmark = pytest.mark.skipif(not SAMPLE.exists(), reason="sample ROOT absent")


@pytest.fixture(scope="module")
def run():
    return read_run(SAMPLE)


def test_reads_every_histogram(run):
    assert len(run.hists) == 40
    assert run.detector_dir == "medipix3_detector"
    assert not run.is_empty


def test_geometry_recovered_from_axes(run):
    assert run.geometry["n_pixels_x"] == 256
    assert run.geometry["pixel_pitch_x_um"] == pytest.approx(55.0, abs=0.01)


def test_profiles_are_masked_where_empty(run):
    eff = run.hists["efficiency/efficiency_map"]
    assert eff.counts is not None
    # Every NaN must correspond to a zero-entry bin and vice versa.
    assert np.array_equal(np.isnan(eff.values), eff.counts == 0)


def test_profile2d_counts_orientation_is_transposed():
    """fBinEntries must be transposed to match uproot's [x, y] values().

    This reads the RAW unmasked values straight from uproot so the check is not
    circular (runreader masks values *using* counts). Decisive property: a bin
    with zero entries can never carry a non-zero mean. The transposed
    orientation yields zero violations; the untransposed one yields thousands.
    """
    with uproot.open(SAMPLE) as f:
        for key in ("efficiency/efficiency_map", "cluster_size/cluster_size_map"):
            obj = f[f"DetectorHistogrammer/medipix3_detector/{key}"]
            nx = int(obj.member("fXaxis").member("fNbins"))
            ny = int(obj.member("fYaxis").member("fNbins"))
            raw = np.asarray(obj.values(), dtype=float)
            entries = np.asarray(obj.member("fBinEntries"), dtype=float)
            ring = entries.reshape(ny + 2, nx + 2)[1:-1, 1:-1]

            transposed = ring.T
            untransposed = ring
            viol_t = int(np.sum((transposed == 0) & (raw != 0)))
            viol_u = int(np.sum((untransposed == 0) & (raw != 0)))

            assert viol_t == 0, f"{key}: transposed orientation has {viol_t} violations"
            assert viol_u > 0, (
                f"{key}: untransposed now also aligns -- uproot may have changed "
                "its axis convention; re-derive the orientation in runreader"
            )


def test_agrees_with_production_reader(run):
    """The page and the campaign CSVs must not be able to diverge."""
    import analysis.scripts.material_penetration_experiment as m

    counts, centers = m.read_cluster_charge(SAMPLE, "medipix3_detector")
    h = run.hists["charge/cluster_charge"]
    assert np.array_equal(counts, h.values)
    assert np.allclose(centers, h.axes[0].centers)

    n_ref = m.read_detected_event_count(SAMPLE, "medipix3_detector")
    assert float(np.nansum(run.hists["event_size_clusters"].values)) == n_ref


def test_uproot_tripwire_tprofile2d_counts_still_raises():
    with uproot.open(SAMPLE) as f:
        obj = f["DetectorHistogrammer/medipix3_detector/efficiency/efficiency_map"]
        with pytest.raises(Exception):
            obj.counts()


def test_uproot_tripwire_tprofile_counts_includes_flow():
    with uproot.open(SAMPLE) as f:
        obj = f["DetectorHistogrammer/medipix3_detector/efficiency/efficiency_vs_x"]
        assert len(obj.counts()) == len(obj.values()) + 2


def test_missing_root_degrades_gracefully():
    from analysis.viz.runreader import read_run_or_none
    assert read_run_or_none(reg.DATA_DIR / "does_not_exist.root") is None


def test_truncated_run_is_reported_not_crashed():
    truncated = reg.DATA_DIR / "s2_cdte_fresh.root"
    if not truncated.exists():
        pytest.skip("truncated sample absent")
    r = read_run(truncated)
    assert r.is_empty
    assert r.warnings
