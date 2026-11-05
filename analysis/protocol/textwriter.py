"""Parse Allpix2 TextWriter output into a per-event, per-pixel charge table.

Only the PixelCharge records are read; MCParticle blocks are skipped.
Returns a pandas DataFrame with columns: event, detector, px, py, charge_e.
Charge is reported as a positive number of collected carriers.
"""
from __future__ import annotations
import re
from pathlib import Path
import pandas as pd

_EVENT = re.compile(r"^=== (\d+) ===")
_DET = re.compile(r"^--- (\S+) ---$")
_PIX = re.compile(r"^Pixel: \((\d+), (\d+)\)")
_CHG = re.compile(r"^Charge: (-?\d+) e")


def read_pixel_charge(path: str | Path) -> tuple[pd.DataFrame, int]:
    rows, event, det, in_pc, pix = [], None, None, False, None
    n_events = 0
    with open(path) as f:
        for line in f:
            if line.startswith("==="):
                m = _EVENT.match(line)
                if m:
                    event = int(m.group(1)); n_events = max(n_events, event)
                    det = None
                continue
            if line.startswith("--- "):
                m = _DET.match(line.strip())
                if m and "information" not in line and "Printing" not in line:
                    det = m.group(1)
                in_pc = line.startswith("--- Pixel charge information")
                continue
            if in_pc:
                if line.startswith("Pixel:"):
                    m = _PIX.match(line); pix = (int(m.group(1)), int(m.group(2)))
                elif line.startswith("Charge:"):
                    q = int(_CHG.match(line).group(1))
                    rows.append((event, det, pix[0], pix[1], abs(q)))
                    in_pc = False
    df = pd.DataFrame(rows, columns=["event", "detector", "px", "py", "charge_e"])
    return df, n_events
