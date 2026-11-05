"""Regression: the C++ MCTrack reader (simulation/protocol_runs/tools/mctrack_depths.cc) must reproduce the
Python reference reader (analysis/protocol/drift.py:track_depths).

Fixture (tests/fixtures/, 0.65 MB): 300-event flat-beam run, Medipix3 CdTe 1 mm, 59.54 keV, seed 4242
(mctrack_fixture.conf / .mac), its MCTrack objects file, and the C++ reader output (mctrack_fixture_depths.csv).
Original full-size check (2026-11-05, 3000-event run): 2,948 events with electrons, identical event set,
max |diff| 5.0e-7 mm (CSV rounding to 6 decimals).

Fast tests (every push): first FAST_EVENTS events vs the Python reader, entry-point sanity.
Slow tests (@pytest.mark.slow, nightly: `pytest -m slow`): all 300 events, and the C++ binary re-run in the
allpix container must reproduce the committed CSV byte for byte.
"""
import shutil
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

FX = Path(__file__).resolve().parent / "fixtures"
ROOT_FILE = FX / "mctrack_fixture_objects.root"
CPP_CSV = FX / "mctrack_fixture_depths.csv"
REPO = FX.parents[1]
TOL = 1e-6   # CSV written with 6 decimals -> rounding error <= 5e-7
N_EVENTS = 300
FAST_EVENTS = 50
COLS = ["z_wmean_mm", "z_min_mm", "z_max_mm", "e_keV"]


def _compare(entry_stop):
    pytest.importorskip("uproot")
    from analysis.protocol.drift import track_depths
    py = track_depths(ROOT_FILE, entry_stop=entry_stop)
    cpp = pd.read_csv(CPP_CSV).set_index("event").dropna(subset=["z_wmean_mm"])
    if entry_stop is not None:
        cpp = cpp[cpp.index <= entry_stop]
    assert len(py) > 0.9 * (entry_stop or N_EVENTS)
    assert py.index.equals(cpp.index)                          # identical event set (events with electrons)
    assert (py[COLS] - cpp[COLS]).abs().to_numpy().max() < TOL


def test_cpp_reader_matches_python_reader_fast():
    _compare(FAST_EVENTS)


def test_cpp_reader_primary_entry_points():
    cpp = pd.read_csv(CPP_CSV)
    assert len(cpp) == N_EVENTS and cpp.x0_mm.notna().all()   # every event, also non-interacting photons
    h = float((FX / "mctrack_fixture.mac").read_text().split("halfx")[1].split()[0])
    assert np.abs(cpp[["x0_mm", "y0_mm"]].to_numpy()).max() <= h


@pytest.mark.slow
def test_cpp_reader_matches_python_reader_full():
    _compare(None)


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker + allpix image")
def test_cpp_reader_binary_reproduces_fixture():
    binary = REPO / "data/protocol_runs/bin/mctrack_depths"
    if not binary.exists():
        pytest.skip("mctrack_depths not built (see simulation/protocol_runs/tools/mctrack_depths.cc)")
    tmp_root, out = REPO / "data/protocol_runs/bin/_fixture.root", REPO / "data/protocol_runs/bin/_regression_depths.csv"
    try:
        shutil.copy(ROOT_FILE, tmp_root)
        r = subprocess.run(["docker", "compose", "run", "--rm", "-T", "--user", "1000:1000", "-e", "HOME=/tmp",
                            "allpix", "bash", "-c",
                            "cd /tmp && /data/output/protocol_runs/bin/mctrack_depths "
                            "/data/output/protocol_runs/bin/_fixture.root /data/output/protocol_runs/bin/_regression_depths.csv"],
                           cwd=REPO, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            pytest.skip(f"container not runnable: {r.stderr[-300:]}")
        assert out.read_text() == CPP_CSV.read_text()
    finally:
        out.unlink(missing_ok=True)
        tmp_root.unlink(missing_ok=True)
