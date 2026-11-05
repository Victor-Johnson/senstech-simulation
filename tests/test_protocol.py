"""Unit tests for analysis/protocol (drift, integration-time rule, electronics, XCOM parser, phase space)."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from analysis.protocol.config_rules import DriftSpec, transit_ns, validate, IntegrationTimeError, check_integration_time
from analysis.protocol.drift import drift_time_ns
from analysis.protocol.electronics import Electronics, bin_counts, W_EV
from analysis.protocol.phasespace import DTYPE

REPO = Path(__file__).resolve().parents[1]


def test_constant_field_transit_matches_closed_form():
    s = DriftSpec(0.1, -300, None, "constant", "constant", 1090, 110, 293)
    assert transit_ns(s, "e") == pytest.approx(0.1 ** 2 / (1090 * 300) * 1e9, rel=1e-6)
    assert transit_ns(s, "h") == pytest.approx(0.1 ** 2 / (110 * 300) * 1e9, rel=1e-6)


def test_linear_field_undepleted_is_infinite():
    s = DriftSpec(0.1, -100, -300, "linear", "constant", 1090, 110, 293)
    assert transit_ns(s, "e") == float("inf")


def test_drift_time_endpoints():
    s = DriftSpec(0.1, -300, None, "constant", "constant", 1090, 110, 293)
    full_e = transit_ns(s, "e")
    t = drift_time_ns(s, np.array([0.5, -0.5]), 0.5, "e")       # implant at +0.5 mm
    assert t[0] == pytest.approx(0, abs=1e-9)
    assert t[1] == pytest.approx(full_e, rel=1e-6)
    th = drift_time_ns(s, np.array([-0.5, 0.5]), 0.5, "h")       # holes go to -0.5 mm
    assert th[0] == pytest.approx(0, abs=1e-9)
    assert th[1] == pytest.approx(transit_ns(s, "h"), rel=1e-6)


def _write_conf(tmp_path, integration=None, bias="-300V"):
    det = tmp_path / "det.conf"
    det.write_text('[d]\ntype = "medipix3"\nsensor_thickness = 1000um\nsensor_material = "cadmium_telluride"\n')
    it = f"integration_time = {integration}\n" if integration else ""
    conf = tmp_path / "main.conf"
    conf.write_text(f'[Allpix]\ndetectors_file = "{det}"\n[ElectricFieldReader]\nmodel = "constant"\n'
                    f'bias_voltage = {bias}\n[GenericPropagation]\nmobility_model = "constant"\n'
                    f'mobility_electron = 1090cm*cm/V/s\nmobility_hole = 110cm*cm/V/s\n{it}')
    return conf


def test_rule_rejects_default_25ns(tmp_path):
    with pytest.raises(IntegrationTimeError):
        validate(_write_conf(tmp_path))


def test_rule_accepts_1us(tmp_path):
    validate(_write_conf(tmp_path, "1us"))
    r = check_integration_time(_write_conf(tmp_path, "1us"))
    assert r["electron_transit_ns"] == pytest.approx(30.58, abs=0.05)


def _pix(rows):
    return pd.DataFrame(rows, columns=["event", "px", "py", "charge_e"])


def test_bins_exact_without_noise():
    q = lambda keV: keV * 1e3 / W_EV
    pix = _pix([(1, 0, 0, q(25)), (2, 0, 0, q(55)), (3, 0, 0, q(5))])
    el = Electronics([10, 40], sigma_noise_e=0)
    r = bin_counts(pix, 3, el, (2, 2))
    assert np.allclose(r["counts_per_photon"], [1 / 3, 1 / 3])


def test_above_range_lost_vs_clip():
    q = lambda keV: keV * 1e3 / W_EV
    pix = _pix([(1, 0, 0, q(250)), (2, 0, 0, q(100))])
    base = dict(thresholds_keV=[20, 60, 120], saturation_e=45000)
    lost = bin_counts(pix, 2, Electronics(above_range="lost", **base), (1, 1))
    clip = bin_counts(pix, 2, Electronics(above_range="clip", **base), (1, 1))
    assert lost["total_per_photon"] == pytest.approx(0.5)
    assert clip["total_per_photon"] == pytest.approx(1.0)
    assert clip["counts_per_photon"][-1] == pytest.approx(0.5)
    assert lost["above_range_per_photon"] == pytest.approx(0.5)


def test_neighbour_summing_recovers_shared_charge():
    q = lambda keV: keV * 1e3 / W_EV
    pix = _pix([(1, 1, 1, q(35)), (1, 2, 1, q(25))])
    off = bin_counts(pix, 1, Electronics([20, 50]), (4, 4))
    on = bin_counts(pix, 1, Electronics([20, 50], summing="nxn", neighbourhood=3), (4, 4))
    assert np.allclose(off["counts_per_photon"], [2, 0])     # double count, wrong energy
    assert np.allclose(on["counts_per_photon"], [0, 1])      # one count at 60 keV


def test_phasespace_record_size():
    assert DTYPE.itemsize == 30


def test_xcom_parser_on_stored_response():
    raw = REPO / "analysis/protocol/reference/xcom/raw/Cu_0.html"
    if not raw.exists():
        pytest.skip("XCOM raw response not present")
    from analysis.protocol.xcom import _parse
    d = _parse(raw.read_text(encoding="latin-1"))
    assert len(d) >= 50 and d.energy_keV.iloc[0] == pytest.approx(10.0)
    row = d.set_index("energy_keV").loc[100.0]
    assert row.total_with_coherent == pytest.approx(0.4585, rel=2e-3)   # NIST table value for Cu


@pytest.mark.parametrize("mode,arb,expected_sigma", [("pixel", "noisy", 100.0), ("pixel_all", "true", 200.0),
                                                      ("summed", "noisy", 100.0)])
def test_csm_noise_modes(mode, arb, expected_sigma):
    """Single-pixel events, 2x2 summing: 'pixel' noises the one recorded pixel, 'pixel_all' every pixel of the
    block (sqrt(4) x sigma when the block is fixed), 'summed' applies sigma once to the summed signal."""
    from analysis.protocol.electronics import signals
    n = 20000
    pix = _pix([(i, 5, 5, 10000.0) for i in range(1, n + 1)])
    el = Electronics([1.0], sigma_noise_e=100, summing="nxn", neighbourhood=2, noise_mode=mode, arbitration=arb)
    s = signals(pix, el, (10, 10))
    assert len(s) == n
    assert s.charge_e.std() == pytest.approx(expected_sigma, rel=0.03)
    assert s.charge_e.mean() == pytest.approx(10000.0, abs=5)


def test_noisy_arbitration_biases_single_pixel_events():
    """With every pixel noisy, the chip-like choice of the largest NOISY 2x2 sum (4 candidates sharing the seed)
    shifts single-pixel events up and narrows them -- a real CSM effect, quantified in exp0_v1_fwhm."""
    from analysis.protocol.electronics import signals
    pix = _pix([(i, 5, 5, 10000.0) for i in range(1, 20001)])
    s = signals(pix, Electronics([1.0], sigma_noise_e=100, summing="nxn", neighbourhood=2,
                                 noise_mode="pixel_all"), (10, 10))
    assert s.charge_e.mean() > 10000 + 50 and s.charge_e.std() < 190


def test_vectorised_2x2_picks_best_block():
    from analysis.protocol.electronics import _sum_neighbourhood
    pix = _pix([(1, 5, 5, 100.0), (1, 4, 5, 10.0), (1, 6, 5, 30.0), (1, 6, 6, 20.0), (1, 8, 8, 999.0 - 900)])
    r = _sum_neighbourhood(pix, 2).iloc[0]
    assert (r.px, r.py) == (5, 5) and r.charge_e == pytest.approx(150.0) and r.k == 3   # block (5..6, 5..6)
