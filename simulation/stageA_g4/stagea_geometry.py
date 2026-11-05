"""Write Stage-A line geometry (Protocol s5, Table 5) as GDML for simulation/stageA_g4/stagea.cc.

Source frame: focal spot at z = 0, beam along +z, x along the belt, y across. All values tag A (T-12) until
Sens-Tech confirms the machine. Simplifications (each listed in inputs_register.csv, PH-15):
  * tube housing and housing leakage are NOT simulated: the source only samples directions towards the fan
    slit (variance reduction); leakage needs a separate run.
  * tube-exit collimator (15 mm W at z=100, 30 x 6 mm opening) is included; it only matters for slit-edge
    margin photons.
  * fan-defining slit walls are straight, not focused: the along-belt opening is only 2.8-5.3 mm wide, so the
    ray angle in x is < 0.006 rad and a 10 mm deep straight wall clips < 0.06 mm.
  * carbon-fibre belt plate = graphite-like carbon at 1.6 g/cm3.
  * cabinet = four side walls (2 mm steel + 3 mm Pb lining on the inside) at +-D from the axis, z -50..800.
Usage:
  python stagea_geometry.py --alloy CuZn39Pb3 --thickness 10 --fan-slit 2.9 [--no-rails] [--cabinet 250|500|0]
         [--no-object] --out gdml/stagea_<name>.gdml
"""
from __future__ import annotations
import argparse
from pathlib import Path

ALLOYS = {  # T-01 bracket (tag A), mass fractions by NIST element material, density g/cm3
    "Cu": ({"G4_Cu": 1.0}, 8.96),
    "CuZn37": ({"G4_Cu": 0.63, "G4_Zn": 0.37}, 8.44),
    "CuZn39Pb3": ({"G4_Cu": 0.58, "G4_Zn": 0.39, "G4_Pb": 0.03}, 8.47),
    "CuSn8": ({"G4_Cu": 0.918, "G4_Sn": 0.08, "G4_P": 0.002}, 8.80),
    "CuNi10Fe1Mn": ({"G4_Cu": 0.875, "G4_Ni": 0.10, "G4_Fe": 0.015, "G4_Mn": 0.01}, 8.90),
}
# Table 6: fan slit opening at z=500 mm per detector (mm); common 7 mm fan -> (7+0.4)*500/700
FAN_SLIT_MM = {"linda": 2.9, "varex": 5.3, "medipix3": 2.9, "photodiode": 2.8, "common7": 5.29}


def box(n, x, y, z):
    return f'<box name="{n}" x="{x:.4f}" y="{y:.4f}" z="{z:.4f}" lunit="mm"/>'


def build(alloy: str | None, t_mm: float, slit_mm: float, rails: bool, cabinet_mm: float) -> str:
    mats, solids, vols, places = [], [], [], []

    def add(name, solid, mat, x, y, z):
        solids.append(solid.replace('name="S"', f'name="{name}S"'))
        vols.append(f'<volume name="{name}"><materialref ref="{mat}"/><solidref ref="{name}S"/></volume>')
        places.append(f'<physvol name="{name}"><volumeref ref="{name}"/><position name="{name}P" x="{x:.4f}" y="{y:.4f}" z="{z:.4f}" unit="mm"/></physvol>')

    mats.append('<material name="CarbonFibre" state="solid"><D value="1.6" unit="g/cm3"/><fraction n="1.0" ref="G4_C"/></material>')
    # tube-exit collimator, 15 mm W at z 100-115, opening 30 (y) x 6 (x), outer 300 x 300
    zc = 107.5
    add("CollimatorXp", box("S", 147, 300, 15), "G4_W", 3 + 147 / 2, 0, zc)
    add("CollimatorXm", box("S", 147, 300, 15), "G4_W", -(3 + 147 / 2), 0, zc)
    add("CollimatorYp", box("S", 6, 135, 15), "G4_W", 0, 15 + 135 / 2, zc)
    add("CollimatorYm", box("S", 6, 135, 15), "G4_W", 0, -(15 + 135 / 2), zc)
    # fan-defining slit, 10 mm W at z 500-510, opening slit_mm in x, 200 mm in y (covers the 160 mm fan)
    zs, h = 505, slit_mm / 2
    add("SlitXp", box("S", 100, 400, 10), "G4_W", h + 50, 0, zs)
    add("SlitXm", box("S", 100, 400, 10), "G4_W", -(h + 50), 0, zs)
    add("SlitYp", box("S", slit_mm, 100, 10), "G4_W", 0, 100 + 50, zs)
    add("SlitYm", box("S", slit_mm, 100, 10), "G4_W", 0, -(100 + 50), zs)
    if alloy:
        fr, rho = ALLOYS[alloy]
        mats.append(f'<material name="{alloy}" state="solid"><D value="{rho}" unit="g/cm3"/>'
                    + "".join(f'<fraction n="{v}" ref="{k}"/>' for k, v in fr.items()) + "</material>")
        add("Object", box("S", 200, 200, t_mm), alloy, 0, 0, 600 - t_mm / 2)
    add("BeltPVC", box("S", 400, 400, 2), "G4_POLYVINYL_CHLORIDE", 0, 0, 601)
    add("BeltCarbon", box("S", 400, 400, 2), "CarbonFibre", 0, 0, 603)
    if rails:  # steel 20 (y) x 40 (z) at y = +-120, z 604-644, along x
        add("RailP", box("S", 400, 20, 40), "G4_STAINLESS-STEEL", 0, 120, 624)
        add("RailM", box("S", 400, 20, 40), "G4_STAINLESS-STEEL", 0, -120, 624)
    # scoring plane, 1 um vacuum at z = 639 mm, |x|,|y| < 100 (rails at |y| >= 110)
    add("Plane", box("S", 200, 200, 0.001), "G4_Galactic", 0, 0, 639)
    if cabinet_mm > 0:
        D, zlen, zc = cabinet_mm, 850, (800 - 50) / 2
        span = 2 * D + 10
        for s in (+1, -1):  # walls at x = +-D and y = +-D: Pb lining (3 mm, inner) + steel (2 mm, outer)
            add(f"CabinetPbX{'p' if s > 0 else 'm'}", box("S", 3, span, zlen), "G4_Pb", s * (D + 1.5), 0, zc)
            add(f"CabinetFeX{'p' if s > 0 else 'm'}", box("S", 2, span + 10, zlen), "G4_STAINLESS-STEEL", s * (D + 4), 0, zc)
            add(f"CabinetPbY{'p' if s > 0 else 'm'}", box("S", 2 * D, 3, zlen), "G4_Pb", 0, s * (D + 1.5), zc)
            add(f"CabinetFeY{'p' if s > 0 else 'm'}", box("S", 2 * D, 2, zlen), "G4_STAINLESS-STEEL", 0, s * (D + 4), zc)
    world = 2 * max(1200.0, cabinet_mm + 50)
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<gdml xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://service-spi.web.cern.ch/service-spi/app/releases/GDML/schema/gdml.xsd">
<define/>
<materials>{"".join(mats)}</materials>
<solids>{box("WorldS", world, world, world)}{"".join(solids)}</solids>
<structure>
{"".join(vols)}
<volume name="World"><materialref ref="G4_AIR"/><solidref ref="WorldS"/>
{"".join(places)}
</volume>
</structure>
<setup name="Default" version="1.0"><world ref="World"/></setup>
</gdml>'''


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--alloy", default=None); a.add_argument("--thickness", type=float, default=0)
    a.add_argument("--fan-slit", type=float, required=True); a.add_argument("--no-rails", action="store_true")
    a.add_argument("--cabinet", type=float, default=250); a.add_argument("--no-object", action="store_true")
    a.add_argument("--out", required=True)
    o = a.parse_args()
    Path(o.out).parent.mkdir(parents=True, exist_ok=True)
    Path(o.out).write_text(build(None if o.no_object else o.alloy, o.thickness, o.fan_slit, not o.no_rails, o.cabinet))
    print(o.out)
