"""Model-free integrity checks."""
from __future__ import annotations

import pytest

from analysis.viz import registry as reg
from analysis.viz.integrity import (PAIRED_TOLERANCE, contradictions,
                                    paired_config_check)

pytestmark = pytest.mark.skipif(
    not (reg.DATA_DIR / "p2_bare_eiger2_20keV.root").exists(),
    reason="ROOT files absent")


def test_paired_runs_share_identical_configs():
    """Every phase-2 thickness pair points at the same sim config. That is the
    driver bug this pipeline exists to surface -- if it is ever fixed, these
    hashes will differ and this test should be updated on purpose."""
    findings = paired_config_check("phase2_selection")
    assert findings
    assert all(f.configs_identical for f in findings)


def test_only_eiger2_contradicts():
    bad = contradictions("phase2_selection")
    assert {f.detector for f in bad} == {"eiger2"}
    assert {f.energy_keV for f in bad} == {20.0, 30.0, 40.0}


def test_other_chips_agree_within_tolerance():
    for f in paired_config_check("phase2_selection"):
        if f.detector == "eiger2":
            continue
        assert f.relative_difference <= PAIRED_TOLERANCE, f.explain()


def test_explanation_names_the_evidence():
    bad = contradictions("phase2_selection")[0]
    text = bad.explain()
    assert "BYTE-IDENTICAL" in text
    assert bad.config_sha_a[:12] in text
