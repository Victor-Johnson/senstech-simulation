"""Exp 0 X0-T transport check through the full Stage-A geometry (PH-14 ruling a).

open:   data/protocol_runs/stageA/check_linda_open_150kVp       (5e6 primaries, same geometry, no object)
object: data/protocol_runs/stageA/check_linda_CuZn39Pb3_5mm_150kVp (5e7 primaries)
Unscattered primaries (origin 0) per 2 keV bin, ratio object/open (normalised per primary) vs
exp(-mu_G4 * rho * t / cos(theta)) with Geant4's own mu (stagea_spike mu mode), and vs XCOM.
Also reports the scatter composition at the plane (scatter-to-primary ratio by origin and last volume).
Output: analysis/protocol/exp0/transport_check.csv, exp0/stageA_spr.csv
"""
from pathlib import Path
import numpy as np, pandas as pd
from analysis.protocol.phasespace import read, ORIGIN, VOLUME
R = Path(__file__).resolve().parents[2]
O = R / "analysis/protocol/exp0"
A = R / "data/protocol_runs/stageA"
RHO, T_MM = 8.47, 5.0
op, mo = read(A / "check_linda_open_150kVp")
ob, mb = read(A / "check_linda_CuZn39Pb3_5mm_150kVp")
g4 = pd.read_csv(R / "data/protocol_runs/g4mu/mu_CuZn39Pb3.csv").set_index("energy_keV").total_with_coherent
xc = pd.read_csv(R / "analysis/protocol/reference/xcom/CuZn39Pb3.csv", keep_default_na=False)
xc = xc[xc.edge == ""].set_index("energy_keV").total_with_coherent
edges = np.arange(40, 152, 2.0)
c = 0.5 * (edges[1:] + edges[:-1])
po = op[op.origin == 0]; pb = ob[ob.origin == 0]
n_o = np.histogram(po.E_keV, edges)[0]; n_b = np.histogram(pb.E_keV, edges)[0]
ratio = (n_b / mb["n_primaries"]) / np.where(n_o > 0, n_o / mo["n_primaries"], np.nan)
sig = ratio * np.sqrt(1 / np.maximum(n_b, 1) + 1 / np.maximum(n_o, 1))
inv_cos = float(np.mean(1 / pb.uz)) if len(pb) else 1.0
K_EDGES_KEV = [88.005]  # Pb K-edge (only absorption edge of CuZn39Pb3 in 40-150 keV)
def mu_at(mu, E):
    # log-log interpolation that never crosses an absorption edge: use the two grid points on the same side
    lo, hi = np.floor(E), np.ceil(E)
    for k in K_EDGES_KEV:
        if lo < k <= E: lo = hi = np.ceil(E)
        if E < k <= hi: lo = hi = np.floor(E)
    if lo == hi: return float(mu.loc[lo])
    return float(np.exp(np.interp(np.log(E), [np.log(lo), np.log(hi)], [np.log(mu.loc[lo]), np.log(mu.loc[hi])])))
def expect(mu):
    # bin-average of exp(-mu rho t / cos) on a 0.1 keV sub-grid (spectrum assumed flat within 2 keV)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        Es = np.arange(lo + 0.05, hi, 0.1)
        out.append(np.mean([np.exp(-mu_at(mu, E) * RHO * T_MM / 10 * inv_cos) for E in Es]))
    return np.array(out)
t_g4, t_x = expect(g4), expect(xc)
d = pd.DataFrame(dict(E_keV=c, n_open=n_o, n_object=n_b, T_mc=ratio, T_mc_sigma=sig, T_g4mu=t_g4, T_xcom=t_x))
d["pull_vs_g4"] = (d.T_mc - d.T_g4mu) / d.T_mc_sigma
d["rel_vs_xcom"] = d.T_mc / d.T_xcom - 1
O.mkdir(parents=True, exist_ok=True); d.to_csv(O / "transport_check.csv", index=False)
d["edge_bin"] = [any(lo < k < hi for k in K_EDGES_KEV) for lo, hi in zip(edges[:-1], edges[1:])]
d.to_csv(O / "transport_check.csv", index=False)
ok = d[(d.n_object >= 50) & ~d.edge_bin]
print("edge bins (reported, excluded from chi2):"); print(d[d.edge_bin][["E_keV", "T_mc", "T_mc_sigma", "T_g4mu", "pull_vs_g4"]].round(4).to_string(index=False))
pd.set_option("display.width", 200)
print(f"mean 1/cos = {inv_cos:.5f}; bins with >=50 counts: {len(ok)}")
print(ok[["E_keV", "n_object", "T_mc", "T_mc_sigma", "T_g4mu", "pull_vs_g4", "rel_vs_xcom"]].round(4).to_string(index=False))
print(f"chi2/ndf vs G4 mu: {np.sum(ok.pull_vs_g4**2):.1f}/{len(ok)};  max |pull| {ok.pull_vs_g4.abs().max():.2f}")
# scatter composition at the plane, object run, within the LINDA active area (|x|<1.32, |y|<3.3 mm)
m = (ob.x_mm.abs() < 1.32) & (ob.y_mm.abs() < 3.3)
s = ob[m].groupby(["origin", "last_volume"]).size().rename("n").reset_index()
s["origin"] = s.origin.map(ORIGIN); s["last_volume"] = s.last_volume.map(VOLUME)
prim = s[s.origin == "primary"].n.sum()
s["per_primary"] = s.n / prim
s.to_csv(O / "stageA_spr.csv", index=False)
print("\nComposition at z=639 mm inside the LINDA active area (5 mm leaded brass, 150 kVp 1 mm Cu):")
print(s.round(4).to_string(index=False)); print(f"SPR total = {(s.n.sum() - prim) / prim:.3f}")
