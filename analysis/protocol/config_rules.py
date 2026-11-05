"""Allpix config parsing, drift-time prediction and the integration_time validation rule.

Background: Allpix GenericPropagation defaults to integration_time = 25 ns and silently
drops charge still drifting when it expires (feasibility test 1: 60 keV full-energy fraction
0.41 vs 0.90 at 300 V / 1 mm CdTe). Rule (register PH-12):

    integration_time >= SAFETY * slowest full-thickness transit of every propagated carrier

Electrons are always propagated; holes only if propagate_holes = true (or TransientPropagation,
which always propagates both). Transit is integrated numerically through the configured field.

Field models (Allpix ElectricFieldReader):
  constant: E = |V| / d
  linear:   E(x) = (|V| - |V_d|)/d + 2|V_d|/d * (1 - x/d), x = depth from the depleting side.
            Requires |V| >= |V_d| (fully depleted); otherwise an undepleted region exists and
            the rule reports transit = inf.
Mobility models:
  constant: mobility_electron / mobility_hole from config.
  jacoboni: Jacoboni-Canali (silicon parameters, as Allpix implements), field-dependent.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parents[2]
SAFETY = 1.5
DEFAULT_INTEGRATION_NS = 25.0
DEFAULT_TEMPERATURE_K = 293.0

_UNIT = {"ns": 1.0, "us": 1e3, "ms": 1e6, "ps": 1e-3, "s": 1e9}
_LEN = {"um": 1e-4, "mm": 0.1, "cm": 1.0, "nm": 1e-7}  # -> cm


def parse_conf(path: str | Path) -> dict[str, dict[str, str]]:
    """Return {section: {key: raw_value}} (first section occurrence wins; values unquoted)."""
    out, sec = {}, None
    for line in Path(path).read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line:
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            sec = m.group(1); out.setdefault(sec, {}); continue
        if "=" in line and sec is not None:
            k, v = (s.strip() for s in line.split("=", 1))
            out[sec].setdefault(k, v.strip('"'))
    return out


def _qty(v: str, table: dict[str, float]) -> float:
    m = re.match(r"^\s*([-+0-9.eE]+)\s*([a-zA-Z]+)\s*$", v)
    if not m:
        raise ValueError(f"cannot parse quantity {v!r}")
    return float(m.group(1)) * table[m.group(2)]


def volts(v: str) -> float:
    m = re.match(r"^\s*([-+0-9.eE]+)\s*(k?V)\s*$", v)
    return float(m.group(1)) * (1e3 if m.group(2) == "kV" else 1.0)


def mobility_constant(v: str) -> float:
    m = re.match(r"^\s*([0-9.eE+-]+)\s*cm\*cm/V/s\s*$", v)
    if not m:
        raise ValueError(f"cannot parse mobility {v!r}")
    return float(m.group(1))


def jacoboni_velocity(E: np.ndarray, carrier: str, T: float) -> np.ndarray:
    """Drift velocity (cm/s) for field E (V/cm), Jacoboni-Canali with silicon parameters."""
    if carrier == "e":
        vm, Ec, beta = 1.53e9 * T ** -0.87, 1.01 * T ** 1.55, 2.57e-2 * T ** 0.66
    else:
        vm, Ec, beta = 1.62e8 * T ** -0.52, 1.24 * T ** 1.68, 0.46 * T ** 0.17
    return vm * (E / Ec) / (1 + (E / Ec) ** beta) ** (1 / beta)


@dataclass
class DriftSpec:
    thickness_cm: float
    bias_V: float
    depletion_V: float | None
    field_model: str
    mobility_model: str
    mu_e: float | None
    mu_h: float | None
    temperature_K: float


def transit_ns(s: DriftSpec, carrier: str, n: int = 4000) -> float:
    """Full-thickness transit time in ns (upper bound for any interaction depth)."""
    d, V = s.thickness_cm, abs(s.bias_V)
    x = (np.arange(n) + 0.5) / n * d
    if s.field_model == "linear":
        Vd = abs(s.depletion_V) if s.depletion_V is not None else V
        if V < Vd:
            return float("inf")
        E = (V - Vd) / d + 2 * Vd / d * (1 - x / d)
    else:  # constant (and anything else treated as uniform)
        E = np.full_like(x, V / d)
    if s.mobility_model == "jacoboni":
        v = jacoboni_velocity(E, carrier, s.temperature_K)
    else:
        mu = s.mu_e if carrier == "e" else s.mu_h
        if mu is None:
            raise ValueError("constant mobility model without mobility value")
        v = mu * E
    with np.errstate(divide="ignore"):
        return float(np.sum((d / n) / v) * 1e9)


def resolve_detector_file(conf: dict, conf_path: Path) -> Path | None:
    raw = conf.get("Allpix", {}).get("detectors_file")
    if not raw:
        return None
    p = Path(raw)
    if raw.startswith("/data/simulation/"):
        p = REPO / "simulation" / raw[len("/data/simulation/"):]
    elif not p.is_absolute():
        p = conf_path.parent / raw
    return p if p.exists() else None


def drift_spec(conf_path: str | Path) -> tuple[DriftSpec | None, dict]:
    conf_path = Path(conf_path)
    c = parse_conf(conf_path)
    info: dict = {"config": str(conf_path.relative_to(REPO)) if conf_path.is_relative_to(REPO) else str(conf_path)}
    prop_sec = "TransientPropagation" if "TransientPropagation" in c else ("GenericPropagation" if "GenericPropagation" in c else None)
    info["propagation"] = prop_sec
    if prop_sec is None:
        return None, info
    p, f = c[prop_sec], c.get("ElectricFieldReader", {})
    info["integration_time_ns"] = _qty(p["integration_time"], _UNIT) if "integration_time" in p else DEFAULT_INTEGRATION_NS
    info["integration_time_set"] = "integration_time" in p
    info["propagate_holes"] = prop_sec == "TransientPropagation" or p.get("propagate_holes", "false").lower() == "true"
    det = resolve_detector_file(c, conf_path)
    info["detector_file"] = (str(det.relative_to(REPO)) if det.is_relative_to(REPO) else str(det)) if det else None
    if det is None or "bias_voltage" not in f:
        return None, info
    dc = parse_conf(det)
    thick = None
    for sec in dc.values():
        if "sensor_thickness" in sec:
            thick = _qty(sec["sensor_thickness"], _LEN); info["sensor_material"] = sec.get("sensor_material"); break
    if thick is None:
        return None, info
    mm = p.get("mobility_model", "jacoboni")
    spec = DriftSpec(
        thickness_cm=thick, bias_V=volts(f["bias_voltage"]),
        depletion_V=volts(f["depletion_voltage"]) if "depletion_voltage" in f else None,
        field_model=f.get("model", "linear"), mobility_model=mm,
        mu_e=mobility_constant(p["mobility_electron"]) if "mobility_electron" in p else None,
        mu_h=mobility_constant(p["mobility_hole"]) if "mobility_hole" in p else None,
        temperature_K=float(re.sub(r"[^0-9.]", "", p.get("temperature", "293K")) or DEFAULT_TEMPERATURE_K),
    )
    info.update(thickness_mm=thick * 10, bias_V=spec.bias_V, depletion_V=spec.depletion_V,
                field_model=spec.field_model, mobility_model=mm)
    return spec, info


def check_integration_time(conf_path: str | Path, safety: float = SAFETY) -> dict:
    """Evaluate the rule; returns info dict with 'ok' and 'reason'."""
    spec, info = drift_spec(conf_path)
    if spec is None:
        info.update(ok=None, reason="not checkable (no propagation module / detector / bias)")
        return info
    te = transit_ns(spec, "e")
    th = transit_ns(spec, "h") if info["propagate_holes"] else float("nan")
    slowest = max(te, th) if info["propagate_holes"] else te
    need = safety * slowest
    info.update(electron_transit_ns=te, hole_transit_ns=th, required_ns=need,
                ok=bool(info["integration_time_ns"] >= need))
    info["reason"] = ("ok" if info["ok"] else
                      f"integration_time {info['integration_time_ns']:.0f} ns < {safety} x slowest transit {slowest:.1f} ns")
    return info


class IntegrationTimeError(ValueError):
    pass


def validate(conf_path: str | Path, safety: float = SAFETY) -> None:
    """Reject a config whose integration_time is shorter than the slowest expected drift (PH-12)."""
    r = check_integration_time(conf_path, safety)
    if r["ok"] is False:
        raise IntegrationTimeError(f"{r['config']}: {r['reason']}")
