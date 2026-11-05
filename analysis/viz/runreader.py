"""Read every histogram out of one Allpix2 ROOT file.

Production code today reads two of the ~40 objects in each file
(charge/cluster_charge and event_size_clusters). Everything else -- cluster
sizes, residuals, efficiency maps, hit maps, pixel/seed/total charge -- is
already on disk and never looked at. This module reads all of it, uniformly.

uproot 5.7.4 quirks this works around (all verified against real files, see
tests/test_runreader.py):

  * TProfile2D.counts()  raises IndexError -- it slices a flat fBinEntries as
    if it were 2D. We reshape (ny+2, nx+2), strip the under/overflow ring and
    transpose to uproot's [x, y] convention. Verified: transposed gives zero
    bins with count==0 but value!=0; untransposed gives thousands.
  * TProfile.counts()    returns n_bins + 2 -- it includes under/overflow, so
    it is off by one against values(). We strip the ring ourselves.
  * TProfile/TProfile2D  have no to_numpy() at all.
  * A profile bin with zero entries still returns a number from values(). Those
    are masked to NaN here, because plotting them renders pure noise.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import uproot

from analysis.viz.registry import RunKey, parse_name

# Families group the ~40 histograms into readable sections on a run page.
FAMILY_OF_PREFIX = {
    "cluster_size": "cluster_size",
    "charge": "charge",
    "residuals": "residuals",
    "efficiency": "efficiency",
}
_OCCUPANCY = {"hit_map", "hit_map_global", "hit_map_global_mc",
              "hit_map_local", "hit_map_local_mc"}
_EVENT_SIZE = {"event_size_pixels", "event_size_clusters"}

FAMILY_ORDER = ("event_size", "occupancy", "cluster_size",
                "charge", "residuals", "efficiency", "other")


def _family(key: str) -> str:
    head = key.split("/")[0]
    if key in _EVENT_SIZE:
        return "event_size"
    if key in _OCCUPANCY:
        return "occupancy"
    return FAMILY_OF_PREFIX.get(head, "other")


# ROOT axis titles carry TLatex markup. Decode the few that actually occur so
# the page never shows "#mum" and never guesses a unit.
_ROOT_MARKUP = {
    "#mum": "\u00b5m", "#mu": "\u00b5", "#circ": "\u00b0",
    "#pm": "\u00b1", "#times": "\u00d7", "#Delta": "\u0394",
    "_{": "", "^{": "", "}": "",
}
# Allpix uses both "title [unit]" and "title (unit)" in its axis titles.
_UNIT_RE = re.compile(r"[\[(]([^\])]+)[\])]\s*$")


def decode_root_title(title: str) -> str:
    out = title
    for k, v in _ROOT_MARKUP.items():
        out = out.replace(k, v)
    return out.strip()


@dataclass(frozen=True)
class Axis:
    title: str
    n: int
    low: float
    high: float
    edges: np.ndarray

    @property
    def centers(self) -> np.ndarray:
        return (self.edges[:-1] + self.edges[1:]) / 2.0

    @property
    def label(self) -> str:
        """Human-readable axis title, TLatex markup decoded."""
        return decode_root_title(self.title)

    @property
    def unit(self) -> str:
        """Unit parsed out of the trailing [..] of the axis title.

        Read, never assumed: residual_r is in micrometres while hit_map_local is
        in millimetres, and hardcoding either produces numbers wrong by 1000x.
        """
        m = _UNIT_RE.search(self.title)
        if not m:
            return ""
        # Allpix's own title for hit_map_global_mc is "x [mm[]", so strip any
        # leftover bracket rather than rendering upstream's typo on every page.
        return decode_root_title(m.group(1)).strip("[]()")


@dataclass(frozen=True)
class HistData:
    key: str                      # "charge/cluster_charge"
    path: str                     # full in-file path
    classname: str                # TH1D | TH2D | TProfile | TProfile2D
    family: str
    title: str
    axes: tuple[Axis, ...]
    values: np.ndarray            # profiles: NaN where no entries
    counts: np.ndarray | None     # profiles only, correctly de-ringed
    errors: np.ndarray | None
    entries: float
    underflow: float
    overflow: float
    stats: dict[str, float] = field(default_factory=dict)

    @property
    def is_profile(self) -> bool:
        return self.classname.startswith("TProfile")

    @property
    def ndim(self) -> int:
        return len(self.axes)


@dataclass(frozen=True)
class RunData:
    key: RunKey | None
    root_path: Path
    detector_dir: str             # "medipix3_detector"
    hists: dict[str, HistData]
    geometry: dict[str, float]
    warnings: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """True for a truncated run: the file exists but Allpix wrote no
        histograms. Six s2_cdte_* files in data/ are like this (1.8 kB, only
        empty module directories) -- aborted runs that were never re-run."""
        return not self.hists

    def by_family(self) -> dict[str, list[HistData]]:
        out: dict[str, list[HistData]] = {}
        for h in self.hists.values():
            out.setdefault(h.family, []).append(h)
        return {f: out[f] for f in FAMILY_ORDER if f in out}


def _axis(obj, which: str) -> Axis:
    ax = obj.member(which)
    n = int(ax.member("fNbins"))
    low = float(ax.member("fXmin"))
    high = float(ax.member("fXmax"))
    try:
        bins = np.asarray(ax.member("fXbins"), dtype=float)
    except Exception:
        bins = np.array([])
    edges = bins if bins.size == n + 1 else np.linspace(low, high, n + 1)
    return Axis(str(ax.member("fTitle") or ""), n, low, high, edges)


def _profile_counts(obj, shape: tuple[int, ...]) -> np.ndarray:
    """fBinEntries without the under/overflow ring, in uproot's axis order."""
    raw = np.asarray(obj.member("fBinEntries"), dtype=float)
    if len(shape) == 1:
        return raw[1:-1]
    nx, ny = shape
    return raw.reshape(ny + 2, nx + 2)[1:-1, 1:-1].T


def _stats(h_values: np.ndarray, counts: np.ndarray | None,
           axes: tuple[Axis, ...], entries: float,
           underflow: float, overflow: float) -> dict[str, float]:
    v = np.asarray(h_values, dtype=float)
    finite = v[np.isfinite(v)]
    weights = counts if counts is not None else v

    out: dict[str, float] = {
        "entries": float(entries),
        "integral": float(np.nansum(v)),
        "n_bins": int(v.size),
        "n_nonzero": int(np.count_nonzero(np.nan_to_num(v))),
        "min": float(finite.min()) if finite.size else math.nan,
        "max": float(finite.max()) if finite.size else math.nan,
        "underflow": float(underflow),
        "overflow": float(overflow),
    }
    out["frac_nonzero"] = out["n_nonzero"] / v.size if v.size else 0.0

    # Weighted mean/std along each axis. For a plain histogram the bin content
    # IS the weight; for a profile the entry count is.
    w = np.nan_to_num(np.asarray(weights, dtype=float), nan=0.0)
    w = np.where(w < 0, 0.0, w)
    for i, ax in enumerate(axes):
        c = ax.centers
        wi = w if w.ndim == 1 else w.sum(axis=1 - i)
        tot = wi.sum()
        suffix = "x" if i == 0 else "y"
        if tot > 0 and wi.size == c.size:
            mean = float((wi * c).sum() / tot)
            var = float((wi * (c - mean) ** 2).sum() / tot)
            out[f"mean_{suffix}"] = mean
            out[f"std_{suffix}"] = math.sqrt(max(var, 0.0))
        else:
            out[f"mean_{suffix}"] = math.nan
            out[f"std_{suffix}"] = math.nan
        out[f"axis_{suffix}_low"] = ax.low
        out[f"axis_{suffix}_high"] = ax.high
        out[f"axis_{suffix}_nbins"] = float(ax.n)

    flat = np.nan_to_num(v)
    if flat.size:
        idx = int(np.argmax(flat))
        out["argmax_bin"] = float(idx)
        if v.ndim == 1:
            out["argmax_center"] = float(axes[0].centers[idx])
        else:
            ix, iy = np.unravel_index(idx, v.shape)
            out["argmax_center_x"] = float(axes[0].centers[ix])
            out["argmax_center_y"] = float(axes[1].centers[iy])
    return out


def _read_hist(obj, key: str, path: str) -> HistData | None:
    cls = obj.classname
    if cls not in ("TH1D", "TH1F", "TH2D", "TH2F", "TProfile", "TProfile2D"):
        return None

    is_2d = cls in ("TH2D", "TH2F", "TProfile2D")
    axes = (_axis(obj, "fXaxis"),) + ((_axis(obj, "fYaxis"),) if is_2d else ())

    # values(flow=True) is the version-independent way to reach the
    # under/overflow ring; the raw member name differs between streamers.
    try:
        flow = np.asarray(obj.values(flow=True), dtype=float)
        if is_2d:
            underflow = float(flow[0, :].sum() + flow[:, 0].sum() - flow[0, 0])
            overflow = float(flow[-1, :].sum() + flow[:, -1].sum() - flow[-1, -1])
        else:
            underflow, overflow = float(flow[0]), float(flow[-1])
    except Exception:
        underflow = overflow = 0.0

    counts = None
    if cls.startswith("TProfile"):
        shape = (axes[0].n, axes[1].n) if is_2d else (axes[0].n,)
        counts = _profile_counts(obj, shape)
        values = np.asarray(obj.values(), dtype=float)
        # A zero-entry profile bin still returns a number. Mask it: plotting
        # those renders noise that looks like data.
        values = np.where(counts > 0, values, np.nan)
        errors = np.asarray(obj.errors(), dtype=float)
        errors = np.where(counts > 0, errors, np.nan)
    else:
        values = np.asarray(obj.to_numpy()[0], dtype=float)
        try:
            errors = np.asarray(obj.errors(), dtype=float)
        except Exception:
            errors = np.sqrt(np.clip(values, 0, None))

    return HistData(
        key=key, path=path, classname=cls, family=_family(key),
        title=str(obj.member("fTitle") or key),
        axes=axes, values=values, counts=counts, errors=errors,
        entries=float(obj.member("fEntries")),
        underflow=underflow, overflow=overflow,
        stats=_stats(values, counts, axes, float(obj.member("fEntries")),
                     underflow, overflow),
    )


def _geometry(hists: dict[str, HistData]) -> dict[str, float]:
    """Recover sensor geometry from the histogram axes.

    Pixel count comes from hit_map's axes and pitch from hit_map_local's extent
    divided by that count. Sensor *thickness* is not encoded anywhere in the
    ROOT -- that is what derive.implied_thickness estimates from efficiency.
    """
    geo: dict[str, float] = {}
    hm = hists.get("hit_map")
    if hm is not None and hm.ndim == 2:
        geo["n_pixels_x"] = float(hm.axes[0].n)
        geo["n_pixels_y"] = float(hm.axes[1].n)
    loc = hists.get("hit_map_local")
    if loc is not None and loc.ndim == 2 and "n_pixels_x" in geo:
        span_x = loc.axes[0].high - loc.axes[0].low
        span_y = loc.axes[1].high - loc.axes[1].low
        if geo["n_pixels_x"]:
            geo["pixel_pitch_x_um"] = round(span_x / geo["n_pixels_x"] * 1000.0, 3)
        if geo["n_pixels_y"]:
            geo["pixel_pitch_y_um"] = round(span_y / geo["n_pixels_y"] * 1000.0, 3)
        geo["sensor_span_x_mm"] = span_x
        geo["sensor_span_y_mm"] = span_y
    return geo


def read_run(root_path: Path) -> RunData:
    """Read every histogram in one ROOT file. Raises if the file is unreadable."""
    root_path = Path(root_path)
    hists: dict[str, HistData] = {}
    detector_dir = ""

    hist_classes = {"TH1D", "TH1F", "TH2D", "TH2F", "TProfile", "TProfile2D"}

    with uproot.open(root_path) as f:
        # classnames() lets us skip the TDirectory entries (charge/,
        # cluster_size/, residuals/, efficiency/) without opening them.
        for full, cls in f.classnames(recursive=True).items():
            if cls not in hist_classes:
                continue
            name = full.split(";")[0]
            if not name.startswith("DetectorHistogrammer/"):
                continue
            rest = name[len("DetectorHistogrammer/"):]
            if "/" not in rest:
                continue
            det, _, key = rest.partition("/")
            detector_dir = detector_dir or det
            if det != detector_dir:
                continue
            try:
                obj = f[full]
            except Exception:
                continue
            h = _read_hist(obj, key, name)
            if h is not None:
                hists[key] = h

    warnings: list[str] = []
    if not hists:
        warnings.append(
            "no DetectorHistogrammer output in this file -- the run was "
            "truncated or aborted; nothing can be derived from it"
        )
    else:
        missing = {"charge/cluster_charge", "event_size_clusters"} - hists.keys()
        for key in sorted(missing):
            warnings.append(f"expected histogram {key!r} is absent")

    return RunData(
        key=parse_name(root_path.stem),
        root_path=root_path,
        detector_dir=detector_dir,
        hists=hists,
        geometry=_geometry(hists),
        warnings=tuple(warnings),
    )


def read_run_or_none(root_path: Path) -> RunData | None:
    """Graceful variant: ROOT files are not in git, so a fresh clone has none.

    Callers render provenance, config and golden-sourced values instead, and
    say the ROOT is absent -- never an empty chart.
    """
    try:
        if not Path(root_path).exists():
            return None
        return read_run(root_path)
    except Exception:
        return None
