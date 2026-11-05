"""Before/after table for the integration_time audit (review item 4).

before: data/<name>.root            (original run, GenericPropagation default integration_time = 25 ns)
after:  data/audit_itime/<name>.root (same config and seed, integration_time = 1 us)

Observables (DetectorHistogrammer, both files):
  events_with_cluster  = sum of event_size_clusters bin contents (events with >= 1 cluster; the histogram
                         x-axis starts at 1, so zero-cluster events fill no bin -- see phase2 memory notes)
  clusters             = entries of cluster_charge
  mean_cluster_charge_ke, median_cluster_charge_ke (from the cluster_charge histogram)
  full_energy_frac     = clusters with charge within +-5% of the beam energy, per event (mono runs only)
Writes analysis/protocol/audit/integration_time_before_after.csv and prints the per-campaign summary.
"""
from __future__ import annotations
import re
from pathlib import Path
import numpy as np
import pandas as pd
import uproot

R = Path(__file__).resolve().parents[2]
AUD = R / "analysis/protocol/audit"
W_EV = 4.43


def observables(path: Path, beam_keV: float | None) -> dict:
    with uproot.open(path) as f:
        dets = [k.split("/")[1] for k in f.keys(recursive=True) if k.startswith("DetectorHistogrammer/") and k.count("/") == 1]
        if not dets:
            return {}
        d = dets[0]
        esc = f[f"DetectorHistogrammer/{d}/event_size_clusters"]
        cc = f[f"DetectorHistogrammer/{d}/charge/cluster_charge"]
        n_events = int(f["config/Allpix/number_of_events"].member("fTitle")) if "config/Allpix/number_of_events" in f else None
        vals, edges = cc.to_numpy()
        unit = cc.member("fXaxis").member("fTitle")
    centres = 0.5 * (edges[1:] + edges[:-1])
    scale_ke = 1.0 if "ke" in unit else (1e-3 if re.search(r"\[e\]|\(e\)", unit) else 1.0)
    q_ke = centres * scale_ke
    tot = vals.sum()
    out = dict(detector=d, events_with_cluster=float(esc.values().sum()), clusters=float(tot),
               mean_cluster_charge_ke=float((q_ke * vals).sum() / tot) if tot else np.nan,
               median_cluster_charge_ke=float(q_ke[np.searchsorted(np.cumsum(vals), tot / 2)]) if tot else np.nan,
               charge_axis=unit)
    if beam_keV:
        q_keV = q_ke * 1e3 * W_EV / 1e3
        m = np.abs(q_keV - beam_keV) <= 0.05 * beam_keV
        out["full_energy_clusters"] = float(vals[m].sum())
    return out


def main() -> pd.DataFrame:
    audit = pd.read_csv(AUD / "integration_time_audit.csv")
    sel = audit[audit.rerun_selected]
    subs_f = R / "data/audit_itime/seed_substitutions.csv"
    subs = pd.read_csv(subs_f).set_index("config") if subs_f.exists() else pd.DataFrame()
    inv_f = AUD / "known_invalid_before.csv"
    invalid = pd.read_csv(inv_f) if inv_f.exists() else pd.DataFrame(columns=["pattern", "reason"])
    rows = []
    for _, r in sel.iterrows():
        name = Path(r.config).stem
        before, after = R / "data" / f"{name}.root", R / "data/audit_itime" / f"{name}.root"
        if not after.exists():
            continue
        m = re.search(r"_(\d+)keV", name)
        E = float(m.group(1)) if m else None
        b, a = observables(before, E), observables(after, E)
        if not b or not a:
            continue
        row = dict(config=r.config, campaign=r.campaign, bias_V=r.bias_V, thickness_mm=r.thickness_mm,
                   e_transit_pred_ns=r.electron_transit_ns, beam_keV=E,
                   after_seed_note=(f"after uses seed {subs.loc[r.config, 'replacement_seed']} "
                                    f"(seed {subs.loc[r.config, 'bad_seed']} hung)") if r.config in subs.index else "")
        for k in ("events_with_cluster", "clusters", "mean_cluster_charge_ke", "full_energy_clusters"):
            if k in b:
                row[f"{k}_before"], row[f"{k}_after"] = b[k], a[k]
                row[f"{k}_rel_change"] = a[k] / b[k] - 1 if b[k] else np.nan
        bad = [x.reason for x in invalid.itertuples() if re.search(x.pattern, name)]
        row["before_invalid"] = bool(bad)
        row["note"] = bad[0] if bad else row.get("after_seed_note", "")
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(AUD / "integration_time_before_after.csv", index=False)
    grouped(df).to_csv(AUD / "integration_time_before_after_by_campaign.csv", index=False)
    return df


def grouped(df: pd.DataFrame) -> pd.DataFrame:
    """Table for Alex: per campaign / detector / bias / thickness; runs with an invalid 'before' are excluded."""
    d = df[~df.before_invalid].copy()
    d["detector"] = d.config.str.extract(r"([^/]+)\.conf$")[0].str.replace(r"_\d+keV.*", "", regex=True)
    g = d.groupby(["campaign", "detector", "bias_V", "thickness_mm"], as_index=False).agg(
        runs=("config", "size"), energies_keV=("beam_keV", lambda s: f"{s.min():g}-{s.max():g}"),
        e_transit_ns=("e_transit_pred_ns", "max"),
        events_change_median=("events_with_cluster_rel_change", "median"),
        events_change_max=("events_with_cluster_rel_change", "max"),
        mean_charge_change_median=("mean_cluster_charge_ke_rel_change", "median"),
        full_energy_change_median=("full_energy_clusters_rel_change", "median"),
        full_energy_change_max=("full_energy_clusters_rel_change", "max"))
    g["changed"] = (g.events_change_max.abs() > 0.01) | (g.full_energy_change_max.abs() > 0.01)
    return g.sort_values(["changed", "campaign", "detector"], ascending=[False, True, True])


if __name__ == "__main__":
    df = main()
    pd.set_option("display.width", 220)
    print(f"{len(df)} runs compared")
    g = df.groupby(["campaign", "bias_V", "thickness_mm"]).agg(
        n=("config", "size"), pred_transit_ns=("e_transit_pred_ns", "max"),
        events_change_med=("events_with_cluster_rel_change", "median"),
        events_change_max=("events_with_cluster_rel_change", lambda s: s.abs().max()),
        charge_change_med=("mean_cluster_charge_ke_rel_change", "median"),
        fullE_change_med=("full_energy_clusters_rel_change", "median"))
    print(g.round(4).to_string())
