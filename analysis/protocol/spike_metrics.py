"""Event-level response metrics from a TextWriter PixelCharge table (mono-energetic beam)."""
import numpy as np
from analysis.protocol.textwriter import read_pixel_charge

W_EV = 4.43  # eV per e-h pair, CdTe (register PH-05)
K_LINES_KEV = (23.1, 27.5)  # Cd Ka, Te Ka (escape peaks at E - line)


def response_metrics(path, E_keV, n_events, thr_keV=5.0, peak_tol_keV=2.0):
    df, _ = read_pixel_charge(path)
    df = df.assign(E=df.charge_e * W_EV * 1e-3)
    d = df[df.E > thr_keV]
    ev = d.groupby("event").E.agg(["sum", "size"])
    tot = df.groupby("event").E.sum()  # all collected charge (no threshold)
    n = n_events
    p = lambda k: k / n
    se = lambda k: np.sqrt(p(k) * (1 - p(k)) / n)
    det = len(ev)
    fep = int((np.abs(tot - E_keV) < peak_tol_keV).sum())
    esc = int(sum((np.abs(tot - (E_keV - L)) < peak_tol_keV).sum() for L in K_LINES_KEV))
    multi = int((ev["size"] > 1).sum())
    return {
        "detected_frac": p(det), "detected_se": se(det),
        "full_energy_frac": p(fep), "fep_se": se(fep),
        "escape_frac": p(esc), "esc_se": se(esc),
        "multipixel_frac_of_detected": multi / max(det, 1),
        "mean_pixels": float(ev["size"].mean()),
    }
