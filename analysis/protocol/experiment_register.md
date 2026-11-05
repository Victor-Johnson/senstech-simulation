# Experiment register (live)

Source plan: ~/.claude/plans/i-want-to-run-sprightly-swan.md. Input IDs refer to inputs_register.csv. Status: ✅ runnable now · 🟡 runnable as tag-A bracket · ⛔ blocked by a ★ input. Update the Status column as inputs arrive.


Status key: ✅ runnable now · 🟡 runnable as an A-bracket · ⛔ blocked by a ★ input.

| Exp / Phase | Inputs (tag) | Process | Outputs (protocol table) | Status |
|---|---|---|---|---|
| **Exp 0 / P0 Validation** | SpekPy (S); XCOM (S); literature V1–V3 data (S, §2f); IFAE/Varex data (L9/V5) | Empty-beam spectra vs SpekPy; primary-only transmission vs XCOM; weighted vs unweighted check; production-cut multi-pixel fraction; V1 Am-241 tuning of σ_cloud, noise, dispersion; V2 threshold scan (trapping); V3 count-rate curve (τ, pulse); V4 blind prediction | Protocol Tbl 10, Improvement Tbl 5, frozen model hash | Checks ✅; V1–V3 🟡 (after §2f); **V4 ⛔ L9/V5** |
| **P0 Cost book** | B2, V6 | Triangular distributions per option | Improvement Tbl 6, C_alt | ⛔ B2 |
| **Exp 1 Response** | Stage B mono beams; L3, L8, V2 | B-sc per detector; Stage C summing on/off, bias ±20%, LINDA 1 vs 2 mm (Transient) | Tbl 11 η(E), Tbl 12 peak/escape/multi-pixel/tail/FWHM | LINDA, Medipix3 ✅; VAREX 🟡 V2; photodiode 🟡 S1/S2 |
| **Exp 2 Thick alloy** | Stage A (T1, T4, T6), Stage B/C, T2 target SNR | Fold; pre-screen cells; t to target SNR | Tbl 13; photon-starved thickness | Shape 🟡; **absolute t ⛔ T2, T5**; alloys ⛔ T1 (brass bracketed) |
| **Exp 3 Scatter** | Stage A variants (Tbl 14 rows), T6 | One-at-a-time geometry; matched and common 7 mm fan | Tbl 14 SPR, ΔCNR, ranking change | 🟡 (geometry all A until T6) |
| **Exp 4 Resolution** | W edge at 2–5° (G4_W exact); focal spot; TDI motion; T2 defect | Stage A edge object → B/C → slanted-edge MTF, NNPS, DQE, d′ | Tbl 15 | MTF/DQE ✅; **d′ ⛔ T2** |
| **Exp 5 Discrimination** | T1 alloys; bins; separate seed for bin choice | R, σ_R, CNR(R); drift with thickness; LINDA 1/2/4/6 bins | Tbls 16, 17, 18 | ⛔ T1 (method runnable on a brass bracket) |
| **Exp 6 Dead time** | L1, V3, Medipix3 literature; TL-01…TL-09 | **Time-domain layer (TL):** Poisson arrivals from the Stage-B hit library → event-driven CR-RC pulse model → dead time / pile-up / charge-summing busy time → counters and TDI → metrics. Live fraction decomposed into readout / pixel / summing penalties | Tbls 19, 20, 21 | 🟡 L1/V3 bracket; 6b ⛔ L8/V4 |
| **Exp 7 Pile-up/line speed** | L1, L2, L4, T5; TL-01…TL-09 | Same TL layer at flux grid 1e4–1e8 photons/mm²/s (open-beam characterisation, R-02) plus operating points from tube current × spectrum × attenuation; pulse overlap within shaping time, counters/overflow, TDI sum; fit both loss models | Tbls 22, 23, 24 decision map | 🟡; **operating-point cells ⛔ T5** |
| **P1 Shapley** (Tbls 7, 8) | M0 and Mref from Exp 1–7; T3 for the G1 ceiling | 2⁸ = 256 coalitions per candidate, task and endpoint; bootstrap CIs | φᵢ per mechanism; non-structural ceiling | LINDA 🟡; photodiode 🟡; **G1 decision ⛔ T3** |
| **P2 Screening** (Tbls 9–11) | 12 factors per candidate; ≥5 seeds with common random numbers | 2^(12−7) resolution-IV design (32 runs) + foldover; Morris; Benjamini–Hochberg | Main effects, interactions, shortlist ≤6 | 🟡; G2 needs B4 |
| **P3 Optimisation** (Tbl 12) | Shortlist; constraints (T3, T5) | LHS ≥20 points per factor → GP surrogate → max-min margin; direct-run check | Optimum per thickness class | ⛔ T3/T5 for constraints |
| **P4 / §8.8 / Exp 8 Cost** (Tbls 13, 14, 26–29) | B1, B2, V6 | Joint simulation of bundles; Pareto front; knee; Ck vs C_alt | Frontier, knee, budget picks | ⛔ B1/B2 (φ part runnable) |
| **P5 Robustness** (Tbl 15) | Uncertain-input ranges (all A tags) | Sobol; drift scenarios (polarisation 11–14%, temperature, composition, alignment, speed) | Rank-stability table | 🟡 |
| **P6 Pilot** | Hardware at IFAE / Sens-Tech | Outside simulation; we supply predicted φ with CIs | Tbl 16 predicted column | n/a |
| **§9 Compatibility** | Integration team | Checklist | Tbl 30 | not simulation |


## 5. Execution order (each step has a gate; a failed gate goes back a step)

0. **Freeze the inputs register.**
   - Create `analysis/protocol/inputs_register.csv` with columns: name, value, unit, tag, source, owner, used_by, bracket. Every row in §2 goes in, plus the S/P values from both PDFs.
   - Create `analysis/protocol/experiment_register.md`, which is §4 kept live.
   - Create a partner questionnaire per owner from §2. **Nothing else starts until you have reviewed this register.**
1. **Spikes**, each answering a feasibility question with a measurement:
   - (a) Allpix `[TextWriter]` PixelCharge round-trip and parser.
   - (b) Livermore list plus cuts: run time and multi-pixel fraction versus QGSP_BERT on one existing config.
   - (c) TransientPropagation run time for 1 mm and 2 mm CdTe.
   - (d) Is Geant4 available in the Allpix image for a standalone app (headers plus cmake)? If not, use a separate pinned Geant4 image.
   - (e) Parallel containers.
2. **Exp 0 checks** that need no partner data: SpekPy, XCOM, weighted vs unweighted, cut check; then V1–V3 against the literature. **Gate G0 (partial):** V4 stays open until L9/V5 arrive.
3. **Stage B response matrices**: LINDA, Medipix3, VAREX bracket, photodiode bracket.
4. **Exp 1 → 4 → 6 → 7** (detector-only physics), then **Exp 2, 3, 5** once Stage A and T1/T6 exist.
5. **P1 Shapley → P2 → P3 → P4 → P5**, following the documents' own priority if time runs short: P1, then P2 with C0 factors only, then P4 for the C0/C1 bundles.


### Time-domain layer (shared by Exp 6/7, P1 mechanism 1, A3–A5, A7, L5–L8)

1. **Hit library**: Stage-B per-event, per-pixel charge plus arrival time (TextWriter), mono-energetic or spectrum-folded.
2. **Arrivals**: Poisson process at flux φ, with the event drawn from the library by spectrum weight (TL-08).
3. **Pulse model**: CR-RC with peaking time t_p (TL-01–TL-03); induced-charge timing from drift (TL-07).
4. **Front end**: threshold crossing, dead time (paralyzable or non-paralyzable, D-L10/11), pile-up (pulse overlap), charge-summing coincidence window and neighbour busy time (TL-05/06).
5. **Counters and TDI**: per-bin counters with depth (D-L17), overflow, TDI sum over rows (D-L07, D-L18).
6. **Metrics**: measured/true rate, wrong-bin fraction, mean energy shift, live fraction.

**Validation (TL-09):**
- At low flux the result is exactly the single-photon result.
- An ideal dead time reproduces m = n/(1+nτ) and m = n·e^(−nτ).
- Pulse width above threshold is consistent with LINDA's ~1 µs dead time (TL-04).

### Exp 0 checks added 2026-11-05 (review items 1–4)

| Check | Inputs | Process | Output | Status |
|---|---|---|---|---|
| **X0-T** transport | Stage-A geometry, G4 μ (`stagea_spike mu`) | Unscattered-primary transmission through the object vs exp(−μ_G4·ρ·t), per 1 keV bin | exp0/transport_check.csv | spike: pass (worst 3.1σ); Stage-A end-to-end run in progress |
| **X0-D** data | XCOM 1 keV grid (reference/xcom), G4 Livermore μ/ρ | \|μ_G4/μ_XCOM − 1\| ≤ 2% on μ/ρ | exp0/data_check_summary.csv | alloys + CdTe pass; W/GOS/CsI fail below K-edges (coherent term, PH-17) |
| **X0-B** band | X0-D | Thick-part T band from the μ/ρ difference (shared Stage A → absolute exposure time only, not rankings) | exp0/thick_part_T_band.csv | done |
| **X0-CSA** hole tail | TransientPropagation + CSADigitizer subset | Python Ramo + trapping + CR-RC tail vs Allpix CSA amplitudes | — | REQUIRED, not built |
| **X0-IT** integration time | config_rules.validate | every protocol config validated; earlier campaigns audited | audit/*.csv | rule live; audit re-runs in progress |
| **X0-DR** drift | MCTrack depths | per-photon t_e, t_h vs Allpix carrier times | exp0/drift_validation_*.csv | pass |

## Changes 2026-11-05 (review: FWHM breakdown, beam, audit)

| Item | Decision / status | Where |
|---|---|---|
| Stage B illumination | Uniform flat GPS plane beam (rectangle, +z) over fiducial + 0.1 mm; pixel-level metrics scored only for photons entering the central fiducial square (LINDA 4x4, Medipix3/Timepix3 16x16, VAREX 8x8). The Allpix `beam_shape = "rectangle"` source was measured to be bell-shaped (sigma ~ size/2), not uniform. (PH-20) | `stageb.py` (`gps_macro`, `fiducial`, `load_fiducial`) |
| Real array edges | Not in Stage B. The real arrays (LINDA 8x20 etc.) and their edge losses go in a separate system-level model (Exp 4/6b, line-level counts). | to build |
| Exp 4 flat field / NNPS / DQE | Must use uniform illumination (GPS plane), never the Allpix `beam` source. | Exp 4 |
| Beam audit | `audit_beam.py`: earlier campaigns (1 mm Gaussian sigma on >= 14 mm matrices) have no photons outside the matrix or within 0.5 mm of its edge; only protocol milestone 1 (LINDA 8x20, about 4.6% outside) and the 2 mm spike were affected. Bell vs flat comparison: `beam_bell_vs_flat.py`. | `audit/beam_footprint_audit.csv`, `audit/beam_bell_vs_flat.csv` |
| X0-V1 FWHM breakdown | `exp0_v1_fwhm.py`: Stage B variants (ideal / no Fano / no trapping / base / transient mu-tau_h 1.8e-4 and 1e-5) x Stage C (full vs 2x2 summing, noise modes, dispersion 0/20/40/80 e-). Core-only Gaussian fit [mu-1 sigma, mu+3 sigma]. | `exp0/v1/fwhm_breakdown.csv` |
| CSM noise model | 80 e- per pixel on all 4 block pixels (`noise_mode = "pixel_all"`), i.e. 160 e- effective. The earlier 175 e- per recorded pixel, then summed, double-counted the summing noise. Interpretation of D-M04 to be confirmed. | `electronics.py`, `exp0_v1.py` |
| Fano factor | 0.24, explicit in every Stage B config (PH-19). | `stageb.py` |
| Ballistic deficit | Not modelled in Stage B (PH-21); X0-CSA remains REQUIRED. | -- |
| MCTrack reader | C++ (`simulation/protocol_runs/tools/mctrack_depths.cc`), about 600x faster; regression test against the Python reader. | `tests/test_mctrack_reader.py` |
| Audit hang | `mpu_bare_timepix3_cdte_50keV` hung on its last event with 1 us integration (3.5 h); killed and logged as FAILED. Watchdog (30 min limit, SIGKILL) for the rest. | `simulation/protocol_spikes/audit_watchdog.sh`, `data/audit_itime/hung/` |
