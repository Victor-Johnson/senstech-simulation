# SensTech handover — claim-confirmation audit

Eight-item checklist worked against the codebase. Every number below is read from
the ROOT files, the configs, or the results CSVs on disk; nothing is assumed.

**Table 10 was not modified.** `table10_native.csv`, `table10_matched.csv` and both
`cnr_*.csv` are byte-identical to the delivered versions (checksums in
`data/baseline_checksums.txt`). All variants are additional, separately tagged rows.

Reproduce: each `itemN_*.py` is standalone, `PYTHONPATH=. ./venv/bin/python <script>`.

| # | Claim | Decision |
|---|---|---|
| 1 | EIGER2's 80 keV upper edge | **Revised** — it is a Python mask, not a simulation setting, and corresponds to one of three real EIGER2 outputs |
| 2 | CdTe charge transport | **Confirmed** — silicon model is used, but it is empirically immaterial here |
| 3 | "Validation" of the simulation | **Revised** — it is an analytical consistency check on one factor |
| 4 | Ranking certainty | **Revised** — top three are statistically unresolved |
| 5 | Incident vs deposited energy | **Revised** — mechanism is ~55% fluorescence escape, not Compton alone |
| 6 | Numerical consistency | **Revised** — four statements do not reproduce |
| 7 | Interaction probability as a ceiling | **Revised** — bounds events, not a real chip's pixel counts |
| 8 | Alloy discrimination | **Revised** — "cannot distinguish" is an exposure limit, not a physical one |

---

## Item 1 — EIGER2's 80 keV "upper edge"

**Claim.** `material_penetration_report.md:103`: *"Lower energy threshold (4 keV), upper
threshold (80 keV) | **On datasheet** | Taken directly from the published spec."* and `:117`
*"EIGER2 has a hard upper energy threshold at 80 keV"*.

**Checked.** All 551 generated configs; `phase2_selection_experiment.py:91-104`; the 168
`p2_bare_*` ROOTs.

**Test / result.** Every `[DefaultDigitizer]` block in the campaign contains exactly three keys —
`threshold`, `electronics_noise`, `threshold_smearing` — all *lower* discriminators. Zero configs
contain `upper`, `saturation`, `adc_` or `qdc`. **The 80 keV edge exists nowhere in the
simulation.** It is applied only in Python, at `:100`, against collected cluster charge × 4.43 eV,
while the theory branch at `:117` cuts on incident photon energy. Same number, two different
physical quantities — the entire source of the +90.7% δ.

All three of EIGER2's real outputs are recoverable from the existing ROOTs, no reruns
(`item1_eiger2_modes.py`), full 14-energy × 5-alloy grid, native 0.75 mm:

| EIGER2 output mode | N_theory | N_sim | δ | rank vs the other 5 |
|---|--:|--:|--:|--:|
| **Difference image (4–80 keV)** ← currently modelled | 3,463 | 6,372 | +90.7% | 6th of 6 |
| **Lower-threshold image (≥4 keV)** | 15,485 | 15,622 | **+0.9%** | **5th — overtakes Medipix3** |
| Upper-threshold image (≥80 keV) | 13,987 | 9,250 | −33.7% | 6th of 6 |

`lower − upper = difference` holds exactly for all five alloys. Two things follow. First, the
4–80 keV window is **not an error** — it is precisely EIGER2's *difference image*, a real output.
Second, in lower-threshold (counting) mode δ collapses from +90.7% to **+0.9%**, the same
agreement as the wide-window chips — independent confirmation of the deposited-vs-photon-energy
explanation — and EIGER2 overtakes Medipix3 at **3.5σ** (15,622 ± 58 vs 15,349 ± 53).

**Unresolved contradiction.** The report cites the datasheet for the 80 keV upper threshold; the
code comment (`material_penetration_experiment.py:133-137`, M. Sultana 2026-07-25, and
**uncommitted — working tree only**) says the datasheet carries 8–100 keV as the system range and
4–80 keV as the *discriminator* range. Only the vendor can settle which output SensTech intends.

> **Replacement wording.** "EIGER2 is modelled as its 4–80 keV *difference image*. Read instead as
> a lower-threshold counting image — the more likely choice for a penetration application — it
> registers 15,622 counts rather than 6,372, agrees with first-principles theory to 0.9%, and
> ranks fifth rather than last. Its position is conditional on operating mode, which is not yet
> confirmed with Dectris."

## Item 2 — CdTe charge transport

**Claim.** `Handover §3.5`: transport uses *"the Jacoboni mobility parametrisation originally
derived for silicon and applied here to CdTe"*.

**Checked / test.** `mobility_model = "jacoboni"` appears in **566 occurrences with zero
alternatives**; no trapping or recombination in either live campaign; linear field throughout.
Allpix v3.2.0 (confirmed in-container) offers only silicon-fitted parameterisations by name, but
accepts `mobility_model = "constant"`. Re-ran 80/100/150 keV × 6 detectors with CdTe values
(μ_e 1100, μ_h 100 cm²/Vs; τ_e 3000 ns, τ_h 500 ns) — **twice**, because Allpix propagates
*electrons only* by default, so the first arm could not see hole physics at all.

| arm | count probability | collected charge | cluster size | ranking |
|---|--:|--:|--:|---|
| electrons only | ≤0.20% | ≤0.40% | ≤0.40% | unchanged |
| **+ holes propagated** | **≤0.16%** | **≤0.43%** | **≤0.50%** | **unchanged** |

**Why it barely matters** (drift vs trapping timescales at 5 kV/cm): electron transit is ~18 ns
against a 3,000 ns lifetime — under 1% trapped. Holes would be ~40% trapped, but they drift *away*
from the pixel implant and are collected at the back contact, while `SimpleTransfer`
(`max_depth_distance = 5um`) only collects carriers arriving at the implant. Hole trapping
therefore cannot affect this counting metric whatever its parameters — which the measurement
confirms. The counting result is dominated by *absorption*, which Geant4 already models with real
CdTe cross-sections.

> **Replacement wording.** "Charge transport uses a silicon mobility parameterisation and models no
> trapping. Substituting CdTe mobilities and lifetimes, with holes propagated, changes counts by
> under 0.2% and leaves the ranking unchanged: this metric is absorption-limited, not
> transport-limited. Transport fidelity would matter for energy resolution and long-term
> polarisation, neither of which this study measures."

## Item 3 — what the "validation" proves

**Claim.** `Handover §4`: *"strong evidence that the simulation pipeline is trustworthy"*;
`§1`: *"Independently validate the Monte Carlo simulation against a first-principles physics
prediction."*

**Test / result.** `build_table()` computes `n_theory += N0*wE*tE*pE` and `n_sim += N0*wE*tE*r`.
**Five of eight inputs are common-mode** — N₀, spectrum weight w(E), alloy transmission T(E),
sensor thickness, and the window edges. The comparison varies exactly one factor: analytic
`P_CdTe(E)` vs simulated `R_d(E)`. An error in the spectrum or the alloy attenuation moves both
sides identically and is undetectable by this check. A repo-wide search finds **no measured or
hardware data of any kind**; Phase 4 was never executed.

> **Replacement wording.** "The <1% theory–simulation agreement is an analytical consistency check
> on the detector-response factor: it confirms the simulated detection efficiency reproduces the
> analytic absorption probability, which would catch a misconfigured sensor, thickness or
> digitizer. It is not physical validation — no measured detector data was used — and it cannot
> detect an error in the source spectrum or the alloy attenuation, which both calculations share."

## Item 4 — uncertainty in the ranking

**Claim.** `Handover §4`: ranking *"Timepix4 > Medipix4 > Timepix3 > Medipix3 > EIGER2"*; §8
shortlists Timepix4 and Medipix4.

**Test / result.** Using the `sigma_sim` already stored in `table10_native.csv`:

| adjacent pair | difference | combined σ | separation |
|---|--:|--:|--:|
| HEXITEC − Timepix4 | 131 | 81 | **1.6σ** |
| Timepix4 − Medipix4 | 86 | 81 | **1.1σ** |
| Medipix4 − Timepix3 | 1,491 | 79 | 18.8σ |
| Timepix3 − Medipix3 | 1,534 | 77 | 20.1σ |

The tier boundaries are real; the ordering *within* the top three is not. Note an earlier internal
document, `analysis/reports/Handover_Document_SensTech.md:58`, said exactly this — *"statistical
tie… report tiers, not a false 1-to-5 ranking"* — and the final PDF dropped it.

Modelling uncertainty is reported separately, per the checklist: operating mode (item 1) moves
EIGER2 by **2.45×**; transport (item 2) by **<0.2%**. Multi-seed sampling was descoped. **Hazard
recorded:** `RANDOM_SEED` is not part of any output filename, so a seed rerun silently overwrites
the campaign — always pair it with `OUTPUT_TAG`. Concurrent runs also race on the shared
`modules.root`.

> **Replacement wording.** "Timepix4, Medipix4 and HEXITEC are separated by 1.1–1.6σ of
> Monte-Carlo uncertainty and are statistically unresolved under this simulation; they should be
> reported as a single leading tier. The tiers below them are separated by 19–20σ and are robust."

## Item 5 — incident vs deposited energy, at event level

**Claim.** The earlier investigation attributed EIGER2's 90–150 keV counts to Compton scattering.

**Test.** No per-event data existed — all 566 ROOTs were histogram-only. Enabled
`[ROOTObjectWriter]` + `record_all_tracks` and re-ran EIGER2 at 90/100/120/150 keV (0.75 mm),
producing genuine Geant4 interaction records for the first time in this project. Events classified
by `MCTrack`'s own `origin_g4_process_name_` and `end_g4_vol_name_`.

Mechanism of the events landing inside the 4–80 keV window:

| beam | Compton | K-fluorescence escape | mean deposit, fluorescence route |
|--:|--:|--:|--:|
| 90 keV | 26.4% | **73.6%** | 65.2 keV |
| 100 keV | 39.0% | **61.0%** | 75.3 keV |
| 120 keV | **99.7%** | 0.3% | 94.7 keV → outside the window |
| 150 keV | **99.8%** | 0.2% | 124.1 keV → outside the window |

The escaping photon carries **24.7–25.9 keV** — between Cd Kα (23.1) and Te Kα (27.5) — confirming
it is genuinely K-fluorescence. The sharp switch at 120 keV is simply that E − 25 keV stops landing
under 80 keV.

Weighted by each energy's actual contribution to the +3,285 excess, the split is **≈55%
fluorescence escape / ≈45% Compton** (unweighted event counts give 39%/61%, which over-weights the
sparsely-populated high energies).

> **Replacement wording.** "High-energy photons enter EIGER2's 4–80 keV count through two measured
> routes: CdTe K-fluorescence escape, where a ~25 keV Cd/Te X-ray leaves the sensor after
> photoelectric absorption (~55% of the effect, dominant at 90–100 keV), and Compton scattering
> (~45%, dominant at 120–150 keV). Both are confirmed from Geant4 interaction records."

## Item 6 — numerical and version consistency

| statement | reality | decision |
|---|---|---|
| δ column | **3 of 6 rows cannot be recomputed** from the N_theory/N_sim printed beside them (Timepix3 6.69 vs 6.33, Medipix3 15.20 vs 14.28, EIGER2 90.73 vs 84.02). Published δ is the *mean of per-alloy δ*; the columns are means. | Revised |
| "the **four** chips … agree to under 1%" | **Three** (HEXITEC +0.80, Timepix4 +0.08, Medipix4 −0.39). Timepix3 is +6.69% — and the next sentence already calls it narrow-window. | Revised |
| "**every chip** loses roughly 15%" | True for five (15.0–15.6%). **EIGER2 loses 0%** — it is 0.75 mm in both scenarios. | Revised |
| "a total of **84** bare-detector runs" | **168** (84 at 1 mm + 84 at 0.75 mm); 84 describes one scenario. | Revised |
| Figure A2 provenance | Built by `phase2_energy_spectra.py:37` with no thickness tag → EIGER2's 1 mm runs. Its Cu total is **6,043 vs Table A1's 5,241 (+15.3%)**. Control: Timepix4 agrees **exactly** (16,510 = 16,510), so the fault is EIGER2-specific. Those 1 mm runs are separately known-bad. | Revised |

> **Replacement wording.** "δ is the mean of the per-alloy δ values, which is not recoverable from
> the tabulated mean N_theory and N_sim; state the definition explicitly or tabulate per-alloy δ.
> Three chips agree to under 1%. Five of six chips lose ~15% at matched thickness; EIGER2 loses
> nothing, being 0.75 mm in both. The campaign comprises 168 runs across the two scenarios."

## Item 7 — interaction probability vs count probability

**Claim.** `Handover §3.4`: *"a physical ceiling that no detector's counted signal can exceed,
regardless of its electronics."*

**7a — which coefficient?** μ comes from `spekpy.DataTables.MuData("nist_mu.dat")`. Cu at 100 keV:
pipeline **0.4585** vs NIST with-coherent 0.4584, without-coherent 0.4205, photoelectric 0.0379 —
so it is **total attenuation including coherent (Rayleigh) scattering**. Rayleigh deposits
essentially no energy, so `1−exp(−μt)` is a **valid but loose** ceiling, conservative in the safe
direction. A tight bound on energy-depositing interactions would use total-minus-coherent or μ_en/ρ.

**7b — can one photon produce several reported units?** Yes, and it scales with pitch:

| detector | pitch | pixel hits per incident photon | pixels / ceiling |
|---|--:|--:|--:|
| HEXITEC | 250 µm | 1.51–1.57 | 1.51–1.60 |
| EIGER2 | 75 µm | 2.07–2.26 | 2.08–2.29 |
| Timepix4 | 55 µm | 2.48–2.74 | 2.48–2.77 |
| Medipix3 | 55 µm | 2.73–2.92 | 2.74–2.96 |

Against *events* the ceiling holds (1.00–1.02, the small excess being oblique path lengths) — and
events are what the pipeline compares. But a real photon-counting ASIC counts **pixel discriminator
firings**, and without charge-summing that is 1.5–2.9× higher, **in a pitch-dependent order that
runs opposite to the reported ranking** — HEXITEC's coarse pixels share least.

> **Replacement wording.** "Transmission × interaction probability bounds the number of *unique
> detected primary events*, which is the quantity compared here, and every detector respects it. It
> does not bound a real chip's raw pixel-count output: charge sharing makes one photon fire 1.5–2.9
> pixels depending on pitch, so a chip without charge-summing can legitimately report more counts
> than this ceiling."

## Item 8 — alloy discrimination

**Claim.** `Handover §4`: *"Every chip … achieves a similar, strong contrast-to-noise ratio
(CNR ≈ 40) … No chip, however, can reliably distinguish pure copper from copper-nickel 90/10; this
is a limit set by the alloys' near-identical physical properties, not by detector choice."*

**Result.** The reported mean conceals a spread of up to **83×** within a single detector
(1.08 → 89.70). The worst pair is `Cu vs CuNi 90/10` for **every** detector.

CNR is `|N₁−N₂|/√(N₁+N₂)` on the N₀-scaled counts, so **CNR ∝ √N₀** exactly. Every quoted value is
conditional on the arbitrary 10⁶-photon budget:

| detector | CNR @10⁶ | N₀ for CNR = 5 | more photons |
|---|--:|--:|--:|
| Medipix3 | 1.11 | 2.02×10⁷ | 20× |
| Timepix4 / Medipix4 / HEXITEC | 1.08 | 2.14×10⁷ | 21× |
| EIGER2 | 0.91 | 3.05×10⁷ | 30× |

So the pair is separable — it needs ~20–30× more photons. No exposure, background, dark-count or
CNR cutoff is defined anywhere, so the quoted figures are an optimistic upper bound at one
arbitrary budget.

> **Replacement wording.** "Report worst-pair alongside mean CNR: the ~40 average spans 1.1 to 89.7.
> Copper versus copper-nickel 90/10 reaches CNR 1.1 at the assumed 10⁶-photon budget, and since CNR
> scales as √N₀, separating them at CNR 5 needs roughly 20–30× more photons. This is an exposure
> limit at the modelled budget, not an absolute physical one."

---

## Changes made to the repository

Additive only, all behind environment flags; **default config emission verified byte-identical**.

- `simulation/run_phase2_selection.sh` — `MOBILITY_MODEL`, `MOBILITY_ELECTRON`, `MOBILITY_HOLE`,
  `TRAPPING_TIME_ELECTRON`, `TRAPPING_TIME_HOLE`, `PROPAGATE_HOLES`, `WRITE_OBJECTS`.
- `simulation/run.sh` — forwards the above.
- **Bug fixed in all three drivers:** `ALLPIX_VERSION` was captured with `allpix --version | head -1`,
  which SIGPIPEs the process and intermittently captured *multiple lines*, embedding a newline in the
  manifest row and splitting it across two lines. 26 rows written during this audit were corrupted
  and have been repaired (`phase2_selection_run_manifest.corrupt.bak` retains the damaged copy);
  capture now uses `sed -n '1p'` and every free-text field passes through a `csv_safe` sanitiser.
  This was the first real exercise of the v2 provenance machinery, which now records image ref,
  digest, Allpix version, driver name and git revision correctly.

New ROOT files are all separately tagged (`_cdte`, `_cdte075`, `_cdteh`, `_cdteh075`, `_obj`) and
do not collide with the published campaign.
