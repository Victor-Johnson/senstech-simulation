# ROADMAP: LINDA / Medipix3 / VAREX / Sens-Tech protocol programme (M2–M7)

Plan of record: `~/.claude/plans/i-want-to-run-sprightly-swan.md`. Inputs are tracked in `analysis/protocol/inputs_register.csv` (IDs below), experiments in `analysis/protocol/experiment_register.md`, and the running log in `PROGRESS.md`. M1 (first milestone: Stage B 1 mm for LINDA/Medipix3/VAREX at reduced statistics, Exp 0 checks X0-T/X0-D, integration-time audit) is **done** (2026-11-05).

**Labelling rule.** Any result that depends on a placeholder input (tag A, or a bracket for a MISSING/TBD value) is **PROVISIONAL (tag A)**. Every output table carries a `provisional` column naming those inputs.

**Estimate basis (measured on this machine: 28 cores, 23 GB; one Allpix run uses all cores, so runs are sequential):**

| Stage | Measured rate | Basis |
|---|---|---|
| Stage B (Allpix, GenericPropagation) | ~1.7 ms/event | milestone 1: 1.8 M events in 3,060 s, sharing the CPU with the audit |
| Full-statistics response matrix (170 energies × 1e5 events) | **~8 h per detector config** | |
| Same at 4e4 events/energy (screening grade) | ~3.2 h | |
| Stage B transient (induced charge) | 0.24 s/event | 3k events ≈ 10 min |
| Stage A (standalone Geant4) | 5e7 primaries in 963 s (~16 min) | 2e5 in 3.4 s |
| Stage C/D (Python electronics, folding, metrics) | seconds to minutes per configuration | |

"Build" = agent working time to write and test code. "Compute" = wall-clock on this machine. Overnight queue ≈ 12 h.

---

## M2: Exp 0 validation (gate G0)

**Tasks**
1. Done: X0-T transport check (Beer–Lambert with Geant4 μ), X0-D XCOM data check, drift-time validation, integration-time rule and audit, flat-beam set-up, V1 simulation side (Am-241 SPM/CSM spectra, FWHM breakdown).
2. X0-B: weighted vs unweighted Stage A check (variance-reduced source vs analogue run, same observable).
3. Production-cut check: Stage B at a lower range cut vs default, compared on multi-pixel fraction and peak fraction (Medipix3, 3 energies).
4. **X0-CSA (required):** Stage C analytic Ramo + CR-RC ballistic-deficit model, compared with Allpix CSADigitizer on the same events (59.5 keV and 2 higher energies).
5. V1 comparison with published Am-241 spectra (peak position ±0.5 keV, FWHM ±10%, multi-pixel fraction). Note: no CSA yet, so the simulated peak is expected to be slightly narrow.
6. V2 threshold scan vs published Medipix3/Timepix3 scans (trapping, dispersion).
7. V3 count-rate curve vs published curve (needs the M3 timing layer).
8. V4 blind prediction vs IFAE/Varex measurement.
9. Settle PH-06 (Fano conflict) and PH-07 (charge-cloud width) from V1.

**Inputs**

| Needed | Status | Placeholder used meanwhile |
|---|---|---|
| Published Am-241 spectra, threshold scans, count-rate curves (§2f) | colleague, in progress | none (comparison waits) |
| B-03 Exp 0 tolerances | MISSING | protocol Tbl 10 proposals (0.5 keV, 10% FWHM), tag A |
| D-L28 / D-V16 measured data (V4) | MISSING (L9, V5) | **blocks V4**; D-L28 fallback = G0 on published Medipix3 data only |
| D-M10 Medipix3 dead time; D-M08 peaking time | colleague | literature bracket |
| PH-01..04 CdTe transport; PH-06 Fano | in progress / CONFLICT | Ariño-Estrada 2014; F = 0.24 |
| D-M04 / D-M12 noise and dispersion | in progress | 80 e⁻ per pixel; 40 e⁻ |

**Definition of done:** Protocol Tbl 10 and Improvement Tbl 5 filled. V1–V3 each pass or fail against stated tolerances. X0-CSA agreement stated. Frozen model hash recorded. G0 decision written (pass / pass on published data only / fail).

**Sanity checks:** Beer–Lambert (X0-T, already χ²/ndf 53/45); XCOM data ≤2% (alloys and CdTe pass; W/GOS/CsI coherent outliers recorded); drift times vs d²/μV; energy-budget closure (sum of pixel charge ≤ E, and full-energy peak at E minus trapping deficit); CSA vs CSADigitizer within tolerance.

| | Estimate |
|---|---|
| Build | X0-CSA 1–1.5 days; X0-B + cut check 0.5 day; V2/V3 harness 0.5 day; comparisons 0.5 day per dataset once data arrive |
| Compute | X0-B ~1 h; cut check ~2 h; X0-CSA (transient + CSADigitizer, 3 energies × ~20k events) **~4–5 h**; V2 threshold scans are Stage C only (minutes) → **~1 night** |

---

## M3: core experiments 2, 5, 7 for LINDA, Medipix3, VAREX

**Tasks (unblocked builds first)**
1. **Timing layer** (Stage C, time domain), with analytic tests:
   - Poisson arrivals on Stage B event lists
   - paralysable / non-paralysable dead time
   - CR-RC (and bipolar) pulse pile-up with per-photon drift time (TL-07)
   - charge-summing coincidence window and busy time
   - counters with overflow
2. **TDI:** row-wise accumulation, line-rate budget, belt-speed coupling; Medipix3 emulated TDI over 48 rows (R-03).
3. **Stage A production phase spaces at 639 mm:** kVp × prefilter × alloy grade × thickness (+ open beam), per detector fan slit.
4. **Fold** Stage A phase space × Stage B response × Stage C electronics → counts per bin per line.
5. **R-value metrics (Exp 5):** R, σ_R (analytic + MC check), CNR(R), drift with thickness, LINDA 1/2/4/6-bin variants, separate seed for the bin choice.
6. **Exp 2:** exposure time to target SNR through the thickest part; photon-starved thickness; pre-screen cells.
7. **Exp 7:** count loss vs flux (both loss models fitted), spectral drift, overflow, line speed; Tbls 22–24 decision map.
8. Full-statistics Stage B response matrices (1e5 events, 170 energies) for LINDA, Medipix3, VAREX 1 mm (+ VAREX thickness bracket).

**Inputs**

| Needed | Status | Placeholder (all tag A) |
|---|---|---|
| T-01 alloy grades | MISSING (T1) | CuZn37 / CuZn39Pb3 / CuSn8 / CuNi10Fe1Mn bracket |
| T-03 target SNR / d′ | MISSING (T2) | SNR 3 / 5 / 10 |
| T-11 tube current, belt speed → operating flux | MISSING (T5) | tube-current bracket (R2); **absolute exposure-time cells PROVISIONAL** |
| D-L10/11 LINDA dead time and model | CONFIRM / MISSING (L1) | 0.5 / 1 / 2 µs × paralysable and non-paralysable |
| D-L14 / TL-03 shaping | MISSING (L2) | 100 ns – 1 µs |
| D-L17/18 counters, TDI readout | MISSING (L4) | 8/12/16 bit; both readouts |
| D-L24 above range | MISSING (L7, HIGH) | both scenarios (lost / clip) |
| D-M07/08/10 Medipix3 counters, peaking time, dead time | colleague | literature values |
| D-V13/14/15 VAREX thickness, τ, TDI stages | MISSING (V2–V4) | 0.75/1/1.5/2 mm; 50/100/200 ns; 4/8/16 |
| TL-05/06 summing window, busy time; R-04 | colleague / MISSING | 50–500 ns; = window to 2× |
| T-09/T-10/T-12 tube, prefilters, geometry | ASSUMED (protocol) | protocol Tbl 5, SpekPy W 12° |

**Definition of done:** Protocol Tbls 13, 16, 17, 18, 22, 23, 24 filled for LINDA, Medipix3, VAREX, with bootstrap CIs (≥5 seeds) and `provisional` columns. Decision map (Tbl 24) drawn. Every result that depends on T-03/T-11 is marked PROVISIONAL.

**Sanity checks (a failure means STOP):**
- **Analytic dead-time curves:** m = n/(1+nτ) and m = n·e^(−nτ) reproduced within 1% (MC stat).
- **Low-flux equivalence:** at 1e4 ph/mm²/s the timing layer gives exactly the single-photon Stage C counts.
- **Beer–Lambert:** Stage A unscattered primaries vs exp(−μρt) within statistics for every grade and thickness.
- **Energy-budget closure:** folded counts ≤ transmitted photons × η(E); deposited energy ≤ incident.
- **Drift times:** per-photon t_e, t_h vs d²/μV.
- **TDI:** an N-row sum equals N × single-row signal for a static object.
- **σ_R:** the analytic formula matches the MC spread within 10%.

| | Estimate |
|---|---|
| Build | timing layer + tests 1–1.5 days; TDI 0.5–1 day; Stage A production driver + fold 0.5–1 day; R metrics 0.5 day; Exp 2/5/7 tables 1 day → **~4–5 days** |
| Compute, Stage B full grids | 3 × 8 h = **24 h** (+ VAREX thickness bracket 3 × 8 h = 24 h, or 3 × 3.2 h at screening grade) |
| Compute, Stage A | 3 kVp × 5 grades × 6 thicknesses + open ≈ 93 runs × 5–16 min = **8–25 h** |
| Compute, timing / Stage C | ~2–4 h |
| Total | **≈ 3–5 nights** |

---

## M4: Exp 1, 3, 4, 6 + photodiode

**Tasks**
1. **Exp 1:** η(E) and Tbl 11/12 from the M3 full grids; summing on/off; bias ±20% (Stage B variants); LINDA 1 vs 2 mm (generic transport + Stage C Ramo model; transient only if PH-23 is triggered).
2. **Exp 3:** scatter geometry, one at a time (Tbl 14 rows), matched fan vs common 7 mm fan, via Stage A geometry variants.
3. **Exp 4:**
   - tungsten edge at 2–5° through Stage A → B → C
   - slanted-edge MTF
   - **flat field / NNPS / DQE under uniform illumination only** (GPS plane, never the Allpix `beam` source)
   - d′ for the T-02 defect
   - **real-array system model** (LINDA 8×20, edges, dead edge, inter-chip gap)
4. **Exp 6:** live-fraction decomposition from the timing layer; 6b edges/gaps.
5. **Photodiode:**
   - Geant4 scintillator deposits (CsI:Tl, GOS × 0.5/1/2/3 mm, stacked filter Cu 0/0.5/1 mm)
   - Python optical/electronic model (light yield, Swank, blur, afterglow, ADC)
   - photodiode entries in Exp 1–7

**Inputs**

| Needed | Status | Placeholder (tag A) |
|---|---|---|
| T-02 defect, T-03 d′, T-05 MTF criterion | MISSING (T2, T3) | wire/void bracket; **d′ PROVISIONAL** |
| T-12 geometry | ASSUMED | protocol Tbl 5 ± sweeps |
| D-L26 bias; D-L25 contact; D-L27 gaps and dead edge | MISSING (L8) | −300…−500 V; Schottky/ohmic; 0/20/50 µm |
| D-M06 dead edge | colleague | 0.8 mm (P) |
| D-P04–P11 photodiode (all) | MISSING (S1–S6) | **pure bracket study**: CsI/GOS, thickness, stacked, literature optics |

**Definition of done:** Tbls 11, 12 (all 4 detectors), 14, 15, 19–21 filled; photodiode columns as bracket bands; NNPS/DQE from uniform illumination verified flat.

**Sanity checks:**
- η ≤ XCOM single-pass ceiling. The M1 70 keV excess of 0.7–0.8% (about 4σ) is suspected to be backscatter from the ASIC/support and must be explained here.
- MTF(0) = 1; DQE(0) ≤ η.
- NNPS of a simulated uniform Poisson field = white noise level within statistics.
- Photodiode light-yield energy budget closes.
- Scatter SPR reproduces the M1 Stage A value (0.062) on the reference geometry.

| | Estimate |
|---|---|
| Build | image chain (MTF/NNPS/DQE/d′) 1.5–2 days; real-array system model 1 day; Exp 3 variants 0.5 day; photodiode 1.5–2 days; Exp 6 0.5 day → **~5–6 days** |
| Compute | bias ±20% Stage B: 6 configs × 3.2 h (screening grade) ≈ 19 h; Exp 3 Stage A: ~15 variants × 2 fans × 16 min ≈ 8 h; Exp 4 edge + flood (real arrays, 1e6–1e7 photons) ≈ 2–6 h per detector → ~12 h; photodiode Geant4 ≈ 2–3 h → **≈ 3–4 nights** |

---

## M5: Shapley decomposition (P1) + C0 screening (P2)

**Tasks**
1. P1:
   - M0 (baseline) and Mref (reference) per candidate (LINDA, photodiode)
   - 8 mechanisms → 256 coalitions per candidate × task × endpoint
   - only thickness, pitch and energy-range mechanisms need new Stage B (~4 configs per candidate)
   - bootstrap CIs; efficiency-axiom check
2. P2:
   - 12 factors, 2^(12−7) resolution-IV design (32 runs) + foldover, ≥5 seeds with common random numbers
   - Morris; Benjamini–Hochberg
   - shortlist of ≤6 factors

**Inputs:** T-03/T-04 (G1 ceiling), B-04 (G2 minimum effect), B-05 composite weights; all MISSING or CONFIRM. Placeholders: 5% of gap (B-04, A); equal weights (A). **G1/G2 decisions are PROVISIONAL until these arrive.**

**Definition of done:** Improvement Tbls 7–11 filled; φᵢ per mechanism with CIs; shortlist with effect sizes; G1/G2 decisions recorded (provisional).

**Sanity checks:** Σφᵢ = v(N) − v(∅) (efficiency axiom, exact); the resolution-IV generator is verified; the Shapley toy game reproduces known values; null-factor runs give zero effect within CI.

| | Estimate |
|---|---|
| Build | Shapley engine + tests 1 day; DOE / Morris / BH + tests 1 day; wiring to Stage C/D 1 day → **~3 days** |
| Compute | structural Stage B variants: LINDA ~4 × 3.2–8 h ≈ 13–32 h; photodiode Geant4 ~4 × 0.5 h; 256 coalitions × bootstrap on Stage C/D ≈ 2–6 h; P2 64 runs × 5 seeds, mostly Stage C/D (few h), plus any Stage B factor (+3.2 h each) → **≈ 2–4 nights** |

---

## M6: optimisation, cost, robustness (P3–P5)

**Tasks**
1. P3: Latin hypercube (≥20 points per shortlisted factor) → GP surrogate → max-min margin optimum per thickness class; direct-run check of the optimum.
2. P4: cost book (triangular distributions), Pareto front, knee, Ck vs C_alt, budget picks (Tbls 13, 14, 26–29).
3. P5: Sobol over uncertain inputs (every tag-A row); drift scenarios (polarisation 11–14%, temperature, composition, alignment, speed); rank-stability table.

**Inputs:** T-03/T-04/T-07/T-08 constraints (MISSING); **B-01, B-02, D-L29, D-V17 costs (MISSING) → P4 blocked**, apart from its φ part; PH-08 temperature (A); D-L25 contact (polarisation). Placeholders: constraint brackets; cost cannot be bracketed meaningfully.

**Definition of done:** Improvement Tbls 12–15 filled; frontier and knee (if costs exist); rank stability stated with Sobol indices.

**Sanity checks:** the GP predicts held-out direct runs within its CI; the optimum is re-simulated directly; Sobol indices sum ≤ 1 (first order); Pareto front monotone.

| | Estimate |
|---|---|
| Build | GP / LHS 1–1.5 days; cost model 0.5–1 day; Sobol + drift scenarios 1–1.5 days → **~3–4 days** |
| Compute | LHS ~120 points (Stage C/D cheap; structural points at screening-grade Stage B: up to ~40 × 3.2 h ≈ 5 nights if many structural factors survive P2, otherwise hours); Sobol N(k+2) ≈ 10⁴ Stage C/D evaluations ≈ 3–6 h; drift-scenario Stage B ≈ 4 × 3.2 h → **≈ 1–6 nights**, depending on the P2 shortlist |

---

## M7: hardware pilot (not simulation)

Run at IFAE / Sens-Tech. Our deliverable is Improvement Tbl 16 "predicted" column: φ with CIs for the pilot configuration, plus the frozen model hash and run IDs. **Build ~0.5 day, compute negligible**, once M5/M6 are done.

---

## Work order and rules

1. **M3 build first** (unblocked): timing layer + analytic tests → TDI → Stage A production phase spaces → R metrics → Exp 2/5/7 tables.
2. Heavy compute runs **overnight**, queued sequentially: M3 Stage B full grids, Stage A production, then M4 variants.
3. **M2 comparisons as soon as published reference data arrive** (V1 harness ready: drop files in `analysis/protocol/reference/v1/`).
4. **STOP and report when:**
   - a milestone is done;
   - any sanity check fails (Beer–Lambert, low-flux equivalence, analytic dead-time curves, energy-budget closure, drift times);
   - a result changes a previous conclusion or differs >10% from expectation;
   - a ruling or a blocked input is needed.

   Routine progress goes in `PROGRESS.md`.
5. Every output table carries a `provisional` column naming its tag-A inputs.

**Total rough budget for M2–M6:** build **~18–23 working days**; compute **~10–20 nights**. The range depends on whether VAREX thickness and structural P2/P3 factors need full-grid Stage B, and on when partner data arrive.
