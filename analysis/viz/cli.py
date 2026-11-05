"""Command line entry point: python -m analysis.viz <command>

Phase 1 commands:
  ls     enumerate discovered runs, report anything that parses to nothing
  show   dump every histogram of one run as a text table
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from analysis.viz import registry as reg
from analysis.viz.runreader import read_run_or_none


def _fmt(x: float, width: int = 12) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-".rjust(width)
    if isinstance(x, float) and (abs(x) >= 1e5 or (0 < abs(x) < 1e-3)):
        return f"{x:.4e}".rjust(width)
    return f"{x:,.4f}".rstrip("0").rstrip(".").rjust(width) if isinstance(x, float) else str(x).rjust(width)


def cmd_ls(args: argparse.Namespace) -> int:
    d = reg.discover(args.data_dir, args.campaign)
    by = d.by_campaign()

    if args.check_roundtrip:
        failures = []
        for key in d.runs:
            try:
                name = reg.build_name(key)
            except Exception as exc:
                failures.append((key, f"{type(exc).__name__}: {exc}"))
                continue
            if reg.parse_name(name) != key:
                failures.append((key, f"parses back differently: {name}"))
        print(f"round-trip: {len(d.runs) - len(failures)}/{len(d.runs)} ok")
        for key, why in failures[:20]:
            print(f"  FAIL {key.campaign}/{key.mode} {key.detector}: {why}")
        if failures:
            return 3

    if args.long:
        for key in sorted(d.runs, key=reg.sort_key):
            path = reg.root_path(key, args.data_dir)
            size = path.stat().st_size if path.exists() else 0
            var = " ".join(f"{k}={v}" for k, v in key.variant) or "-"
            print(f"{key.run_id:46s} {key.campaign:30s} {key.mode:12s} "
                  f"{key.detector:14s} {size/1e6:7.2f}MB  {var}")
    else:
        for name, keys in sorted(by.items()):
            spec = reg.CAMPAIGNS[name]
            modes = ", ".join(sorted({k.mode for k in keys}))
            print(f"{name:30s} {len(keys):4d} runs   [{modes}]")
            if args.verbose:
                print(f"{'':32s}{spec.description}")

    print(f"\ntotal: {len(d.runs)} runs")
    if d.unparsed:
        # Never silent: an unrecognised name means a convention the registry
        # does not know, and those runs would otherwise vanish from every
        # downstream count.
        print(f"\nUNPARSED ({len(d.unparsed)}) -- no registry pattern matches:")
        for p in d.unparsed:
            print(f"  {p.name}")
        return 3
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    key = reg.parse_name(args.run_id)
    if key is None:
        print(f"'{args.run_id}' matches no registry pattern", file=sys.stderr)
        return 3
    path = reg.root_path(key, args.data_dir)
    run = read_run_or_none(path)
    if run is None:
        print(f"ROOT absent: {path}", file=sys.stderr)
        return 2

    cfg = reg.config_path(key)
    print(f"run       {key.run_id}")
    print(f"campaign  {key.campaign}   mode {key.mode}   detector {key.detector}")
    if key.energy_keV is not None:
        print(f"energy    {key.energy_keV:g} keV")
    if key.variant:
        print("variant   " + "  ".join(f"{k}={v}" for k, v in key.variant))
    print(f"root      {path}  ({path.stat().st_size/1e6:.2f} MB)")
    print(f"config    {cfg if cfg and cfg.exists() else '(absent)'}")
    print(f"detector  {run.detector_dir}")
    if run.geometry:
        print("geometry  " + "  ".join(f"{k}={v:g}" for k, v in run.geometry.items()))
    for w in run.warnings:
        print(f"WARNING   {w}")
    print()

    if run.is_empty:
        return 2

    for family, hists in run.by_family().items():
        print(f"--- {family} ({len(hists)}) " + "-" * (60 - len(family)))
        for h in hists:
            dims = "x".join(str(a.n) for a in h.axes)
            unit = h.axes[0].title or ""
            print(f"  {h.key:44s} {h.classname:11s} {dims:>9s}")
            s = h.stats
            print(f"      entries {s['entries']:>12,.0f}   integral {s['integral']:>14,.3f}"
                  f"   nonzero {s['n_nonzero']:>7,d} ({s['frac_nonzero']*100:5.1f}%)")
            print(f"      mean_x  {s.get('mean_x', float('nan')):>12.5f}   "
                  f"std_x    {s.get('std_x', float('nan')):>14.5f}   "
                  f"range   [{s['min']:.4g}, {s['max']:.4g}]")
            if unit:
                print(f"      axis-x  {unit!r}  [{s['axis_x_low']:g}, {s['axis_x_high']:g}]"
                      f"  under {s['underflow']:g}  over {s['overflow']:g}")
            if args.bins and h.ndim == 1:
                print(f"      {'bin':>5s} {'low':>12s} {'high':>12s} {'value':>14s} {'error':>12s}")
                for i, (lo, hi) in enumerate(zip(h.axes[0].edges[:-1], h.axes[0].edges[1:])):
                    err = h.errors[i] if h.errors is not None else float("nan")
                    print(f"      {i:5d} {lo:12.5g} {hi:12.5g} {h.values[i]:14.6g} {err:12.5g}")
            print()
    return 0


def cmd_spectra(args: argparse.Namespace) -> int:
    from analysis.viz.spectra import campaign_spectra

    if args.campaign not in reg.CAMPAIGNS:
        print(f"unknown campaign: {args.campaign}", file=sys.stderr)
        return 3

    out = campaign_spectra(args.campaign, data_dir=args.data_dir,
                           drop_empty_bins=not args.all_bins, progress=True)
    recon = out["reconciliation"]

    print()
    for name, frame in out.items():
        print(f"{name:34s} {len(frame):>8,} rows")

    if not recon.empty:
        ok_c = int(recon.count_match.sum()) if "count_match" in recon else 0
        ok_r = int(recon.response_match.sum()) if "response_match" in recon else 0
        print()
        print(f"reconciliation   sub-bin counts match window : {ok_c}/{len(recon)}")
        print(f"                 response matches Table 10   : {ok_r}/{len(recon)}")
        if ok_r != len(recon):
            bad = recon[~recon.response_match]
            print("\nMISMATCHES (a finding, not a reason to change Table 10):")
            print(bad[["run_id", "windowed_response",
                       "windowed_response_from_subbins"]].to_string(index=False))

    if args.out_csv:
        target = args.out_dir or (
            reg.REPO_ROOT / "analysis/results" / _results_dir(args.campaign) / "data_csv")
        target.mkdir(parents=True, exist_ok=True)
        written = []
        for name, frame in out.items():
            if frame.empty:
                continue
            path = target / f"{name}.csv"
            # The spectrum is the one output that must never be silently
            # shrunk, so it is written whole; gzip only changes the container.
            if name == "deposited_spectrum" and args.gzip:
                path = path.with_suffix(".csv.gz")
                frame.to_csv(path, index=False, compression="gzip")
            else:
                frame.to_csv(path, index=False)
            written.append(path)
        print()
        for path in written:
            print(f"wrote {path.relative_to(reg.REPO_ROOT)}  "
                  f"({path.stat().st_size/1e6:.2f} MB)")

    return 0 if recon.empty or int(recon.response_match.sum()) == len(recon) else 1


# Campaign name -> analysis/results/<dir>. The results directories predate the
# registry and do not all match the campaign key.
_RESULTS_DIRS = {
    "phase2_selection": "phase2_selection_framework",
    "material_penetration_uniform": "material_penetration_uniform",
    "material_penetration": "material_penetration",
}


def _results_dir(campaign: str) -> str:
    return _RESULTS_DIRS.get(campaign, campaign)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m analysis.viz")
    ap.add_argument("--data-dir", type=Path, default=reg.DATA_DIR)
    sub = ap.add_subparsers(dest="command", required=True)

    p_ls = sub.add_parser("ls", help="enumerate discovered runs")
    p_ls.add_argument("--campaign")
    p_ls.add_argument("-l", "--long", action="store_true", help="one line per run")
    p_ls.add_argument("-v", "--verbose", action="store_true")
    p_ls.add_argument("--check-roundtrip", action="store_true",
                      help="assert build_name(parse_name(x)) == x for every run")
    p_ls.set_defaults(func=cmd_ls)

    p_show = sub.add_parser("show", help="dump every histogram of one run")
    p_show.add_argument("run_id")
    p_show.add_argument("--bins", action="store_true", help="print every bin")
    p_show.set_defaults(func=cmd_show)

    p_spec = sub.add_parser("spectra",
                            help="publish deposited-energy spectra at native resolution")
    p_spec.add_argument("--campaign", required=True)
    p_spec.add_argument("--out-csv", action="store_true", help="write CSVs")
    p_spec.add_argument("--out-dir", type=Path, help="override output directory")
    p_spec.add_argument("--gzip", action="store_true",
                        help="gzip the spectrum CSV (container only, no rebinning)")
    p_spec.add_argument("--all-bins", action="store_true",
                        help="keep zero-count bins (default drops them; native "
                             "widths and bin_index are preserved either way)")
    p_spec.set_defaults(func=cmd_spectra)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
