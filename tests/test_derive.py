"""Derivation contracts.

The formula-consistency test is the one that matters most: it makes it
structurally impossible for a run page to display a formula that does not
produce the number shown next to it.
"""
from __future__ import annotations

import pytest

from analysis.viz import detectors as D
from analysis.viz import manifest as mf
from analysis.viz import provenance as pv
from analysis.viz import registry as reg
from analysis.viz.derive import (SATURATION_EFF, THICKNESS_SPREAD_TOLERANCE_MM,
                                 derive_run, implied_thickness_profile,
                                 thickness_verdict)
from analysis.viz.runreader import read_run_or_none

pytestmark = pytest.mark.skipif(
    not (reg.DATA_DIR / "p2_bare_medipix3_100keV.root").exists(),
    reason="ROOT files absent")

SAMPLES = ["p2_bare_medipix3_100keV", "p2_bare_eiger2_075mm_60keV",
           "p2_bare_hexitec_proxy_150keV", "mpu_bare_timepix3_cdte_80keV"]


def _derive(run_id):
    key = reg.parse_name(run_id)
    run = read_run_or_none(reg.root_path(key))
    if run is None:
        pytest.skip(f"{run_id} absent")
    manifest = reg.CAMPAIGNS[key.campaign].manifest_path
    m = mf.read(manifest) if manifest else None
    prov = pv.capture(key, manifest=m, run_geometry=run.geometry)
    source = reg.CAMPAIGNS[key.campaign].detector_source
    return derive_run(run, prov, D.resolve(key.detector, source))


@pytest.mark.parametrize("run_id", SAMPLES)
def test_every_formula_reproduces_its_value(run_id):
    for q in _derive(run_id):
        q.assert_consistent()


@pytest.mark.parametrize("run_id", SAMPLES)
def test_quantities_are_produced(run_id):
    qs = _derive(run_id)
    keys = {q.key for q in qs}
    assert {"detection_efficiency", "windowed_response", "n_events"} <= keys


def test_windowed_response_matches_production_pipeline():
    """The page and phase2_selection_experiment must not be able to diverge."""
    import analysis.scripts.phase2_selection_experiment as p2

    run_id = "p2_bare_eiger2_075mm_60keV"
    qs = {q.key: q for q in _derive(run_id)}
    det = next(d for d in p2.DETS if d.key == "eiger2")
    expected, _ = p2.bare_windowed_response(det, 0.75, 60.0, 10000)
    assert qs["windowed_response"].value == pytest.approx(expected, rel=1e-12)


def test_units_come_from_the_root_axis_not_a_literal():
    """residual_r is micrometres; hardcoding mm would be wrong by 1000x."""
    qs = {q.key: q for q in _derive("p2_bare_medipix3_100keV")}
    assert qs["residual_r_mean"].unit == "µm"
    assert 0 < qs["residual_r_mean"].value < 100


def test_saturated_energies_are_marked_invalid():
    qs = {q.key: q for q in _derive("p2_bare_hexitec_proxy_150keV")}
    t = qs.get("implied_thickness_mm")
    assert t is not None and t.valid       # 150 keV is well below saturation


class TestThicknessIntegrity:
    """The estimator must recover a known thickness, and say so when it can't."""

    @pytest.mark.parametrize("detector", ["medipix3", "timepix4", "hexitec_proxy",
                                          "medipix4", "timepix3_cdte"])
    def test_tagged_runs_recover_075mm(self, detector):
        v = thickness_verdict(detector, "phase2_selection",
                              variant={"thickness_tag": "_075mm"})
        assert v["status"] == "ok", v
        assert v["median_mm"] == pytest.approx(0.75, abs=0.03)
        assert v["spread_mm"] <= THICKNESS_SPREAD_TOLERANCE_MM

    @pytest.mark.parametrize("detector", ["medipix3", "timepix4", "hexitec_proxy",
                                          "medipix4", "timepix3_cdte"])
    def test_untagged_runs_recover_1mm(self, detector):
        v = thickness_verdict(detector, "phase2_selection", variant={})
        assert v["status"] == "ok", v
        assert v["median_mm"] == pytest.approx(1.0, abs=0.03)

    def test_eiger2_untagged_has_no_plateau(self):
        """The known-bad runs. If this ever starts passing, they were re-run --
        update the expectation deliberately rather than deleting the test."""
        v = thickness_verdict("eiger2", "phase2_selection", variant={})
        assert v["status"] == "UNRESOLVED"
        assert v["spread_mm"] > THICKNESS_SPREAD_TOLERANCE_MM

    def test_threshold_limited_low_energy_point_does_not_fail_a_good_run(self):
        """Medipix4's 30 keV bin sits below the saturation cut because of its
        1773 e- threshold. Excluding energies below the efficiency peak is what
        stops that single point from condemning a perfectly good run."""
        df = implied_thickness_profile("medipix4", "phase2_selection", variant={})
        low = df[df.energy_keV == 30.0]
        assert not low.empty
        assert float(low.efficiency.iloc[0]) < SATURATION_EFF     # would be "usable"
        assert thickness_verdict("medipix4", "phase2_selection",
                                 variant={})["status"] == "ok"
