# "alloy2" provenance (2026-11-05)

## Two different materials share the name "alloy2"

| Path | Material actually used | Where it is defined |
|---|---|---|
| Hybrid / analytic results (combined_results, rankings, CNR, Theoretical Reference Framework) | **C36000 free-machining brass**, ~3% Pb, NIST per-element composition (exact) | `analysis/scripts/material_penetration_experiment.py` alloy table |
| Full-transport validation runs, files `mp_/mpu_transport_<chip>_alloy2_<E>keV` | **Geant4 `G4_BRASS`** (57.5% Cu, 33.4% Zn, **9.07% Pb**, ρ 8.52), 20 × 20 × 5 mm slab — **only for runs made before 2026-07-25** | `[alloy2_brass_block]` in the generated `detector_<chip>_transport.conf` |
| The same `mpu_transport_*_alloy2` configs, re-run on or after 2026-07-25 | **`G4_Cu`** (pure copper) | The shared detector file was regenerated on 2026-07-25 for the pure-Cu pilot. It now holds only `[alloy1_slab] material = "G4_Cu"`, but the alloy2 configs still point to it. |

## Every alloy2 run and the material it actually simulated

The ROOT files are histogram-only and record no material, so the material is established two ways:

- **Config and driver history.** The `material_penetration/` detector files are dated 2026-07-02 and still contain G4_BRASS. In the 2026-07-14 commit, `run_material_penetration_uniform.sh` hard-codes `[alloy2_brass_block]` with G4_BRASS.
- **Physics fingerprint** (`alloy2_material_fingerprint.csv`). The ratio of counts in alloy2 to counts in the current Cu `alloy1` run, for the same chip and energy, is compared with T(G4_BRASS)/T(Cu) for 5 mm (xraydb). Brass absorbs far more above the 88 keV Pb K-edge.

| Run set | Files | Run date | Material simulated | Evidence | Label OK? |
|---|---|---|---|---|---|
| `data/mp_transport_{eiger2 x14 E, medipix3/timepix3_cdte/hexitec_proxy x 40/80/120}_alloy2` | 23 | 2026-07-02 | G4_BRASS | detector files unchanged since 07-02 | yes, if read as "G4_BRASS" |
| `data/mpu_transport_{same set}_alloy2` | 23 | 2026-07-05 | G4_BRASS | fingerprint at 60-150 keV matches brass for all 4 chips (e.g. EIGER2 90 keV: 0.17 measured vs 0.08 brass / 1.0 Cu); 40 keV indeterminate (Cu alloy1 has 0 counts) | yes, if read as "G4_BRASS" |
| `data/audit_itime/mpu_transport_{eiger2,medipix3}_alloy2` (integration-time audit re-runs) | 17 | 2026-11-05 | **G4_Cu** | fingerprint ratio 1.00-1.07 at all testable energies | **NO**: named alloy2, simulated copper. Excluded from the audit; must not be copied into `data/` |

## Results and reports that used alloy2 transport runs

| Item | Date | Transport data used | Label in the document | Flag |
|---|---|---|---|---|
| `analysis/results/material_penetration/transport_validation.csv`, `_fixed/`, `_fixed_mpx120/`, `_uniform/`, `_uniform_mpx120/` | 07-05 … 07-25 | `data/` alloy2 runs (07-02 / 07-05) = G4_BRASS | `g4_brass` | OK. The 07-25 uniform tables were regenerated after the detector-file switch, but they read the unchanged 07-05 ROOT files. |
| `analysis/reports/material_penetration_report.md` + `.docx` (original report) | 07-03 | EIGER2 alloy2 "directly measured full-physics transport fraction" | "Alloy 2 (brass)" = C36000 in the rest of the report | **MISMATCH**: the transport measured 9.07% Pb G4_BRASS but is used as C36000 (3% Pb). Known since 07-05 (`material_penetration_uniform_summary.md` §2.1); the file was left stale on purpose and never corrected. |
| `analysis/results/material_penetration/table_values.md`, results index (original baseline) | 07-14 file date (content from 07-03) | EIGER2/alloy2 `direct_transport` (19,141 transmitted / 7,169 detected) | alloy2 = C36000 | **MISMATCH**, same cause as above (stale baseline) |
| `notes/Material_Penetration_Experiment2_filled.md` | 07-14 | Relative Error / RMSE "only measurable for Alloy 2 / brass, from `transport_validation.csv`" | "Alloy 2 / brass" | **POSSIBLE MISMATCH**: the transport side is G4_BRASS but the label reads as the C36000 alloy. Check which material the error figures were compared against. |
| `material_penetration_academic_report.md`, `_short_report.md`, `_presentation_defense.md`, `_uniform_summary.md`, `_uniform_short_report.md` | revised 07-05/07-06 | G4_BRASS transport | explicitly "G4_BRASS, 9.07% Pb" | OK. `_uniform_short_report.md` still mentions the G4_BRASS-calibrated EIGER2 correction, which was removed on 07-21 (stale text, not a material mislabel). |
| `analysis/results/theory_transport_validation/` (pure-Cu pilot) | 07-25 | `mpu_transport_*_alloy1` = G4_Cu | alloy1 / G4_Cu | OK |
| Theoretical Reference Framework PDFs v1-v4 (`notes/`) | 07-25 … 07-30 | none (analytic C36000 × bare response) | C36000 | OK for material. v1 lists C36000 as Zn 35.8 / Pb 2.7 and v2-v4 as Zn 35.4 / Pb 3.1: the composition differs between versions. |
| `presentation_material_penetration_and_phase2.md`, `Technical_Report_Phase2_detector_selection.md`, `alloy_2_4_attenuation_correction.md`, `medipix3_vs_eiger2_report` | 06-26 … 08-03 | no transport alloy2 use found | -- | OK |

## Risk going forward

Re-running any `mpu_transport_*_alloy2` config today silently simulates **copper** under an alloy2 (brass) name. Fixing it means either restoring an `[alloy2_brass_block]` detector file for those configs or renaming them. The configs are root-owned, so this needs your decision and the chown fix.
