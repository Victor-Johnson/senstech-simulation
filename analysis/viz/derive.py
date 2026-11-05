"""Per-run derived quantities, each carrying its formula and inputs.

Every function here returns Quantity objects rather than bare floats, so the
run page can show how each number was produced. Where the repo already has a
canonical implementation (binomial_se, the deposited-energy window logic), this
calls or mirrors it exactly so a page and a campaign CSV cannot disagree.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

import analysis.scripts.material_penetration_experiment as _mpe
from analysis.viz import registry as reg
from analysis.viz.detectors import DetectorSpec
from analysis.viz.provenance import RunProvenance
from analysis.viz.quantities import QRef, Quantity
from analysis.viz.runreader import RunData

EPSILON_CDTE_EV = _mpe.EPSILON_CDTE_EV
_CDTE_CSV = (reg.REPO_ROOT / "analysis/results/material_penetration_uniform"
             / "cdte_interaction.csv")

# The implied-thickness estimator inverts eff = 1 - exp(-mu*t), so it is only
# valid where ABSORPTION is what limits detection. Above this efficiency the
# limit is instead the threshold and K-shell fluorescence escape (the Cd/Te
# K-edges sit at 26.7/31.8 keV), and the inversion returns nonsense -- a 1 mm
# sensor at 30 keV measures eff = 0.978 and "implies" 0.30 mm.
#
# 0.90 is calibrated, not guessed: requiring >=10% transmission, every
# physically consistent run in data/ returns its labelled thickness with a
# cross-energy spread of 0.022-0.031 mm. See tests/test_derive.py.
SATURATION_EFF = 0.90

# A correct run returns the SAME thickness at every usable energy. This is the
# tolerance on that flatness, and it is what separates a mislabelled run from a
# merely undocumented one.
THICKNESS_SPREAD_TOLERANCE_MM = 0.15
_MU_CACHE: dict[float, float] | None = None


def cdte_mu_linear() -> dict[float, float]:
    """CdTe linear attenuation per energy, from the campaign's own NIST table."""
    global _MU_CACHE
    if _MU_CACHE is None:
        if _CDTE_CSV.exists():
            df = pd.read_csv(_CDTE_CSV)
            _MU_CACHE = dict(zip(df.energy_keV.astype(float),
                                 df.mu_linear_cm_inv.astype(float)))
        else:
            _MU_CACHE = {}
    return _MU_CACHE


def _root_origin(run: RunData, key: str, op: str) -> str:
    return f"root:DetectorHistogrammer/{run.detector_dir}/{key}#{op}"


def _conf_origin(prov: RunProvenance, section: str, key: str) -> str:
    name = prov.sim_config.path.name if prov.sim_config.exists else "(absent)"
    return f"conf:{name}#{section}.{key}"


def _hist_sum(run: RunData, key: str) -> float:
    h = run.hists.get(key)
    return float(np.nansum(h.values)) if h is not None else math.nan


def derive_run(run: RunData, prov: RunProvenance,
               det: DetectorSpec | None) -> list[Quantity]:
    """Every derived number shown on one run page, in page order."""
    qs: list[Quantity] = []
    if run.is_empty:
        return qs

    # ---- counts ---------------------------------------------------------
    n_events_raw = prov.fields.get("n_events")
    try:
        n_events = float(str(n_events_raw))
    except (TypeError, ValueError):
        n_events = float(_mpe.DEFAULT_BARE_EVENTS)
    n_events_origin = (_conf_origin(prov, "Allpix", "number_of_events")
                       if prov.source_of("n_events") == "conf"
                       else f"{prov.source_of('n_events')}:n_events")

    detected = _hist_sum(run, "event_size_clusters")
    deposits = run.hists["charge/total_charge"].entries if "charge/total_charge" in run.hists else math.nan

    qs.append(Quantity(
        key="n_events", label="Events fired", value=n_events, unit="events",
        formula_py="", note="The number of photons Allpix simulated for this run.",
        inputs=(QRef("n_events", n_events, "events", n_events_origin),),
        tags=("counts",)))

    qs.append(Quantity(
        key="detected_events", label="Events detected", value=detected, unit="events",
        formula_tex=r"N_{\mathrm{det}} = \sum_i \mathrm{event\_size\_clusters}_i",
        formula_py="cluster_events",
        inputs=(QRef("cluster_events", detected, "events",
                     _root_origin(run, "event_size_clusters", "sum"),
                     label="event_size_clusters integral",
                     hist_key="event_size_clusters"),),
        note="Events that produced at least one reconstructed cluster. This is "
             "the same quantity material_penetration_experiment."
             "read_detected_event_count() reads.",
        tags=("counts",)))

    if not math.isnan(deposits):
        qs.append(Quantity(
            key="events_with_deposit", label="Events with any deposit",
            value=float(deposits), unit="events",
            formula_py="total_charge_entries",
            inputs=(QRef("total_charge_entries", float(deposits), "events",
                         _root_origin(run, "charge/total_charge", "entries"),
                         hist_key="charge/total_charge"),),
            note="Events depositing charge in the sensor. A LOWER BOUND on the "
                 "interaction count, not equal to it: it counts events with any "
                 "propagated charge, which is why it can sit below n_events even "
                 "when the sensor is opaque.",
            tags=("counts",)))

    # ---- efficiency -----------------------------------------------------
    eff = detected / n_events if n_events else math.nan
    eff_se = float(_mpe.binomial_se(eff, int(n_events))) if n_events else math.nan
    qs.append(Quantity(
        key="detection_efficiency", label="Detection efficiency", value=eff,
        formula_tex=r"\varepsilon = N_{\mathrm{det}} / N_{\mathrm{ev}}",
        formula_py="detected_events / n_events",
        inputs=(QRef("detected_events", detected, "events",
                     _root_origin(run, "event_size_clusters", "sum"),
                     hist_key="event_size_clusters"),
                QRef("n_events", n_events, "events", n_events_origin)),
        note=f"Binomial standard error {eff_se:.5g} over n={int(n_events):,} "
             "Monte-Carlo trials (material_penetration_experiment.binomial_se).",
        tags=("efficiency",)))

    # ---- deposited-energy window ---------------------------------------
    cc = run.hists.get("charge/cluster_charge")
    if cc is not None and det is not None:
        counts = cc.values
        charge_keV = cc.axes[0].centers * EPSILON_CDTE_EV
        total = float(np.nansum(counts))
        in_win = (charge_keV >= det.lower_keV) & (charge_keV <= det.upper_keV)
        win_counts = float(np.nansum(counts[in_win]))
        wa = win_counts / total if total > 0 else 0.0

        qs.append(Quantity(
            key="window_fraction", label="Window acceptance", value=wa,
            formula_tex=r"w_a = \frac{\sum_{E_{\mathrm{dep}} \in [E_{\min},E_{\max}]} n_i}"
                        r"{\sum_i n_i}",
            formula_py="clusters_in_window / clusters_total",
            inputs=(QRef("clusters_in_window", win_counts, "clusters",
                         _root_origin(run, "charge/cluster_charge",
                                      f"sum[{det.lower_keV:g},{det.upper_keV:g}]keV"),
                         hist_key="charge/cluster_charge"),
                    QRef("clusters_total", total, "clusters",
                         _root_origin(run, "charge/cluster_charge", "sum"),
                         hist_key="charge/cluster_charge"),
                    QRef("E_min", det.lower_keV, "keV", det.origin),
                    QRef("E_max", det.upper_keV, "keV", det.origin),
                    QRef("epsilon_CdTe", EPSILON_CDTE_EV, "eV/e-h",
                         "const:material_penetration_experiment.EPSILON_CDTE_EV")),
            note="The window is applied to DEPOSITED energy (cluster charge x "
                 f"{EPSILON_CDTE_EV} eV), not to incident photon energy, because "
                 "that is what a real chip thresholds. This is exactly why the "
                 "analytic theory (which cuts on photon energy) and the "
                 "simulation diverge for tight-window chips such as EIGER2.",
            tags=("window",)))

        intrinsic = min(eff, 1.0)
        r = min(intrinsic * wa, intrinsic)
        r_se = float(_mpe.binomial_se(r, int(n_events))) if n_events else math.nan
        qs.append(Quantity(
            key="windowed_response", label="Windowed response  R(E)", value=r,
            formula_tex=r"R_d(E) = \min\!\big(\min(\varepsilon,1)\cdot w_a,\ "
                        r"\min(\varepsilon,1)\big)",
            formula_py="min(min(efficiency, 1.0) * window_fraction, min(efficiency, 1.0))",
            inputs=(QRef("efficiency", eff, "", "derived:this_page#detection_efficiency"),
                    QRef("window_fraction", wa, "", "derived:this_page#window_fraction")),
            note=f"Standard error {r_se:.5g}. Both clamps are reproduced verbatim "
                 "from the production pipeline so this page and the campaign CSVs "
                 "cannot diverge. This is the number the hybrid calculation "
                 "multiplies by the analytic alloy transmission.",
            tags=("window", "headline")))

    # ---- charge ---------------------------------------------------------
    if cc is not None:
        mean_ke = cc.stats.get("mean_x", math.nan)
        qs.append(Quantity(
            key="mean_cluster_energy_keV", label="Mean cluster energy",
            value=mean_ke * EPSILON_CDTE_EV, unit="keV",
            formula_tex=r"\bar{E}_{\mathrm{dep}} = \bar{q}\cdot\varepsilon_{\mathrm{CdTe}}",
            formula_py="mean_cluster_charge_ke * epsilon_CdTe",
            inputs=(QRef("mean_cluster_charge_ke", mean_ke, "ke-",
                         _root_origin(run, "charge/cluster_charge", "mean"),
                         hist_key="charge/cluster_charge"),
                    QRef("epsilon_CdTe", EPSILON_CDTE_EV, "eV/e-h",
                         "const:material_penetration_experiment.EPSILON_CDTE_EV")),
            note="Compare against the beam energy: a large shortfall means most "
                 "clusters are partial-energy deposits (escape or charge sharing).",
            tags=("charge",)))

    sc = run.hists.get("charge/seed_charge")
    if cc is not None and sc is not None:
        m_seed = sc.stats.get("mean_x", math.nan)
        m_clu = cc.stats.get("mean_x", math.nan)
        frac = m_seed / m_clu if m_clu else math.nan
        qs.append(Quantity(
            key="seed_charge_fraction", label="Seed-pixel charge fraction", value=frac,
            formula_tex=r"f_{\mathrm{seed}} = \bar{q}_{\mathrm{seed}}/\bar{q}_{\mathrm{cluster}}",
            formula_py="mean_seed_charge / mean_cluster_charge",
            inputs=(QRef("mean_seed_charge", m_seed, "ke-",
                         _root_origin(run, "charge/seed_charge", "mean"),
                         hist_key="charge/seed_charge"),
                    QRef("mean_cluster_charge", m_clu, "ke-",
                         _root_origin(run, "charge/cluster_charge", "mean"),
                         hist_key="charge/cluster_charge")),
            note="1.0 means no charge sharing; lower means the cluster's charge "
                 "is spread over neighbouring pixels.",
            tags=("charge",)))

    # ---- cluster size / spatial ----------------------------------------
    for key, label, fallback_unit, tag in (
        ("cluster_size/cluster_size", "Mean cluster size", "pixels", "cluster_size"),
        ("residuals/residual_r", "Mean radial residual", "", "residuals"),
        ("residuals/residual_x", "Mean residual x", "", "residuals"),
        ("residuals/residual_y", "Mean residual y", "", "residuals"),
        ("event_size_pixels", "Mean pixels per event", "pixels", "counts"),
    ):
        h = run.hists.get(key)
        if h is None:
            continue
        # Unit comes from the ROOT axis title, never from a literal here: the
        # residuals are in micrometres while the local hit maps are in
        # millimetres, and assuming either is wrong by 1000x.
        unit = h.axes[0].unit or fallback_unit
        qs.append(Quantity(
            key=key.split("/")[-1] + "_mean", label=label,
            value=h.stats.get("mean_x", math.nan), unit=unit,
            formula_tex=r"\bar{x} = \sum_i n_i x_i / \sum_i n_i",
            formula_py="weighted_mean",
            inputs=(QRef("weighted_mean", h.stats.get("mean_x", math.nan), unit,
                         _root_origin(run, key, "mean"), hist_key=key),),
            tags=(tag,)))

    # ---- efficiency map --------------------------------------------------
    em = run.hists.get("efficiency/efficiency_detector")
    if em is not None and em.counts is not None:
        w = np.nan_to_num(em.counts)
        v = np.nan_to_num(em.values)
        tot = float(w.sum())
        mean_eff = float((v * w).sum() / tot) if tot else math.nan
        qs.append(Quantity(
            key="mean_pixel_efficiency", label="Mean pixel efficiency",
            value=mean_eff,
            formula_tex=r"\bar{\eta} = \sum_i c_i\eta_i / \sum_i c_i",
            formula_py="count_weighted_mean",
            inputs=(QRef("count_weighted_mean", mean_eff, "",
                         _root_origin(run, "efficiency/efficiency_detector",
                                      "count-weighted mean"),
                         hist_key="efficiency/efficiency_detector"),),
            note="Weighted by entries per bin, so empty bins cannot drag it down.",
            tags=("efficiency",)))

    # ---- occupancy -------------------------------------------------------
    hm = run.hists.get("hit_map")
    if hm is not None:
        nz = int(hm.stats.get("n_nonzero", 0))
        qs.append(Quantity(
            key="pixels_hit", label="Pixels hit at least once", value=float(nz),
            unit="pixels",
            formula_py="nonzero_bins",
            inputs=(QRef("nonzero_bins", float(nz), "pixels",
                         _root_origin(run, "hit_map", "count(nonzero)"),
                         hist_key="hit_map"),),
            note=f"Out of {int(hm.values.size):,} pixels in the simulated matrix. "
                 "A 1 mm pencil beam only illuminates the centre, so low "
                 "occupancy is expected and matrix size does not affect counts.",
            tags=("occupancy",)))

    qs.extend(_implied_thickness(run, prov, eff))
    return qs


def _implied_thickness(run: RunData, prov: RunProvenance,
                       eff: float) -> list[Quantity]:
    """Recover sensor thickness from efficiency: t = -ln(1 - eff) / mu.

    This is the check that catches runs whose geometry record was lost or is
    wrong. A real sensor gives the SAME answer at every energy; a run whose
    thickness is not what its name claims does not.

    Above SATURATION_EFF the estimator is reported but marked invalid: CdTe is
    effectively opaque at low energy, so every thickness yields eff ~ 1 and the
    inversion has no resolving power.
    """
    key = run.key
    if key is None or key.energy_keV is None or math.isnan(eff):
        return []
    mu = cdte_mu_linear().get(float(key.energy_keV))
    if mu is None or eff >= 1.0:
        return []

    valid = eff < SATURATION_EFF
    t_mm = -math.log(1.0 - eff) / mu * 10.0
    note = ("t = -ln(1 - efficiency) / mu_CdTe, inverting the interaction "
            "probability 1 - exp(-mu*t). A physically consistent run returns the "
            "SAME thickness at every beam energy.")
    if not valid:
        note += (f" NOT VALID HERE: efficiency {eff:.4f} is at or above "
                 f"{SATURATION_EFF}, so detection is limited by the threshold "
                 "and K-escape rather than by absorption, and the inversion "
                 "returns a meaningless thickness. Read the cross-energy "
                 "profile instead.")

    return [Quantity(
        key="implied_thickness_mm", label="Efficiency-implied CdTe thickness",
        value=t_mm, unit="mm", valid=valid,
        formula_tex=r"t = -\ln(1-\varepsilon)\,/\,\mu_{\mathrm{CdTe}}(E)",
        formula_py="-log(1.0 - efficiency) / mu_cdte * 10.0",
        inputs=(QRef("efficiency", eff, "", "derived:this_page#detection_efficiency"),
                QRef("mu_cdte", mu, "1/cm",
                     f"csv:analysis/results/material_penetration_uniform/"
                     f"cdte_interaction.csv#E={key.energy_keV:g},mu_linear_cm_inv")),
        note=note, tags=("integrity",))]


def implied_thickness_profile(detector: str, campaign: str,
                              variant: dict[str, str] | None = None,
                              data_dir: Path | None = None) -> pd.DataFrame:
    """Implied thickness across every energy for one detector.

    Cross-energy consistency is the discriminating check: this is what separates
    a mislabelled run from a merely undocumented one.
    """
    from analysis.viz.runreader import read_run_or_none

    mus = cdte_mu_linear()
    rows = []
    d = reg.discover(data_dir, campaign)
    for key in d.runs:
        if key.detector != detector or key.energy_keV is None:
            continue
        if variant is not None and {k: v for k, v in key.variant} != variant:
            continue
        run = read_run_or_none(reg.root_path(key, data_dir))
        if run is None or run.is_empty:
            continue
        n_ev = float(str(run.hists["event_size_pixels"].entries))
        detected = float(np.nansum(run.hists["event_size_clusters"].values))
        eff = detected / n_ev if n_ev else math.nan
        mu = mus.get(float(key.energy_keV))
        t = (-math.log(1 - eff) / mu * 10.0
             if mu and 0 < eff < 1 else math.nan)
        rows.append({"run_id": key.run_id, "energy_keV": key.energy_keV,
                     "efficiency": eff, "mu_cdte": mu,
                     "implied_thickness_mm": t,
                     "usable": bool(eff < SATURATION_EFF)})
    return pd.DataFrame(rows).sort_values("energy_keV").reset_index(drop=True)


def _absorption_limited(df: pd.DataFrame) -> pd.Series:
    """Mask of energies where efficiency is limited by ABSORPTION.

    Two conditions, both physical:

    1. Above the efficiency peak. Below it, detection is limited by the
       threshold and K-escape (a chip with a high threshold such as Medipix4 at
       1773 e- loses low-energy events outright), so the inversion of
       eff = 1 - exp(-mu*t) does not apply. Above the peak, attenuation falls
       with energy and absorption is what is being measured.
    2. Efficiency below SATURATION_EFF, so at least 10% of photons transmit and
       (1 - eff) is a real measurement rather than a few Monte-Carlo counts.

    Without condition 1, a single threshold-limited low-energy point makes a
    perfectly good run look inconsistent -- Medipix4's 30 keV bin does exactly
    that.
    """
    if df.empty:
        return pd.Series(dtype=bool)
    peak_energy = float(df.loc[df.efficiency.idxmax(), "energy_keV"])
    return (df.energy_keV > peak_energy) & (df.efficiency < SATURATION_EFF)


def thickness_verdict(detector: str, campaign: str,
                      variant: dict[str, str] | None = None,
                      data_dir: Path | None = None) -> dict:
    """Is this detector's geometry self-consistent across energy?

    A sensor has one thickness. If the runs claiming one configuration return
    different thicknesses at different beam energies, the runs are not what
    their names say -- no analysis downstream of them is supported.
    """
    df = implied_thickness_profile(detector, campaign, variant, data_dir)
    if df.empty:
        return {"detector": detector, "status": "no_runs", "n_usable": 0}

    usable = df[_absorption_limited(df)]
    claimed = None
    tag = (variant or {}).get("thickness_tag")
    if tag:
        digits = tag.strip("_").replace("mm", "")
        claimed = float("0." + digits[1:]) if digits.startswith("0") else float(digits)

    if usable.empty:
        return {"detector": detector, "status": "no_usable_energies",
                "n_usable": 0, "n_runs": len(df), "claimed_mm": claimed}

    t = usable.implied_thickness_mm
    spread = float(t.max() - t.min())
    median = float(t.median())
    consistent = spread <= THICKNESS_SPREAD_TOLERANCE_MM
    matches = claimed is None or abs(median - claimed) <= 0.1

    if not consistent:
        # No plateau. This means the thickness cannot be recovered from these
        # runs -- typically because the chip is threshold-limited across the
        # whole range (Study A's Medipix3 at 1129 e- and Timepix3 at 650 e- both
        # behave this way). It is NOT by itself evidence that the geometry is
        # wrong; see integrity.paired_config_check for a claim that does not
        # depend on this model.
        status = "UNRESOLVED"
    elif not matches:
        status = "MISLABELLED"
    else:
        status = "ok"

    return {
        "detector": detector, "campaign": campaign,
        "variant": dict(variant or {}),
        "status": status,
        "n_runs": len(df), "n_usable": len(usable),
        "median_mm": median, "spread_mm": spread,
        "claimed_mm": claimed,
        "min_mm": float(t.min()), "max_mm": float(t.max()),
        "saturated_energies": sorted(
            df[df.efficiency >= SATURATION_EFF].energy_keV.tolist()),
        "detail": df.to_dict("records"),
    }
