# Input requests for the LINDA / VAREX / Medipix3 / Sens-Tech simulation study

We are about to run the simulation programme described in the *Comparative Simulation Study Protocol* and the *Simulation Experiment Structure* (both dated 5 November 2026). We do not want to run it on assumptions. Below are the values we still need, grouped by the organisation best placed to answer.

For each question:
- **"Blocks"** says what cannot be computed without the answer.
- Items marked **★** decide rankings. If we receive no answer, those results will be reported as blank, not estimated.
- For every other item we will sweep the stated range and label the result *assumed*.

A partial answer, a datasheet, or "unknown" is useful too. The IDs match `inputs_register.csv`.

---

## 1. IFAE — LINDA / ERICA

> **For Alex to forward:** "Hi — we're simulating LINDA for the Sens-Tech line study and have five quick questions that the papers and the patent don't answer. Rough numbers are fine."

1. **Pulse shaping.** What is the peaking/shaping time, is it adjustable, and is the pulse unipolar or bipolar?
2. **Charge summing.** What coincidence window does the Energy-Sum algorithm (WO2016135106A1) use, if the patent doesn't say? Can summing be switched off?
3. **Counters and TDI.** How many bits per energy bin? Is the 8-row TDI sum read per row or per output line?
4. **Measured data.** Could we have any Am-241/Co-57 spectrum, threshold scan, count-rate curve or edge image? We'd use it only to check our model blind, before tuning anything.
5. **Dead time.** Is the ~1 µs per photon from the summing logic or the front end, and does a pixel stay blind (paralyzable) under continued hits?

Everything else (noise, sensor details, costs) we'll take from your publications or bracket. Corrections are welcome.

## 2. Varex — DC-TDI

| ID | Question | Blocks | If unanswered |
|---|---|---|---|
| V1 ★ | Which model is the benchmark: DC-TDI or DC-THOR? The product page says up to 9 m/s; datasheet Rev. C says 120 m/min single energy and 60 m/min dual energy. Which applies to which model and mode? | Line-speed comparison | datasheet Rev. C |
| V2 ★ | Sensor material (CdTe or CdZnTe) and thickness. | Efficiency, spectra and discrimination for VAREX | 0.75 / 1 / 1.5 / 2 mm |
| V3 | Electronic noise, threshold range, dead time or count-rate curve, charge-sharing handling. | Count-rate behaviour | 50 / 100 / 200 ns |
| V4 | Number of TDI stages, dead edge, pixel gap. | Dead area, line rate | — |
| V5 | Any measured data (spectrum, edge image, count-rate curve). | Validation | — |
| V6 | Indicative module price for our scan width. | Break-even comparison | — |

## 3. Sens-Tech — photodiode detector

Every property of this detector is currently unconfirmed. Without these answers it can only be studied as a range of hypothetical designs.

| ID | Question | If unanswered we sweep |
|---|---|---|
| S1 ★ | Scintillator material and thickness for each energy channel (CsI:Tl, GOS, CdWO₄, …). | CsI and GOS, 0.5 / 1 / 2 / 3 mm |
| S2 ★ | Are the two channels stacked (front/back) or side by side? Material and thickness of any filter between them? | stacked; Cu 0 / 0.5 / 1 mm |
| S3 | Pixel pitch and aperture (we have ≈2.5 mm), number of rows, active length. | 2.5 mm, 1 row |
| S4 | Light yield, optical collection efficiency, photodiode quantum efficiency, optical crosstalk or light spread. | published ranges |
| S5 | Electronic noise (e⁻ rms), ADC bits or full well, integration time. | — |
| S6 | Afterglow / lag specification. | — |
| S7 | Any measured channel response, dark or gain maps. | — |

## 4. Sens-Tech — inspection line and task

These define what "good enough" means. Without them no option can be judged as passing or failing.

| ID | Question |
|---|---|
| T1 ★ | The exact alloy grades, with element mass fractions and density: which brass, which leaded brass (Pb %), which bronze (Sn %), CuNi 90/10 or 70/30. |
| T2 ★ | The smallest defect to detect (void or wire, size, material) and the target SNR or detectability index d′. |
| T3 ★ | Acceptance thresholds: usable SNR through the thickest part, MTF at the defect's spatial frequency, required alloy-pair separation (we propose CNR ≥ 3), maximum count loss (we propose 10%), required line speed or exposure time. |
| T4 | X-ray tube: model, anode angle, inherent filtration, focal spot, maximum mA, ripple; the kVp values and prefilters actually used. |
| T5 ★ | Operating point: tube current and belt speed. These set the photon flux at the detector. |
| T6 | Geometry: source–object and source–detector distances, belt height and material, slits, collimators, housing, cabinet lining, belt supports. The protocol's Table 5 values are placeholders. |
| T7 | Part sizes and the thickness range actually inspected. |

## 5. Project lead

| ID | Question |
|---|---|
| B1 | Budget limits for scenarios B2 and B3; planning horizon; discounting of operating costs. |
| B2 | Cost book: minimum / most-likely / maximum € for each improvement option; loaded engineer rate. |
| B3 | Validation tolerances still marked "to be agreed": multi-pixel-fraction reference, blind-prediction tolerance, threshold-scan tolerance. |
| B4 | Minimum meaningful improvement (proposed 5% of the gap) and weights for the composite score. |
| R1 | **Decided 2026-11-05:** baseline ON, modelled as generic neighbour summing (window, neighbourhood, efficiency bracketed); OFF is scenario L6. |
| R2 | **Decided 2026-11-05:** flux sweeps are open-beam characterisation; operating flux from tube current × spectrum × attenuation, tube current bracketed until T5. |
| R3 | **Decided 2026-11-05:** 48 rows plus emulated TDI for Exp 2/3/7 ("hypothetical line-scan Medipix3"); small patch for Exp 1/4/5. |
