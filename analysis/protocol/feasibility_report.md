# Feasibility tests 1–5 (2026-11-05)

Purpose: to check, before building the pipeline, that each piece of the plan works in this repo's toolchain, and what it costs.

Toolchain: Allpix² v3.2.0 (image digest pinned in `docker-compose.yml`), Geant4 11.2.0 with GDML and multithreading, G4EMLOW 8.5, SpekPy 2.5.4, xraydb 4.5.8 (new, independent attenuation source).

Machine: 28 cores, 23 GB RAM. Allpix already uses all cores in a single run (~27 workers), so "28 parallel containers" in the plan is wrong. Runs are sequential, each using all cores.

All configs are in `simulation/protocol_spikes/` and `simulation/stageA_g4/`. Outputs are in `data/protocol_spikes/`, which is root-owned and not committed.

---

## 1. Per-pixel charge and arrival time per event

| Question | Result |
|---|---|
| Per-event per-pixel charge readable? | **Yes.** `[TextWriter] include = "PixelCharge"` writes 3 MB per 1e4 events (60 keV, LINDA geometry). Parsing it with `analysis/protocol/textwriter.py` takes 0.3 s. Charge sums are correct: median 59.6 keV for a 60 keV beam. |
| Arrival time on PixelCharge? | **No.** It is always 0 ns, with both SimpleTransfer and PulseTransfer. The pulse lives only in ROOT objects, which uproot cannot read. |
| Arrival time anywhere? | `PropagatedCharge` carries it, but at ~0.5 MB per event, which is too heavy for production. |
| TL-07 drift times | **Confirmed.** With a constant field, 1 mm at 300 V: electrons max **32.0 ns** (predicted 31), holes max **304.6 ns** (predicted 300). |
| **Bug found** | `GenericPropagation` defaults to `integration_time = 25 ns` and silently drops charge still drifting. At 300 V over 1 mm, the 60 keV full-energy fraction falls from **0.905 (1 µs) to 0.406 (25 ns)**. |

Speed: 1.4 ms/event wall at 60 keV with charge_per_step = 10. Charge propagation is 96–99% of the time.

**Plan changes**
- Every protocol config sets `integration_time = 1us` explicitly.
- The timing layer uses Poisson photon arrival times plus analytic drift (TL-07). Electron drift (≤32 ns) is short compared with every peaking time in the brackets (≥100 ns). Hole-induced pulse shape comes from a small induced-charge subset (test 3).
- **Check, not assumed:** the existing campaigns ran with the 25 ns default (linear field, −500 V; EIGER2 −375 V). At −500 V the spike shows full collection (0.90). Low-bias runs may have lost charge and should be checked before anything is re-quoted.
- Unrelated geometry note: Allpix `beam_size` is a Gaussian **sigma**. A 2 mm sigma overfills LINDA's 2.64 mm-tall array, so only 44% of photons hit it.

## 2. Livermore vs default physics

16 runs: LINDA 330 µm and a Medipix3 55 µm patch × 60 and 150 keV × four physics settings, 1e4 events each. Data: `spike2_physics_comparison.csv`.

| Setting | Speed | Detected fraction at 150 keV, 1 mm CdTe |
|---|---|---|
| QGSP_BERT (current repo) | baseline | 0.284 |
| QGSP_BERT_EMZ | same ±5% | 0.284 |
| **QGSP_BERT_LIV** | same ±5% | **0.297** |
| QGSP_BERT_LIV, 1 µm cut | same ±5% | 0.297 |
| NIST interaction ceiling (total μ, incl. coherent) | — | 0.299 |

- At 60 keV all settings agree within 1σ (σ ≈ 0.004) on detected fraction, full-energy fraction, K-escape fraction and multi-pixel fraction.
- The 1 µm cut changes nothing measurable at these pitches.

**Decision (PH-09): QGSP_BERT_LIV with Allpix's default cut.** It costs nothing extra and agrees best with the NIST ceiling at high energy.

Multi-pixel fraction, unthresholded / 5 keV threshold: LINDA 0.47 / 0.29; Medipix3 55 µm ~0.82 (5 keV). LINDA's 29% at 5 keV is mostly Cd/Te K-fluorescence reaching neighbours, not diffusion (σ_diff ≈ 10 µm). This is a P0 tuning target (PH-07).

## 3. Cost of the hole-tailing (induced-charge) model

TransientPropagation + PulseTransfer with an analytic `pad` weighting potential.

- Allpix rejects the **linear field** for this module ("unphysical results"), so a **constant** field is required.
- First attempt (timestep 0.1 ns, 10 charges per step, 2 µs window): **~6.5 min per event.** Aborted.
- Retuned (0.5 ns, 100 charges per step, 1 µs window):

| Config | Simple (ms/event) | Induced charge (ms/event) | Ratio |
|---|---|---|---|
| 1 mm, 60 keV | 2.3 | 134 | ~60× |
| 1 mm, 150 keV | 2.4 | 223 | ~90× |
| 2 mm, 60 keV | 2.9 | 257 | ~90× |
| 2 mm, 150 keV | 7.4 | 647 | ~90× |

At 1e5 events per energy, a full induced-charge response matrix would take ~4–18 hours **per energy point**, which is not feasible.

**Plan change:** the induced-charge model is used for a small calibration subset only (a few energies × 1 and 2 mm × ~1000 events). From it we derive a hole-tail kernel, applied in Stage C to the fast-model response matrix. This needs a validation step: the kernel-corrected fast model must match direct induced-charge runs at a held-back energy.

### 3b. Does the induced-charge model change the spectrum? (1000 events each; `spike3_tail_comparison.csv`)

At 1000 events the integrated-charge response is the same: 1 mm and 2 mm, 60 and 150 keV, all within statistics.

| Metric | Simple | Induced charge |
|---|---|---|
| Detected fraction | 0.980 / 0.284 / 1.000 / 0.487 | identical |
| Full-energy fraction | 0.861 / 0.238 / 0.843 / 0.435 | 0.866 / 0.238 / 0.843 / 0.434 |
| Low-energy tail (50–95% of E) | 0.104 / 0.015 / 0.142 / 0.016 | 0.099 / 0.015 / 0.144 / 0.017 |
| Multi-pixel fraction | 0.29 / 0.33 / 0.35 / 0.41 | 0.29 / 0.33 / 0.35 / 0.41 |

Why there is no difference:
- With the Arino-Estrada constants, the hole drift length is μτ_h·E = 1.8e-4 × 5000 ≈ 0.9 cm, much longer than the 0.1–0.2 cm sensor. Holes are barely trapped.
- PulseTransfer integrates the whole 1 µs window, so the induced charge integrates to the collected charge (Shockley–Ramo).

So the hole tail is **not a trapping effect** at these constants. It appears only as **ballistic deficit**: a CR-RC shaping time shorter than the hole transit (~300 ns at 1 mm, ~360 ns at 2 mm).

**Revised plan for the hole tail:** model it in Stage C as an analytic small-pixel Shockley–Ramo induced pulse with CR-RC shaping (TL-01/TL-03). Validate it against a few Allpix runs using TransientPropagation + **CSADigitizer**, which applies a charge-sensitive-amplifier response and should expose per-pixel ToA and amplitude. That check is not done yet. The 1 → 2 mm tail increase seen here (0.10 → 0.14 at 60 keV) comes from fluorescence, escape and sharing, not from hole trapping. This bears on hypothesis L13.


## 4. Standalone Geant4 for custom alloys and scintillator

`simulation/stageA_g4/`:
- `main.cc` (~120 lines), `CMakeLists.txt`, `make_gdml.py`
- It **builds in 7 s** inside the existing Allpix image, so no new image is needed.
- Physics: QGSP_BERT_LIV, 1 µm cut, fluorescence on.

**Transmission** (5 placeholder grades × 5 and 20 mm × 60/100/120/150/300 keV, 1e5 photons each; `spike4_g4_transmission_vs_xcom.csv`):
- **Transport is self-consistent.** Unscattered transmission from the Monte Carlo equals exp(−μ_G4·t) within statistics (worst cell 3.1σ, a 20-count cell).
- **Geant4 μ/ρ vs NIST at grid energies:** ≤0.4% at 100/150/300 keV, but **−1.0% at 60 keV** for all alloys (Livermore EPDL vs XCOM photoelectric).
- **Between grid points** (120 keV): Geant4 is 2.2–3.0% below SpekPy's log-log interpolation and close to xraydb/Elam.

**Scintillator** (NIST CsI and GOS, 2.5 × 2.5 mm, 1e5 photons):

| Stack | Interacting at 60 keV | Interacting at 150 keV | Full-energy at 150 keV |
|---|---|---|---|
| CsI 0.5 mm | 0.83 | 0.14 | 0.10 |
| CsI 2 mm | 1.00 | 0.46 | 0.39 |
| GOS 0.5 mm | 0.97 | 0.28 | 0.19 |
| GOS 2 mm | 1.00 | 0.73 | 0.65 |

K-escape and Compton partial deposits are present (8–25% of events). The per-event deposit list feeds the Python optical model.

Speed: 1e5 photons in ~2–13 s, serial, with the CPU shared. The MT run manager is available.

**Plan change:** none to the architecture; Stage A and B-pd are confirmed feasible. Writing the phase-space file at z = 639 mm is not built yet.

## 5. SpekPy spectra and Beer–Lambert vs XCOM

`spike5_spectra_and_attenuation.py`; outputs in `analysis/protocol/spike5/`. Run time: 7 s.

- **Spectra:** 80/150/225/300 kVp × 0/1/2 mm Cu, 1 keV bins. Tube: W anode, 1 mm Be + 2 mm Al (T-09, tag A); **anode angle 12° (tag A — not stated in either protocol; must be added to T-09)**.
- **Fraction of photons above LINDA's ~199 keV range:** 0.7–2.5% at 225 kVp and **5.5–16%** at 300 kVp. That makes question L7 (what happens above the range) matter for every 300 kVp result.

**Attenuation:**
- SpekPy-NIST and xraydb/Elam agree with the NIST grid values for Cu to ≤0.03% at 60/80/100/150/200/300 keV.
- **Between the 100 and 150 keV grid points they differ by up to 3.4%**, because of interpolation.
- Through 20 mm Cu that becomes **up to 22% in transmission.** 1,667 of 6,025 cells (T > 1e-4) differ by more than 2% between the two sources.

---

## What changes in the plan

1. **`integration_time = 1us`** in every Allpix config. Audit the old campaigns for the 25 ns truncation.
2. **Physics list: QGSP_BERT_LIV**, default cut (PH-09 decided).
3. **Timing: analytic.** Poisson photon arrival times plus TL-07 drift. Pixel-level times from Allpix are not available in readable form.
4. **Induced charge: not needed for integrated charge** at the Arino-Estrada μτ values; identical to the simple model within statistics. Hole tailing becomes a Stage C ballistic-deficit model, checked against a few TransientPropagation + CSADigitizer runs. Full induced-charge matrices are infeasible anyway (60–90× slower).
5. **No parallel containers.** One Allpix run already uses all cores. Revised Stage-B estimate: ~1.4–2.5 ms/event wall at 60–150 keV, so 1e5 events × ~170 energies ≈ **7–12 h per detector configuration**. About 15 configurations ≈ 4–7 days. Reducing this needs either fewer events at energies where statistics are not limiting, or charge_per_step 100 (check that sharing is unchanged).
6. **XCOM reference.** We need actual XCOM output on a 1 keV grid for each alloy; tabulated grid values plus interpolation are not good enough for thick parts. The Exp 0 tolerance "2% on T" should be restated on μ/ρ, or on T only where μt ≤ ~1. A 2% T tolerance at 20 mm is a ~0.5% μ tolerance, tighter than the libraries agree. **Ruling needed.**
7. **Geant4 vs XCOM at 60 keV: −1.0%.** This is inside a 2% μ tolerance but must be recorded as a systematic.

## Blockers

- None that stop the build.
- Item 6 needs a ruling.
- XCOM data must be fetched from the NIST web service. It isn't reachable offline in this repo.
