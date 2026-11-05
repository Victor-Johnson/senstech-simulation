"""Audit every Allpix config in simulation/ for the 25 ns integration_time default (PH-12).

Writes analysis/protocol/audit/integration_time_audit.csv: one row per config with predicted
electron/hole full-thickness transit, the rule verdict, and whether a ROOT output exists in data/.
Run: PYTHONPATH=. ./venv/bin/python analysis/protocol/audit_integration_time.py
"""
from pathlib import Path
import pandas as pd
from analysis.protocol.config_rules import REPO, check_integration_time

OUT = REPO / "analysis/protocol/audit"; OUT.mkdir(parents=True, exist_ok=True)
rows = []
for conf in sorted((REPO / "simulation").rglob("*.conf")):
    txt = conf.read_text(errors="ignore")
    if "[GenericPropagation]" not in txt and "[TransientPropagation]" not in txt:
        continue
    r = check_integration_time(conf)
    root = REPO / "data" / (conf.stem + ".root")
    r["root_exists"] = root.exists()
    r["campaign"] = conf.parent.name
    rows.append(r)
df = pd.DataFrame(rows)
df["rerun_selected"] = (df.root_exists & ~df.integration_time_set & (df.bias_V.abs() < 500))
df.to_csv(OUT / "integration_time_audit.csv", index=False)
print("configs with propagation:", len(df), "| default 25 ns:", (~df.integration_time_set).sum(),
      "| with ROOT output:", df.root_exists.sum(), "| default & ROOT:", (df.root_exists & ~df.integration_time_set).sum())
print("rule fails (default & ROOT):", (df.root_exists & ~df.integration_time_set & (df.ok == False)).sum())
g = df[df.root_exists & ~df.integration_time_set].groupby(["campaign", "bias_V"]).agg(
    n=("config", "size"), e_transit_max_ns=("electron_transit_ns", "max"), rule_fail=("ok", lambda s: int((s == False).sum())))
print(g.to_string())
print("\nselected for re-run (|bias| < 500 V, default, ROOT exists):", df.rerun_selected.sum())
