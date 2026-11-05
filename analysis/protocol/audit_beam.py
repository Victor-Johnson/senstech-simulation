"""Beam-footprint audit (review 2026-11-05, item 2): which runs are affected by a non-uniform / spilling beam.

Measured facts (protocol milestone 1, 2026-11-05):
  * beam_shape = "rectangle": NOT a uniform patch. The footprint is bell-shaped with sigma ~ beam_size/2 per
    axis (LINDA 1320 um -> 599-670 um; Medipix3 220 um -> 111 um after pixel quantisation; VAREX 400 -> 203 um).
  * default beam_shape (circle): Gaussian with sigma = beam_size (Allpix documentation; same behaviour as
    the 2 mm spike that over-filled LINDA, feasibility notes).
For every Allpix config with a beam source this computes, for each detector it hits (beam centred at
source_position x,y; detector at its position x,y; no rotation considered):
  frac_outside   fraction of incident photons whose entry point misses the pixel matrix
                 -> per-incident-photon quantities (efficiency, counts/photon) are biased LOW by this fraction
  frac_edge_0p5  fraction entering within 0.5 mm of the matrix edge (charge sharing / fluorescence partly lost
                 at the edge -> multi-pixel fraction, peak fraction biased)
Output: analysis/protocol/audit/beam_footprint_audit.csv and a per-campaign summary.
"""
from __future__ import annotations
import re
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import erf

from analysis.protocol.config_rules import REPO, parse_conf, resolve_detector_file, _qty, _LEN

MODEL_DEFAULTS = {"medipix3": ((256, 256), 0.055), "timepix": ((256, 256), 0.055)}  # /usr/local/share/Allpix/models
AUD = REPO / "analysis/protocol/audit"


def _mm(v: str) -> float:
    """Length in mm; a bare number is in Allpix internal units (mm)."""
    v = v.strip()
    return _qty(v, _LEN) * 10 if re.search(r"[a-zA-Z]$", v) else float(v)


def _vec(v: str) -> list[str]:
    return re.findall(r"[-+0-9.eE]+\s*[a-zA-Z]+|[-+0-9.eE]+", v)


def _frac_inside(c: float, s: float, lo: float, hi: float) -> float:
    """1-D Gaussian (centre c, sigma s) probability within [lo, hi]."""
    return 0.5 * (erf((hi - c) / (np.sqrt(2) * s)) - erf((lo - c) / (np.sqrt(2) * s)))


def detectors(det_path: Path) -> list[dict]:
    out = []
    for name, sec in parse_conf(det_path).items():
        typ = sec.get("type", "").strip('"')
        if "number_of_pixels" in sec:
            nx, ny = (int(x) for x in sec["number_of_pixels"].split()[:2])
        elif typ in MODEL_DEFAULTS:
            nx, ny = MODEL_DEFAULTS[typ][0]
        else:
            continue
        if "pixel_size" in sec:
            px, py = (_mm(x) for x in _vec(sec["pixel_size"])[:2])
        elif typ in MODEL_DEFAULTS:
            px = py = MODEL_DEFAULTS[typ][1]
        else:
            continue
        pos = [_mm(x) for x in _vec(sec.get("position", "0 0 0"))[:2]]
        out.append(dict(detector=name, nx=nx, ny=ny, pitch_x_mm=px, pitch_y_mm=py, cx=pos[0], cy=pos[1]))
    return out


def audit() -> pd.DataFrame:
    rows = []
    for conf in sorted((REPO / "simulation").rglob("*.conf")):
        c = parse_conf(conf)
        dep = c.get("DepositionGeant4")
        if not dep or dep.get("source_type", "beam").strip('"') != "beam" or "Allpix" not in c:
            continue
        shape = dep.get("beam_shape", "circle").strip('"')
        size = [_mm(x) for x in _vec(dep.get("beam_size", "0mm"))]
        if shape == "circle":
            sx = sy = size[0]                       # Gaussian sigma = beam_size
        else:
            sx, sy = size[0] / 2, (size[1] if len(size) > 1 else size[0]) / 2   # measured: sigma ~ size/2
        sp = _vec(dep.get("source_position", "0 0 0"))
        bx, by = (_mm(x) for x in sp[:2])
        det = resolve_detector_file(c, conf)
        if det is None:
            continue
        rel = conf.relative_to(REPO)
        campaign = rel.parent.name if rel.parts[1] != "configs" or len(rel.parts) > 3 else rel.parent.name
        for d in detectors(det):
            hx, hy = d["nx"] * d["pitch_x_mm"] / 2, d["ny"] * d["pitch_y_mm"] / 2
            fin = _frac_inside(bx, sx, d["cx"] - hx, d["cx"] + hx) * _frac_inside(by, sy, d["cy"] - hy, d["cy"] + hy)
            fcore = (_frac_inside(bx, sx, d["cx"] - hx + 0.5, d["cx"] + hx - 0.5) *
                     _frac_inside(by, sy, d["cy"] - hy + 0.5, d["cy"] + hy - 0.5)) if min(hx, hy) > 0.5 else 0.0
            rows.append(dict(config=str(rel), campaign=campaign, beam_shape=shape, beam_size_mm=size[0],
                             sigma_x_mm=sx, detector=d["detector"], matrix_mm=f"{2*hx:.2f}x{2*hy:.2f}",
                             frac_outside=1 - fin, frac_edge_0p5=fin - fcore))
    df = pd.DataFrame(rows)
    AUD.mkdir(parents=True, exist_ok=True)
    df.to_csv(AUD / "beam_footprint_audit.csv", index=False)
    return df


if __name__ == "__main__":
    df = audit()
    pd.set_option("display.width", 220)
    g = df.groupby(["campaign", "beam_shape", "beam_size_mm", "matrix_mm"]).agg(
        n=("config", "size"), frac_outside_max=("frac_outside", "max"), frac_edge_max=("frac_edge_0p5", "max"))
    print(g.round(4).to_string())
