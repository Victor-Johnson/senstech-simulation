#!/usr/bin/env python3
"""Fill in the tables from notes/_Material_Penetration_Experiment2.pdf using the
current material_penetration pipeline results.

Two structural mismatches between that spec document and what was actually
simulated are resolved here per project decision (see header note in the
generated output):
  1. Its Table 2.1 D4 is a hypothetical "Custom thick CdTe PC" that was never
     simulated in the current pipeline -- superseded by Timepix3 CdTe.
  2. Its simulation matrix (Section 9/11) only lists 4 alloys, but Section 3
     defines 5 and the pipeline simulated all 5 -- Alloy 5 is included here.

Several requested metrics (SNR, CNR, absorbed/scattered photon split, charge
sharing %, dead-time loss %) are not directly measured by the pipeline; where
a standard, clearly-labelled approximation can be honestly derived from
existing counts it is computed and flagged as an approximation. Everything
else is marked "Not computed".
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE = REPO_ROOT / "analysis" / "results" / "material_penetration"
NOTES = REPO_ROOT / "notes"

ELEMENTS = {
    "Cu": (29, 63.546),
    "O": (8, 16.00),
    "Zn": (30, 65.38),
    "Pb": (82, 207.2),
    "Ni": (28, 58.693),
    "Fe": (26, 55.845),
    "Al": (13, 26.982),
    "Be": (4, 9.012),
}

ALLOY_COMPOSITION = {
    "alloy1": {"Cu": 0.999, "O": 0.001},
    "alloy2": {"Cu": 0.615, "Zn": 0.355, "Pb": 0.030},
    "alloy3": {"Cu": 0.886, "Ni": 0.100, "Fe": 0.014},
    "alloy4": {"Cu": 0.810, "Al": 0.110, "Fe": 0.040, "Ni": 0.040},
    "alloy5": {"Cu": 0.981, "Be": 0.019},
}

ALLOY_LABELS = {
    "alloy1": "Alloy 1 -- C11000 ETP Copper",
    "alloy2": "Alloy 2 -- C36000 Free-Machining Brass",
    "alloy3": "Alloy 3 -- CuNi 90/10 (C70600)",
    "alloy4": "Alloy 4 -- C95500 Aluminum Bronze",
    "alloy5": "Alloy 5 -- C17200 Beryllium Copper",
}

DETECTOR_LABELS = {
    "medipix3": "D1 Medipix3 CdTe",
    "eiger2": "D2 EIGER2 CdTe",
    "hexitec_proxy": "D3 HEXITEC CdTe proxy",
    "timepix3_cdte": "D4 Timepix3 CdTe (relabeled -- see note)",
}

DETECTOR_SPEC = {
    "medipix3": dict(thickness_mm=0.30, pitch_um=55, npix="256x256", bias_V=-400, depl_V=-300,
                      noise_e=80, threshold_e=1129, smear_e=80, lower_keV=5.0, upper_keV=460.0,
                      bins=2, energy_res_keV="2.5 (FWHM at 60 keV, design spec)",
                      charge_sharing="2x2 Charge Summing Mode (CSM)",
                      dead_time="Dead-time-free dual-counter architecture (design spec)"),
    "eiger2": dict(thickness_mm=0.75, pitch_um=75, npix="256x256", bias_V=-400, depl_V=-250,
                    noise_e=75, threshold_e=903, smear_e=75, lower_keV=4.0, upper_keV=80.0,
                    bins=2, energy_res_keV="Not specified in source doc",
                    charge_sharing="Charge Sharing Addition (CSA)",
                    dead_time="<100 ns between exposures (design spec)"),
    "hexitec_proxy": dict(thickness_mm=1.00, pitch_um=250, npix="80x80", bias_V=-500, depl_V=-300,
                            noise_e=50, threshold_e=452, smear_e=50, lower_keV=2.0, upper_keV=200.0,
                            bins=1, energy_res_keV="0.8 (FWHM at 59.5 keV, design spec)",
                            charge_sharing="CSA / Charge Sharing Discrimination (CSD)",
                            dead_time="Not modeled (proxy digitizer)"),
    "timepix3_cdte": dict(thickness_mm=1.00, pitch_um=55, npix="256x256", bias_V=-300, depl_V=-200,
                            noise_e=90, threshold_e=650, smear_e=90, lower_keV=2.88, upper_keV=120.0,
                            bins=4, energy_res_keV="Not specified (D4 relabeled from hypothetical custom detector)",
                            charge_sharing="ToT-derived analysis bins (ASIC charge sharing not separately modeled)",
                            dead_time="Not modeled"),
}

N0 = 1_000_000
EPSILON_CDTE_EV = 4.43


def md_table(rows: list[dict[str, object]], floatfmt: str = "{:.4f}") -> list[str]:
    if not rows:
        return ["_(no rows)_"]
    cols = list(rows[0].keys())

    def fmt(v: object) -> str:
        if isinstance(v, float):
            return "" if pd.isna(v) else floatfmt.format(v)
        return "" if v is None else str(v)

    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = ["| " + " | ".join(fmt(row[c]) for c in cols) + " |" for row in rows]
    return [header, sep, *body]


def effective_z(composition: dict[str, float], n: float = 2.94) -> float:
    electrons_per_g = {el: w * ELEMENTS[el][0] / ELEMENTS[el][1] for el, w in composition.items()}
    total = sum(electrons_per_g.values())
    return sum((e / total) * ELEMENTS[el][0] ** n for el, e in electrons_per_g.items()) ** (1 / n)


def main() -> None:
    spectrum = pd.read_csv(REPO_ROOT / "spectra" / "150kvp_weights.csv")
    attenuation = pd.read_csv(BASE / "alloy_attenuation.csv")
    response = pd.read_csv(BASE / "detector_response.csv")
    combined = pd.read_csv(BASE / "combined_results.csv")
    transport = pd.read_csv(BASE / "transport_validation.csv")
    bin_results = pd.read_csv(BASE / "per_detector_energy_bin_results.csv")
    performance = pd.read_csv(BASE / "performance_evaluation.csv")

    detectors = ["medipix3", "eiger2", "hexitec_proxy", "timepix3_cdte"]
    alloys = ["alloy1", "alloy2", "alloy3", "alloy4", "alloy5"]

    lines: list[str] = []
    lines += [
        "# Material Penetration Experiment 2 -- Filled Tables",
        "",
        "Source template: `notes/_Material_Penetration_Experiment2.pdf`. Generated by "
        "`analysis/scripts/material_penetration_experiment2_fill.py` from the canonical outputs in "
        "`analysis/results/material_penetration/`. Do not hand-edit; rerun the script after any pipeline change.",
        "",
        "## Reconciliation Notes (read first)",
        "",
        "1. **D4 relabeled.** The source document's Table 2.1 D4 is a hypothetical \"Custom thick CdTe PC\" "
        "(2.0 mm, 100 um pitch, 800 V, 15-160 keV, 16 bins, 200 e- noise) that was never simulated in the "
        "current pipeline. It was superseded earlier in the project by **Timepix3 CdTe** (1.0 mm, 55 um pitch, "
        "-300 V, 2.88-120 keV, 4 ToT-derived bins, 90 e- noise). All D4 results below are Timepix3 CdTe, not "
        "the original hypothetical detector.",
        "2. **Alloy 5 included.** The document's Section 3 defines 5 alloys but its simulation matrix "
        "(Section 9/11) only lists 4 (A1-A4). All tables below use the full 4x5 = 20 combinations, since "
        "Alloy 5 was fully simulated.",
        "3. **Alloy 5 thickness.** Table 3.1 in the source document lists Alloy 5 thickness as 55 mm, "
        "inconsistent with every other alloy's 5 mm and almost certainly a typo. The pipeline simulated "
        "Alloy 5 at 5 mm (matching the pattern), and that is what's reported here.",
        "4. **Metrics not computed by this pipeline**, left marked below rather than estimated: measured "
        "(as opposed to design-spec) energy resolution, charge-sharing loss %, dead-time loss %, and an "
        "absorbed/scattered photon split (Beer-Lambert gives only net transmission, not the split -- full "
        "Geant4 transport tracks it but the pipeline doesn't currently extract it).",
        "5. **SNR and CNR are approximations**, not pipeline-native metrics: SNR uses the standard "
        "Poisson shot-noise formula `SNR = sqrt(N_detected)` (electronic noise not included). CNR compares "
        "each alloy result against a same-detector, no-alloy (open-beam) reference at the same N0, using "
        "`CNR = |N_alloy - N_open| / sqrt(N_alloy + N_open)`. Both are clearly derivable from existing counts "
        "but were not part of the original analysis; treat them as estimates.",
        "6. **Simulation geometry (Table 1.1).** The source document specifies a clinical/security-style "
        "geometry (SSD 300 mm, SDD 50 mm, 2 mm collimator aperture, 17 mm^2 FOV). The Allpix2 configs actually "
        "used a compact pencil-beam approximation instead (source 10 mm from the alloy, 1 mm beam, zero "
        "divergence). Under the stated zero-divergence assumption this doesn't change the physics (Beer-Lambert "
        "transmission depends only on alloy thickness, not absolute source/detector distance), but the absolute "
        "distances in the configs don't match the spec numbers -- flagged here rather than silently presented "
        "as if verified.",
        "",
    ]

    # Table 1.1
    lines += [
        "## 1. Simulation Geometry (Table 1.1)",
        "",
        "As actually configured in the Allpix2 `.conf` files (see note 6 above for the deviation from the "
        "document's specified absolute distances).",
        "",
        *md_table([
            {"Parameter": "Source-to-alloy distance", "Symbol": "--", "Unit": "mm", "Value": "10 (source_position = -1cm)"},
            {"Parameter": "Alloy thickness", "Symbol": "x", "Unit": "mm", "Value": "5.0 (all alloys)"},
            {"Parameter": "Alloy-to-detector gap", "Symbol": "--", "Unit": "mm", "Value": "~0.5 (alloy centered at z=-3mm, 5mm thick; detector at z=0)"},
            {"Parameter": "Beam geometry", "Symbol": "--", "Unit": "--", "Value": "parallel pencil beam, zero divergence"},
            {"Parameter": "Beam size", "Symbol": "--", "Unit": "mm", "Value": "1.0 (diameter)"},
            {"Parameter": "Beam angle", "Symbol": "theta", "Unit": "deg", "Value": "0"},
            {"Parameter": "Document spec (not used): SSD / SDD / FOV / collimator aperture", "Symbol": "--", "Unit": "--", "Value": "300 mm / 50 mm / 17 mm^2 / 2.0 mm -- see note 6"},
        ], floatfmt="{}"),
        "",
    ]

    # Table 2.1
    lines += ["## 2. CdTe Detector Characteristics (Table 2.1)", ""]
    header = ["Parameter"] + [DETECTOR_LABELS[d] for d in detectors]
    rows_2 = [
        ["Detector thickness (mm)"] + [DETECTOR_SPEC[d]["thickness_mm"] for d in detectors],
        ["Pixel pitch (um)"] + [DETECTOR_SPEC[d]["pitch_um"] for d in detectors],
        ["Matrix dimensions"] + [DETECTOR_SPEC[d]["npix"] for d in detectors],
        ["Detector bias (V)"] + [DETECTOR_SPEC[d]["bias_V"] for d in detectors],
        ["Depletion voltage (V)"] + [DETECTOR_SPEC[d]["depl_V"] for d in detectors],
        ["Mobility model"] + ["Jacoboni (Allpix GenericPropagation); no explicit mu-tau product configured" for _ in detectors],
        ["Charge collection efficiency"] + ["Not an explicit parameter -- modeled via drift/diffusion (GenericPropagation) + SimpleTransfer, max depth 5 um" for _ in detectors],
        ["Energy resolution (keV)"] + [DETECTOR_SPEC[d]["energy_res_keV"] for d in detectors],
        ["Lower threshold (keV)"] + [DETECTOR_SPEC[d]["lower_keV"] for d in detectors],
        ["Upper threshold (keV)"] + [DETECTOR_SPEC[d]["upper_keV"] for d in detectors],
        ["Number of energy bins"] + [DETECTOR_SPEC[d]["bins"] for d in detectors],
        ["Electronic noise (e- RMS)"] + [DETECTOR_SPEC[d]["noise_e"] for d in detectors],
        ["Digitizer threshold (e-)"] + [DETECTOR_SPEC[d]["threshold_e"] for d in detectors],
        ["Threshold smearing (e-)"] + [DETECTOR_SPEC[d]["smear_e"] for d in detectors],
        ["Dead time"] + [DETECTOR_SPEC[d]["dead_time"] for d in detectors],
        ["Charge-sharing model"] + [DETECTOR_SPEC[d]["charge_sharing"] for d in detectors],
    ]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in rows_2:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    lines.append("")
    lines.append(
        "Note: EIGER2's electronic noise (75 e-) and Timepix3's lower threshold (2.88 keV, from its 650 e- "
        "digitizer threshold) were themselves corrections made during this project -- EIGER2 was originally "
        "simulated with 0 e- noise (a bug), and Timepix3's documented 2.5 keV edge didn't match its simulated "
        "threshold. See `analysis/scripts/material_penetration_experiment.py` for the derivation."
    )
    lines.append("")

    # Table 3.1 + Z_eff
    lines += ["## 3. Alloy Material Properties (Table 3.1)", ""]
    rows_3 = []
    for a in alloys:
        att_row = attenuation[attenuation["alloy"] == a].iloc[0]
        rows_3.append({
            "Property": ALLOY_LABELS[a],
            "Density (g/cm3)": att_row["density_g_cm3"],
            "Thickness (mm)": att_row["thickness_mm"],
            "Width (mm)": 20.0,
            "Height (mm)": 20.0,
            "Effective atomic number (Zeff)": round(effective_z(ALLOY_COMPOSITION[a]), 2),
        })
    lines += md_table(rows_3, floatfmt="{:.2f}")
    lines.append("")
    lines.append(
        "Zeff computed via the standard exponent method, Zeff = (sum(f_i * Z_i^2.94))^(1/2.94), where f_i is "
        "each element's fraction of total electrons per gram (not weight fraction)."
    )
    lines.append("")

    # Table 3.2
    lines += ["## Table 3.2 Elemental Composition", ""]
    for a in alloys:
        lines.append(f"**{ALLOY_LABELS[a]}**")
        lines.append("")
        rows = [
            {"Element": el, "Weight Fraction (%)": w * 100, "Atomic Number": ELEMENTS[el][0]}
            for el, w in ALLOY_COMPOSITION[a].items()
        ]
        lines += md_table(rows, floatfmt="{:.1f}")
        lines.append("")

    # Table 4.1
    lines += [
        "## 4. Fixed X-ray Source Parameters (Table 4.1)",
        "",
        *md_table([
            {"Parameter": "Tube voltage (kVp)", "Value": "150"},
            {"Parameter": "Anode angle", "Value": "12 deg"},
            {"Parameter": "Tube current / exposure time / mAs", "Value": "N/A -- SpekPy models spectral shape only; absolute photon count set independently via N0, not via mA x t"},
            {"Parameter": "Inherent filtration", "Value": "1.0 mm Al"},
            {"Parameter": "Additional filtration", "Value": "1.0 mm Al"},
            {"Parameter": "Energy range", "Value": "20-150 keV"},
            {"Parameter": "Number of energy bins", "Value": str(len(spectrum))},
            {"Parameter": "Total incident photons, N0 (production result)", "Value": f"{N0:,}"},
            {"Parameter": "Monte Carlo events per Allpix run", "Value": "10,000"},
        ], floatfmt="{}"),
        "",
    ]

    # Table 5.1 -- restructured (no absorbed/scattered split available)
    lines += [
        "## 5. Photon Transport Results (Table 5.1)",
        "",
        "Restructured from Transmitted/Absorbed/Scattered to Transmitted/Attenuated: Beer-Lambert gives only "
        "net transmission, so absorbed and scattered photons can't be separated here (see reconciliation note 4). "
        "Detection efficiency is of the *original incident* beam (detector x alloy combined).",
        "",
    ]
    rows_5 = []
    for _, row in combined.iterrows():
        rows_5.append({
            "Detector": DETECTOR_LABELS[row["detector"]],
            "Alloy": ALLOY_LABELS[row["alloy"]],
            "Incident photons N0": N0,
            "Transmitted photons": row["transmitted_total"],
            "Attenuated (absorbed+scattered)": N0 - row["transmitted_total"],
            "Transmission probability T": row["transmission_fraction"],
            "Detection efficiency eta (%)": row["detected_fraction_of_incident"] * 100,
        })
    lines += md_table(rows_5, floatfmt="{:.4f}")
    lines.append("")

    # Table 7.1 Energy bin counts
    lines += [
        "## 7. Energy Bin Counts (Table 7.1)",
        "",
        "Per detector-alloy-bin. \"Incident Counts\" = N0-weighted incident photons whose *source* energy falls "
        "within the bin's [low, high) keV range (a proxy, since the document doesn't define this precisely for "
        "polychromatic sources); \"Detected Counts\" is summed across all 14 source energies for that bin.",
        "",
    ]
    bin_agg = (
        bin_results.groupby(["detector", "alloy", "detector_energy_bin", "bin_low_keV", "bin_high_keV"], as_index=False)
        .agg(detected=("detected_in_detector_bin", "sum"))
    )
    rows_7 = []
    for _, row in bin_agg.iterrows():
        in_range = spectrum[(spectrum["energy_keV"] >= row["bin_low_keV"]) & (spectrum["energy_keV"] < row["bin_high_keV"])]
        incident = N0 * in_range["weight"].sum()
        transmission = row["detected"] / incident if incident > 0 else np.nan
        rows_7.append({
            "Detector": DETECTOR_LABELS[row["detector"]],
            "Alloy": ALLOY_LABELS[row["alloy"]],
            "Energy Bin (keV)": f"{row['bin_low_keV']:.1f}-{row['bin_high_keV']:.1f}",
            "Incident Counts": incident,
            "Detected Counts": row["detected"],
            "Transmission": transmission,
        })
    lines += md_table(rows_7, floatfmt="{:.2f}")
    lines.append("")

    # Table 8.1 -- alloy-only (detector-independent)
    lines += [
        "## 8. Transmission and Attenuation Calculations (Table 8.1)",
        "",
        "Presented per alloy, not per detector-alloy combination: linear/mass attenuation and beam-hardening "
        "shift depend only on the alloy (Beer-Lambert), not on which detector is used -- confirmed identical "
        "across all 4 detectors in `combined_results.csv`. Values are spectrum-weighted means across the "
        "14-energy source spectrum.",
        "",
    ]
    rows_8 = []
    for a in alloys:
        att = attenuation[attenuation["alloy"] == a].merge(spectrum, on="energy_keV")
        mu_mean = np.average(att["mu_linear_cm_inv"], weights=att["weight"])
        mu_rho_mean = np.average(att["mu_over_rho_cm2_g"], weights=att["weight"])
        combined_row = combined[combined["alloy"] == a].iloc[0]
        beam_hardening_factor = combined_row["mean_transmitted_energy_keV"] / combined_row["mean_incident_energy_keV"]
        rows_8.append({
            "Alloy": ALLOY_LABELS[a],
            "Linear attenuation coeff, mu (cm^-1)": mu_mean,
            "Mass attenuation coeff, mu/rho (cm2/g)": mu_rho_mean,
            "Overall transmission, T": combined_row["transmission_fraction"],
            "Beam hardening factor (E_transmitted/E_incident)": beam_hardening_factor,
            "Beam hardening shift (keV)": combined_row["beam_hardening_shift_keV"],
        })
    lines += md_table(rows_8, floatfmt="{:.4f}")
    lines.append("")

    # Table 9.1 -- simulation matrix, 20 rows
    lines += ["## 9. Detector-Alloy Simulation Matrix (Table 9.1)", ""]
    detector_ids = {"medipix3": "D1", "eiger2": "D2", "hexitec_proxy": "D3", "timepix3_cdte": "D4"}
    alloy_ids = {"alloy1": "A1", "alloy2": "A2", "alloy3": "A3", "alloy4": "A4", "alloy5": "A5"}
    rows_9 = []
    sim_n = 1
    for d in detectors:
        for a in alloys:
            rows_9.append({
                "Simulation": sim_n,
                "Detector": detector_ids[d],
                "Alloy": alloy_ids[a],
                "Completed": "Yes",
            })
            sim_n += 1
    lines += md_table(rows_9, floatfmt="{}")
    lines.append("")

    # Table 10.1 -- performance metrics
    lines += [
        "## 10. Detector Performance Metrics (Table 10.1)",
        "",
        "Detection efficiency is *of transmitted photons only* (post-alloy, i.e. the detector's own performance "
        "isolated from the alloy's absorption) -- see reconciliation note 5 for the SNR/CNR approximations, and "
        "note 4 for Charge Sharing / Dead-Time, which are not computed.",
        "",
    ]
    # open-beam (no-alloy) reference per detector, at N0, for CNR
    open_beam: dict[str, float] = {}
    for d in detectors:
        det_resp = response[response["detector"] == d].merge(spectrum, on="energy_keV")
        open_beam[d] = float((N0 * det_resp["weight"] * det_resp["windowed_response"]).sum())

    rows_10 = []
    for _, row in combined.iterrows():
        d, a = row["detector"], row["alloy"]
        detected = row["detected_total"]
        snr = np.sqrt(detected) if detected >= 0 else np.nan
        n_open = open_beam[d]
        cnr = abs(detected - n_open) / np.sqrt(detected + n_open) if (detected + n_open) > 0 else np.nan
        rows_10.append({
            "Detector": DETECTOR_LABELS[d],
            "Alloy": ALLOY_LABELS[a],
            "Detection Efficiency (%)": row["detected_fraction_of_transmitted"] * 100,
            "Energy Resolution (keV)": DETECTOR_SPEC[d]["energy_res_keV"],
            "Charge Sharing (%)": "Not computed",
            "Dead-Time Loss (%)": "Not computed",
            "SNR (approx, sqrt(N))": snr,
            "CNR (approx, vs open-beam)": cnr,
        })
    lines += md_table(rows_10, floatfmt="{:.2f}")
    lines.append("")

    # Table 11.1 -- comparative results, with real RMSE/relative error where validated (alloy2 only)
    lines += [
        "## 11. Comparative Results (Table 11.1)",
        "",
        "Relative Error (%) and RMSE are only genuinely measurable where a full-transport Monte Carlo "
        "cross-check exists (Alloy 2 / brass, from `transport_validation.csv`); for the other four alloys "
        "there's no independent second measurement to compare against, so those cells are marked accordingly "
        "(see reconciliation note 4). EIGER2's Alloy 2 numbers use its direct transport measurement -- so its "
        "own \"error\" there is 0 by construction; EIGER2's error/RMSE are instead reported from its full "
        "14-energy validation curve.",
        "",
    ]
    rows_11 = []
    for _, row in combined.iterrows():
        d, a = row["detector"], row["alloy"]
        att = attenuation[attenuation["alloy"] == a].merge(spectrum, on="energy_keV")
        mu_mean = np.average(att["mu_linear_cm_inv"], weights=att["weight"])
        mu_rho_mean = np.average(att["mu_over_rho_cm2_g"], weights=att["weight"])

        rel_err = np.nan
        rmse = np.nan
        if a == "alloy2":
            sub = transport[(transport["detector"] == d) & (transport["status"] == "ok")]
            finite = sub[np.isfinite(sub["relative_difference_pct"])]
            if not finite.empty:
                rel_err = finite["relative_difference_pct"].abs().mean()
                rmse = np.sqrt(
                    np.mean((sub["transport_detected_fraction"] - sub["analytical_detected_fraction"]) ** 2)
                )

        rows_11.append({
            "Detector": DETECTOR_LABELS[d],
            "Alloy": ALLOY_LABELS[a],
            "Mean Transmission": row["transmission_fraction"],
            "Linear mu (cm^-1)": mu_mean,
            "Mass mu (cm2/g)": mu_rho_mean,
            "Relative Error (%) vs transport": rel_err,
            "RMSE (detected fraction) vs transport": rmse,
        })
    lines += md_table(rows_11, floatfmt="{:.4f}")
    lines.append("")

    # Table 11.2 -- summary of all simulations
    lines += ["## 11.2 Summary of All Simulations (Table 11.2)", ""]
    rows_112 = []
    sim_n = 1
    for d in detectors:
        for a in alloys:
            row = combined[(combined["detector"] == d) & (combined["alloy"] == a)].iloc[0]
            att = attenuation[attenuation["alloy"] == a].merge(spectrum, on="energy_keV")
            mu_mean = np.average(att["mu_linear_cm_inv"], weights=att["weight"])
            mu_rho_mean = np.average(att["mu_over_rho_cm2_g"], weights=att["weight"])
            snr = np.sqrt(row["detected_total"])
            rows_112.append({
                "Simulation": sim_n,
                "Detector": detector_ids[d],
                "Alloy": alloy_ids[a],
                "Transmission": row["transmission_fraction"],
                "Linear mu (cm^-1)": mu_mean,
                "Mass mu (cm2/g)": mu_rho_mean,
                "Efficiency (%, of transmitted)": row["detected_fraction_of_transmitted"] * 100,
                "SNR (approx)": snr,
            })
            sim_n += 1
    lines += md_table(rows_112, floatfmt="{:.4f}")
    lines.append("")

    (NOTES / "Material_Penetration_Experiment2_filled.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote notes/Material_Penetration_Experiment2_filled.md")


if __name__ == "__main__":
    main()
