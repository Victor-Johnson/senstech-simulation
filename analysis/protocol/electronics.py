"""Stage C (low-flux part): pixel electronics applied to Stage-B per-event pixel charge.

Implemented (each parameter is an input, never a hidden default; tags from inputs_register.csv):
  * electronic noise per pixel per event, Gaussian sigma_noise_e            (D-L22 90 e- P; D-M04 80/175 e- P)
  * threshold dispersion: fixed per-pixel offset, Gaussian sigma_disp_e     (D-L21 bracket 20-80 e-, A)
  * energy thresholds / bins (keV, converted with 4.43 eV/pair, PH-05)
  * charge-sharing correction (R-01): "off", or generic neighbour summing: the charge of all pixels in the
    n x n neighbourhood (n = 2 or 3) around the event's highest pixel is summed and assigned to that pixel;
    with probability (1 - summing_efficiency) an event is NOT corrected and counts per pixel (A, R-04 ranges)
  * front-end range (D-L23, 45 ke- ~ 199 keV) with the two above-range scenarios of review item 5:
      "lost": a pixel (or summed) signal above saturation produces no count
      "clip": it is counted in the top bin
Not here (time-domain layer, Exp 6/7): dead time, pile-up, counters, TDI.

Counting convention: one count per pixel signal above the lowest threshold (summing off), or one count per
summed hit (summing on). Counts are per INCIDENT photon of the Stage-B run (divide by n_events).
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

W_EV = 4.43  # PH-05


@dataclass
class Electronics:
    thresholds_keV: list[float]                 # ascending; bin i = [thr_i, thr_{i+1}), last bin = [thr_last, sat)
    sigma_noise_e: float = 0.0
    sigma_disp_e: float = 0.0
    summing: str = "off"                        # "off" | "nxn"
    neighbourhood: int = 3                      # 2 or 3
    summing_efficiency: float = 1.0
    saturation_e: float | None = None           # None = unlimited front end
    above_range: str = "lost"                   # "lost" | "clip"
    seed: int = 12345
    # Where noise enters when summing is on (review 2026-11-05 item 1):
    #   "pixel"     sigma_noise_e on every RECORDED pixel, then summed (legacy; empty block pixels add no noise)
    #   "pixel_all" sigma_noise_e on EVERY pixel around the seed (5x5, zero-charge pixels materialised), on every
    #               event, BEFORE the block is chosen -> every front-end in every candidate 2x2 / 3x3 block is noisy
    #   "summed"    sigma_noise_e applied ONCE to the summed signal (sigma is an effective CSM noise)
    noise_mode: str = "pixel"
    # Which block wins when summing (n=2): "noisy" (DEFAULT, decided 2026-11-05) = block with the largest NOISY
    # sum, as the chip's arbitration compares noisy summed signals; "true" = block chosen from the noiseless
    # charge (diagnostic only)
    arbitration: str = "noisy"
    tags: dict = field(default_factory=dict)

    def thr_e(self) -> np.ndarray:
        return np.asarray(self.thresholds_keV, float) * 1e3 / W_EV


def _sum_neighbourhood(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Per event: highest pixel (seed) and the summed charge of the n x n block around it.
    n=3: +-1 around the seed; n=2: of the four 2x2 blocks containing the seed, the one with the largest sum.
    Returns event, px, py (seed), charge_e (block sum), k (recorded pixels in the block). Vectorised."""
    d = df.reset_index(drop=True)
    seed = d.loc[d.groupby("event", sort=False).charge_e.idxmax(), ["event", "px", "py"]]
    seed = seed.rename(columns={"px": "sx", "py": "sy"})
    m = d.merge(seed, on="event", how="left")
    dx, dy = (m.px - m.sx).to_numpy(), (m.py - m.sy).to_numpy()
    q = m.charge_e.to_numpy()
    if n == 3:
        inb = (np.abs(dx) <= 1) & (np.abs(dy) <= 1)
        g = pd.DataFrame(dict(event=m.event, q=np.where(inb, q, 0.0), k=inb.astype(int))).groupby("event", sort=False).sum()
    else:
        best = None
        for ox in (-1, 0):
            for oy in (-1, 0):
                inb = (dx - ox >= 0) & (dx - ox <= 1) & (dy - oy >= 0) & (dy - oy <= 1)
                g_ = pd.DataFrame(dict(event=m.event, q=np.where(inb, q, 0.0), k=inb.astype(int))).groupby("event", sort=False).sum()
                if best is None:
                    best = g_
                else:
                    take = g_.q > best.q
                    best = best.where(~take, g_)
        g = best
    out = seed.set_index("event").join(g)
    return pd.DataFrame(dict(event=out.index.to_numpy(), px=out.sx.to_numpy(), py=out.sy.to_numpy(),
                             charge_e=out.q.to_numpy(float), k=out.k.to_numpy(int)))


def _materialise(d: pd.DataFrame, half: int, npix: tuple[int, int]) -> pd.DataFrame:
    """Add zero-charge rows for every pixel within +-half of each event's (noiseless) seed pixel, inside the matrix."""
    seed = d.loc[d.groupby("event", sort=False).charge_e.idxmax(), ["event", "px", "py"]]
    off = np.arange(-half, half + 1)
    ox, oy = np.meshgrid(off, off, indexing="ij")
    ev = np.repeat(seed.event.to_numpy(), ox.size)
    gx = (np.repeat(seed.px.to_numpy(), ox.size) + np.tile(ox.ravel(), len(seed)))
    gy = (np.repeat(seed.py.to_numpy(), ox.size) + np.tile(oy.ravel(), len(seed)))
    ok = (gx >= 0) & (gx < npix[0]) & (gy >= 0) & (gy < npix[1])
    grid = pd.DataFrame(dict(event=ev[ok], px=gx[ok], py=gy[ok]))
    m = grid.merge(d, on=["event", "px", "py"], how="left").fillna({"charge_e": 0.0})
    outside = d.merge(grid, on=["event", "px", "py"], how="left", indicator=True)
    outside = outside[outside["_merge"] == "left_only"].drop(columns="_merge")
    return pd.concat([m, outside], ignore_index=True)


def signals(pix: pd.DataFrame, el: Electronics, npix: tuple[int, int]) -> pd.DataFrame:
    """Return the list of front-end signals (event, px, py, q_e) after noise and summing."""
    rng = np.random.default_rng(el.seed)
    d = pix[["event", "px", "py", "charge_e"]].copy()
    summing = el.summing != "off"
    if summing and el.sigma_noise_e > 0 and el.noise_mode == "pixel_all":
        d = _materialise(d, 2, npix)
    true_q = d.charge_e.to_numpy().copy()
    if el.sigma_noise_e > 0 and (not summing or el.noise_mode in ("pixel", "pixel_all")):
        d["charge_e"] = d.charge_e + rng.normal(0, el.sigma_noise_e, len(d))
    if not summing:
        return d
    if el.arbitration == "true":
        # diagnostic: seed and block chosen on the noiseless charge, the block's NOISY charges summed
        seed = d.assign(charge_e=true_q)
        seed = seed.loc[seed.groupby("event", sort=False).charge_e.idxmax(), ["event", "px", "py"]]
        m = d.assign(tq=true_q).merge(seed.rename(columns={"px": "sx", "py": "sy"}), on="event")
        summed = _sum_fixed_block(m, el.neighbourhood)
    else:
        summed = _sum_neighbourhood(d, el.neighbourhood)
    if el.sigma_noise_e > 0 and el.noise_mode == "summed":
        summed["charge_e"] = summed.charge_e + rng.normal(0, el.sigma_noise_e, len(summed))
    corrected = rng.random(len(summed)) < el.summing_efficiency
    keep_ev = set(summed.event[corrected])
    uncorrected = d[~d.event.isin(keep_ev)]
    if el.sigma_noise_e > 0 and el.noise_mode == "summed":     # uncorrected events: pixel-level noise
        uncorrected = uncorrected.assign(charge_e=uncorrected.charge_e + rng.normal(0, el.sigma_noise_e, len(uncorrected)))
    return pd.concat([summed[corrected].drop(columns="k"), uncorrected], ignore_index=True)


def _sum_fixed_block(m: pd.DataFrame, n: int) -> pd.DataFrame:
    """Block chosen on noiseless charge 'tq' (seed sx, sy from noiseless max), summing the noisy 'charge_e'."""
    dx, dy = (m.px - m.sx).to_numpy(), (m.py - m.sy).to_numpy()
    tq, q = m.tq.to_numpy(), m.charge_e.to_numpy()
    if n == 3:
        inb = (np.abs(dx) <= 1) & (np.abs(dy) <= 1)
        g = pd.DataFrame(dict(event=m.event, q=np.where(inb, q, 0.0), k=inb.astype(int))).groupby("event", sort=False).sum()
    else:
        best_t, g = None, None
        for ox in (-1, 0):
            for oy in (-1, 0):
                inb = (dx - ox >= 0) & (dx - ox <= 1) & (dy - oy >= 0) & (dy - oy <= 1)
                gg = pd.DataFrame(dict(event=m.event, t=np.where(inb, tq, 0.0), q=np.where(inb, q, 0.0),
                                       k=inb.astype(int))).groupby("event", sort=False).sum()
                if g is None:
                    g, best_t = gg[["q", "k"]], gg.t
                else:
                    take = gg.t > best_t
                    g = g.where(~take, gg[["q", "k"]]); best_t = best_t.where(~take, gg.t)
    seed = m.groupby("event", sort=False)[["sx", "sy"]].first()
    out = seed.join(g)
    return pd.DataFrame(dict(event=out.index.to_numpy(), px=out.sx.to_numpy(), py=out.sy.to_numpy(),
                             charge_e=out.q.to_numpy(float), k=out.k.to_numpy(int)))


def bin_counts(pix: pd.DataFrame, n_events: int, el: Electronics, npix: tuple[int, int]) -> dict:
    """Counts per bin per incident photon, plus above-range and below-threshold bookkeeping."""
    rng = np.random.default_rng(el.seed + 1)
    disp = rng.normal(0, el.sigma_disp_e, size=npix) if el.sigma_disp_e > 0 else np.zeros(npix)
    s = signals(pix, el, npix)
    q = s.charge_e.to_numpy()
    off = disp[s.px.to_numpy(), s.py.to_numpy()]
    thr = el.thr_e()
    nb = len(thr)
    above = np.zeros(len(q), bool)
    if el.saturation_e is not None:
        above = q > el.saturation_e
    # effective per-pixel thresholds = nominal + fixed pixel offset (same offset for all thresholds of a pixel)
    qq = q - off
    idx = np.searchsorted(thr, qq, side="right") - 1      # -1 = below lowest threshold
    counted = idx >= 0
    if el.saturation_e is not None:
        if el.above_range == "lost":
            counted &= ~above
        else:  # clip into top bin
            idx = np.where(above, nb - 1, idx)
    counts = np.bincount(idx[counted], minlength=nb)[:nb] / n_events
    return dict(counts_per_photon=counts, total_per_photon=counts.sum(),
                above_range_per_photon=float(above.sum()) / n_events,
                signals_per_photon=len(q) / n_events)
