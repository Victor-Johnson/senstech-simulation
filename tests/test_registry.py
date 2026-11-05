"""Registry contracts.

The round-trip test is the reason the registry can be trusted as the single
source of truth for run names: template and regex cannot drift apart without
this failing.
"""
from __future__ import annotations

import pytest

from analysis.viz import registry as reg

ROOT_FILES = sorted(reg.DATA_DIR.glob("*.root"))
pytestmark = pytest.mark.skipif(not ROOT_FILES, reason="no ROOT files on this machine")


@pytest.mark.parametrize("path", ROOT_FILES, ids=lambda p: p.stem)
def test_every_root_file_parses(path):
    assert reg.parse_name(path.stem) is not None, (
        f"{path.name} matches no registry pattern -- add one to CAMPAIGNS "
        "rather than letting the run disappear from downstream counts"
    )


@pytest.mark.parametrize("path", ROOT_FILES, ids=lambda p: p.stem)
def test_name_round_trips(path):
    key = reg.parse_name(path.stem)
    assert reg.build_name(key) == path.stem


def test_discover_reports_nothing_unparsed():
    d = reg.discover()
    assert not d.unparsed, [p.name for p in d.unparsed]
    assert len(d.runs) == len(ROOT_FILES)


def test_thickness_variants_are_distinct_runs():
    """The bug that destroyed the 1 mm phase-2 manifest rows was that tagged
    and untagged runs collided under one key. They must never be equal."""
    plain = reg.parse_name("p2_bare_eiger2_40keV")
    tagged = reg.parse_name("p2_bare_eiger2_075mm_40keV")
    assert plain != tagged
    assert plain.var.get("thickness_tag") is None
    assert tagged.var["thickness_tag"] == "_075mm"
    assert reg.build_name(plain) != reg.build_name(tagged)


def test_container_path_maps_to_host():
    host = reg.to_host_path(
        "/data/simulation/configs/scenarios/phase2_selection/p2_bare_eiger2_40keV.conf")
    assert host == (reg.REPO_ROOT / "simulation/configs/scenarios/"
                    "phase2_selection/p2_bare_eiger2_40keV.conf")


def test_unknown_name_returns_none_not_exception():
    assert reg.parse_name("totally_unknown_thing") is None
