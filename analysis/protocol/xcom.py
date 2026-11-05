"""Fetch NIST XCOM photon cross sections on a fixed energy grid (reference for Exp 0 data check, PH-14).

Source: NIST XCOM (Berger et al.), web form https://physics.nist.gov/cgi-bin/Xcom/xcom3_3 (mixtures,
mass fractions). Raw HTML responses are kept next to the parsed CSV for provenance.

Run: PYTHONPATH=. ./venv/bin/python analysis/protocol/xcom.py
Output: analysis/protocol/reference/xcom/<material>.csv (+ raw/<material>_<chunk>.html), manifest.csv
Columns (cm2/g): coherent, incoherent, photoelectric, pair_nuclear, pair_electron,
                 total_with_coherent, total_without_coherent. Absorption-edge rows are kept with edge label.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import html as htmlmod
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

URL = "https://physics.nist.gov/cgi-bin/Xcom/xcom3_3"
REFERER = "https://physics.nist.gov/cgi-bin/Xcom/xcom2?Method=Mix&Output2=Hand"
OUT = Path(__file__).resolve().parent / "reference" / "xcom"
COLS = ["coherent", "incoherent", "photoelectric", "pair_nuclear", "pair_electron",
        "total_with_coherent", "total_without_coherent"]

# Mass fractions. Alloys = placeholder grades (T-01, tag A); same as spike4/spike5.
MATERIALS = {
    "Cu": {"Cu": 1.0},
    "CuZn37": {"Cu": 0.63, "Zn": 0.37},
    "CuZn39Pb3": {"Cu": 0.58, "Zn": 0.39, "Pb": 0.03},
    "CuSn8": {"Cu": 0.918, "Sn": 0.08, "P": 0.002},
    "CuNi10Fe1Mn": {"Cu": 0.875, "Ni": 0.10, "Fe": 0.015, "Mn": 0.01},
    "CdTe": {"Cd": 0.46837, "Te": 0.53163},
    "CsI": {"Cs": 0.511549, "I": 0.488451},
    "GOS": {"Gd": 0.832, "O": 0.0847, "S": 0.0833},  # Gd2O2S by mass (Gd 157.25, O 16.00, S 32.06)
    "W": {"W": 1.0},
}
ENERGIES_KEV = np.arange(10.0, 301.0, 1.0)
CHUNK = 50


def _post(name: str, comp: dict[str, float], energies_kev: np.ndarray) -> str:
    form = {
        "Name": re.sub(r"[^A-Za-z]", "", name) or "mat",
        "Formulae": "\n".join(f"{el} {f}" for el, f in comp.items()),
        "Energies": "\n".join(f"{e / 1000:.6f}" for e in energies_kev),
        "Graph1": "on", "Graph2": "on", "Graph3": "on", "Graph4": "on", "Graph5": "on",
        "Graph6": "on", "Graph7": "on", "NumAdd": "1",
        "WindowXmin": "0.001", "WindowXmax": "100000", "ResizeFlag": "on",
    }
    req = urllib.request.Request(URL, data=urllib.parse.urlencode(form).encode(),
                                 headers={"User-Agent": "Mozilla/5.0 (senstech-simulation research script)",
                                          "Referer": REFERER})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read().decode("latin-1")


def _parse(html_text: str) -> pd.DataFrame:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, flags=re.S | re.I):
        cells = [htmlmod.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S | re.I)]
        nums = [c for c in cells if re.fullmatch(r"[0-9.]+E[-+][0-9]+", c)]
        if len(nums) == 8:
            edge = next((c for c in cells if re.fullmatch(r"[KLM]\d?|\d+\s*[KLM]\d?", c)), "")
            rows.append([edge, float(nums[0]) * 1000] + [float(x) for x in nums[1:]])
    if not rows:
        raise ValueError("no data rows parsed (form changed or error page)")
    return pd.DataFrame(rows, columns=["edge", "energy_keV"] + COLS)


def fetch(name: str, comp: dict[str, float], energies=ENERGIES_KEV, pause_s: float = 2.0) -> pd.DataFrame:
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    parts, queue, k = [], [energies[i:i + CHUNK] for i in range(0, len(energies), CHUNK)], 0
    while queue:
        chunk = queue.pop(0)
        txt = _post(name, comp, chunk)
        (OUT / "raw" / f"{name}_{k}.html").write_text(txt, encoding="latin-1"); k += 1
        time.sleep(pause_s)
        if "XCOM: Error" in txt:
            if "too many" in txt and len(chunk) > 5:   # edges add rows: split and retry
                h = len(chunk) // 2; queue[:0] = [chunk[:h], chunk[h:]]; continue
            raise RuntimeError(f"XCOM error page for {name} chunk {k - 1}")
        parts.append(_parse(txt))
    df = pd.concat(parts, ignore_index=True).drop_duplicates(["energy_keV", "edge"]).sort_values(["energy_keV", "edge"])
    df.insert(0, "material", name)
    df.to_csv(OUT / f"{name}.csv", index=False)
    return df


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    man = []
    for name, comp in MATERIALS.items():
        f = OUT / f"{name}.csv"
        df = pd.read_csv(f, keep_default_na=False) if f.exists() else fetch(name, comp)
        grid = df[df.edge == ""]
        missing = sorted(set(ENERGIES_KEV) - set(np.round(grid.energy_keV, 6)))
        csv_bytes = (OUT / f"{name}.csv").read_bytes()
        man.append(dict(material=name, composition="; ".join(f"{k}:{v}" for k, v in comp.items()),
                        rows=len(df), grid_points=len(grid), missing_grid_points=len(missing),
                        edges=";".join(f"{e}@{x:.3f}" for e, x in zip(df.edge, df.energy_keV) if e),
                        sha256=hashlib.sha256(csv_bytes).hexdigest()[:16],
                        source=URL, fetched_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
        print(name, len(grid), "grid points;", "missing", len(missing), ";", man[-1]["edges"])
    pd.DataFrame(man).to_csv(OUT / "manifest.csv", index=False)
