"""Exp 0 V1: Am-241 spectra on Medipix3 / Timepix3 CdTe (55 um, 1 mm) -- simulation side, ready for comparison.

Inputs
  Stage B campaign exp0_v1_am241 (stageb.py): flat-beam mono runs at the Am-241 photon lines, 50k photons
  each, scored in the central 16 x 16 pixel fiducial region (primary entry point).
  Timepix3 shares the Medipix3 Stage B until the publication's sensor parameters arrive (stageb.STAGEB_DET_ALIAS).
  AM241_LINES in stageb.py (emission probabilities; TO VERIFY against DDEP/LNHB, colleague).
  Electronics per detector/mode (Stage C) -- the V1 starting parameters below, every one an input.
  Reference spectra (colleague): analysis/protocol/reference/v1/<detector>_<mode>.csv (energy_keV,counts).
Process
  per line: fiducial pixel table -> Stage C signals (summing off = SPM; 2x2 summing = CSM) -> per-pixel
  threshold-dispersion offset (energy-scale shift of that pixel, as in a threshold-scan spectrum) ->
  histogram per fiducial photon; lines combined with emission probabilities -> spectrum per decay.
Peak metrics (59.54 keV)
  Gaussian fitted to the peak CORE only: window [mu - 1 sigma, mu + 3 sigma], iterated to convergence, no
  constant term -> the low-energy tail (incomplete summing / trapping) and the Cd/Te K-escape peaks
  (59.54 - 23.2 = 36.4 keV, 59.54 - 27.5 = 32.1 keV) are outside the fit. Cross-check: FWHM read directly
  from the histogram (linear interpolation of the half-maximum crossings). 0.1 keV bins.
  multi_pixel_59keV: among fiducial 59.54 keV photons with >= 1 pixel above MP_THR_KEV (noiseless pixel
  charge), the fraction with > 1 such pixel.
Outputs (analysis/protocol/exp0/v1/): sim_<det>_<mode>.csv, v1_metrics.csv
Comparison caveat (review 2026-11-05 item 4): the ballistic deficit (finite CSA shaping) is NOT modelled yet
(PH-21; X0-CSA required, not built). Until the CSA step exists the simulated 59.5 keV peak is expected to be
slightly NARROWER (and its low-energy tail slightly smaller) than a measured one; a FWHM shortfall of this kind
is not by itself a V1 failure. Every row of v1_metrics.csv carries this note.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from analysis.protocol.stageb import AM241_LINES, DETECTORS, STAGEB_DET_ALIAS, load_fiducial, run_name
from analysis.protocol.electronics import Electronics, signals, W_EV

R = Path(__file__).resolve().parents[2]
OUT = R / "analysis/protocol/exp0/v1"
REF = R / "analysis/protocol/reference/v1"
BINS = np.arange(0, 80.05, 0.1)
CENTRES = 0.5 * (BINS[1:] + BINS[:-1])
PEAK = 59.54
MP_THR_KEV = 5.0
TOL_POS_KEV, TOL_FWHM_REL = 0.5, 0.10  # Protocol Table 10 (proposed)
CAVEAT = ("ballistic deficit (CSA shaping) not modelled (PH-21, X0-CSA not built): simulated peak expected "
          "slightly narrower than measured until the CSA step exists")

# V1 starting electronics. CSM noise: per-pixel 80 e- (D-M04 SPM value) on all 4 pixels of the summing block
# ("pixel_all") -> 160 e- effective, consistent with the quoted ~175 e- CSM noise (D-M04). The previous setting
# (175 e- on every recorded pixel, then summed) counted the summing noise twice -- see exp0_v1_fwhm.py.
MPX3_DISP_E = 40.0   # D-M12: threshold dispersion after equalisation, tag A (bracket 20-80 e-) until published value
DEFAULT_EL = {
    ("medipix3", "spm"): Electronics([5.0], sigma_noise_e=80, sigma_disp_e=MPX3_DISP_E, summing="off"),
    # CSM: block = largest NOISY 2x2 sum (chip-like arbitration, default); arbitration="true" is diagnostic only
    ("medipix3", "csm"): Electronics([5.0], sigma_noise_e=80, sigma_disp_e=MPX3_DISP_E, summing="nxn",
                                     neighbourhood=2, noise_mode="pixel_all", arbitration="noisy"),
    ("timepix3", "spm"): Electronics([5.0], sigma_noise_e=62, summing="off"),   # dispersion: no value yet (TBD)
}


def line_signals(campaign: str, det: str, E: float, el: Electronics, variant: str = "base"):
    sdet = STAGEB_DET_ALIAS.get(det, det)
    D = DETECTORS[sdet]
    pix, n_fid, _ = load_fiducial(campaign, run_name(campaign, sdet, E, variant), D)
    s = signals(pix, el, D.sim_array)
    q = s.charge_e.to_numpy()
    if el.sigma_disp_e > 0:
        off = np.random.default_rng(el.seed + 1).normal(0, el.sigma_disp_e, size=D.sim_array)
        q = q - off[s.px.to_numpy(), s.py.to_numpy()]
    return q * W_EV / 1e3, pix, n_fid


def multi_pixel_fraction(pix: pd.DataFrame, thr_keV: float = MP_THR_KEV) -> float:
    n_pix = pix[pix.charge_e * W_EV / 1e3 > thr_keV].groupby("event").size()
    return float((n_pix > 1).mean()) if len(n_pix) else np.nan


def spectrum(det: str, mode: str, el: Electronics | None = None, campaign: str = "exp0_v1_am241") -> tuple[np.ndarray, dict]:
    el = el or DEFAULT_EL[(det, mode)]
    h = np.zeros(len(BINS) - 1)
    multi = {}
    for E, p in AM241_LINES:
        e_keV, pix, n_fid = line_signals(campaign, det, E, el)
        e_keV = e_keV[e_keV >= el.thresholds_keV[0]]
        h += p * np.histogram(e_keV, BINS)[0] / n_fid
        multi[E] = multi_pixel_fraction(pix)
    return h, dict(multi_pixel_by_line=multi)


def _gauss(x, a, mu, s):
    return a * np.exp(-0.5 * ((x - mu) / s) ** 2)


def peak_metrics(centres: np.ndarray, h: np.ndarray, peak: float = PEAK) -> dict:
    """Core Gaussian fit [mu - 1 sigma, mu + 3 sigma] (iterated) + direct half-maximum FWHM."""
    w = (centres > peak - 10) & (centres < peak + 6)
    i0 = np.flatnonzero(w)[np.argmax(h[w])]
    hmax = h[i0]
    l = i0
    while l > 0 and h[l] > hmax / 2:
        l -= 1
    r = i0
    while r < len(h) - 1 and h[r] > hmax / 2:
        r += 1
    xl = np.interp(hmax / 2, [h[l], h[l + 1]], [centres[l], centres[l + 1]])
    xr = np.interp(hmax / 2, [h[r], h[r - 1]], [centres[r], centres[r - 1]])
    direct = xr - xl
    mu, s = centres[i0], max(direct / 2.3548, 0.2)
    pos = fwhm = np.nan
    for _ in range(20):
        m = (centres >= mu - 1.0 * s) & (centres <= mu + 3.0 * s)
        try:
            (a, mu_n, s_n), _ = curve_fit(_gauss, centres[m], h[m], p0=[hmax, mu, s], maxfev=20000)
        except Exception:
            break
        s_n = abs(s_n)
        conv = abs(mu_n - mu) < 1e-4 and abs(s_n - s) < 1e-4
        mu, s = mu_n, s_n
        pos, fwhm = mu, 2.3548 * s
        if conv:
            break
    valley = h[(centres > 45) & (centres < 55)].mean()
    sig = fwhm / 2.3548 if np.isfinite(fwhm) else np.nan
    tail = h[(centres > 40) & (centres < pos - 3 * sig)].sum() if np.isfinite(pos) else np.nan
    core = h[(centres >= pos - 3 * sig) & (centres <= pos + 3 * sig)].sum() if np.isfinite(pos) else np.nan
    return dict(peak_keV=pos, fwhm_keV=fwhm, fwhm_direct_keV=direct,
                peak_to_valley=hmax / valley if valley > 0 else np.inf,
                tail_over_core=tail / core if core else np.nan)


def run() -> pd.DataFrame:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for (det, mode) in DEFAULT_EL:
        h, extra = spectrum(det, mode)
        pd.DataFrame(dict(energy_keV=CENTRES, per_decay=h)).to_csv(OUT / f"sim_{det}_{mode}.csv", index=False)
        el = DEFAULT_EL[(det, mode)]
        r = dict(detector=det, stageB=STAGEB_DET_ALIAS.get(det, det), mode=mode, source="sim",
                 noise_e=el.sigma_noise_e, dispersion_e=el.sigma_disp_e, noise_mode=el.noise_mode if el.summing != "off" else "pixel",
                 **peak_metrics(CENTRES, h), multi_pixel_59keV=extra["multi_pixel_by_line"][59.54],
                 multi_pixel_thr_keV=MP_THR_KEV, caveat=CAVEAT,
                 provisional=("PROVISIONAL (tag A): Medipix3 dispersion 40 e- (D-M12), noise 80 e- (D-M04 interpretation), "
                              "Fano 0.24 (PH-06 conflict), Am-241 line data unverified, sensor/bias A; "
                              "Timepix3 = Medipix3 Stage B until publication parameters"))
        ref = REF / f"{det}_{mode}.csv"
        if ref.exists():
            rr = pd.read_csv(ref)
            rm = peak_metrics(CENTRES, np.interp(CENTRES, rr.energy_keV, rr.counts))
            r.update({f"ref_{k}": v for k, v in rm.items()})
            r["pass_position"] = abs(r["peak_keV"] - rm["peak_keV"]) <= TOL_POS_KEV
            r["pass_fwhm"] = abs(r["fwhm_keV"] / rm["fwhm_keV"] - 1) <= TOL_FWHM_REL
            r["fwhm_sim_narrower"] = r["fwhm_keV"] < rm["fwhm_keV"]   # expected direction until X0-CSA exists
        else:
            r["reference"] = "missing (colleague)"
        rows.append(r)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "v1_metrics.csv", index=False)
    return df


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    print(run().round(3).to_string(index=False))
