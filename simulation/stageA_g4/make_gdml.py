"""Write GDML geometries for feasibility test 4. Alloy compositions = placeholder grades (T-01, tag A)."""
from pathlib import Path
OUT = Path(__file__).resolve().parent / "gdml"; OUT.mkdir(exist_ok=True)
ALLOYS = {  # name: (mass fractions by NIST element material, density g/cm3)  -- same as spike5
    "Cu": ({"G4_Cu": 1.0}, 8.96),
    "CuZn37": ({"G4_Cu": 0.63, "G4_Zn": 0.37}, 8.44),
    "CuZn39Pb3": ({"G4_Cu": 0.58, "G4_Zn": 0.39, "G4_Pb": 0.03}, 8.47),
    "CuSn8": ({"G4_Cu": 0.918, "G4_Sn": 0.08, "G4_P": 0.002}, 8.80),
    "CuNi10Fe1Mn": ({"G4_Cu": 0.875, "G4_Ni": 0.10, "G4_Fe": 0.015, "G4_Mn": 0.01}, 8.90),
}
SCINT = {"CsI": "G4_CESIUM_IODIDE", "GOS": "G4_GADOLINIUM_OXYSULFIDE"}

def box(name, x, y, z): return f'<box name="{name}" x="{x}" y="{y}" z="{z}" lunit="mm"/>'

def trans(alloy, t_mm):
    fr, rho = ALLOYS[alloy]
    mat = f'<material name="{alloy}" state="solid"><D value="{rho}" unit="g/cm3"/>' + "".join(
        f'<fraction n="{v}" ref="{k}"/>' for k, v in fr.items()) + "</material>"
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<gdml xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://service-spi.web.cern.ch/service-spi/app/releases/GDML/schema/gdml.xsd">
<define/>
<materials>{mat}</materials>
<solids>{box("WorldS", 400, 400, 400)}{box("ObjectS", 200, 200, t_mm)}{box("PlaneS", 200, 200, 0.001)}</solids>
<structure>
<volume name="Object"><materialref ref="{alloy}"/><solidref ref="ObjectS"/></volume>
<volume name="Plane"><materialref ref="G4_Galactic"/><solidref ref="PlaneS"/></volume>
<volume name="World"><materialref ref="G4_Galactic"/><solidref ref="WorldS"/>
 <physvol name="Object"><volumeref ref="Object"/><position name="op" x="0" y="0" z="0" unit="mm"/></physvol>
 <physvol name="Plane"><volumeref ref="Plane"/><position name="pp" x="0" y="0" z="100" unit="mm"/></physvol>
</volume>
</structure>
<setup name="Default" version="1.0"><world ref="World"/></setup>
</gdml>'''

def scint(kind, t_mm):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<gdml xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://service-spi.web.cern.ch/service-spi/app/releases/GDML/schema/gdml.xsd">
<define/><materials/>
<solids>{box("WorldS", 100, 100, 100)}{box("ScintS", 2.5, 2.5, t_mm)}{box("ObjectS", 1, 1, 0.001)}</solids>
<structure>
<volume name="Scint"><materialref ref="{SCINT[kind]}"/><solidref ref="ScintS"/></volume>
<volume name="Object"><materialref ref="G4_Galactic"/><solidref ref="ObjectS"/></volume>
<volume name="World"><materialref ref="G4_Galactic"/><solidref ref="WorldS"/>
 <physvol name="Scint"><volumeref ref="Scint"/><position name="sp" x="0" y="0" z="0" unit="mm"/></physvol>
</volume>
</structure>
<setup name="Default" version="1.0"><world ref="World"/></setup>
</gdml>'''

for a in ALLOYS:
    for t in (5, 20):
        (OUT / f"trans_{a}_{t}mm.gdml").write_text(trans(a, t))
for k in SCINT:
    for t in (0.5, 2.0):
        (OUT / f"scint_{k}_{t}mm.gdml").write_text(scint(k, t))
print(sorted(p.name for p in OUT.iterdir()))
