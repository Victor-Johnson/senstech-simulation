# Integration-time fix: what changed (for Alex)

**With all upper energy edges removed, the three chips are indistinguishable; the old ranking reflects the energy windows, not detector physics.** In the uniform 1 mm CdTe study, removing every upper edge gives Medipix3 92,239, Timepix3 92,668 and EIGER2 92,542 counts (95% CI ±558 each), all at the CdTe absorption limit.

**Within the current windows, fixing a simulation setting also changed the ranking: Medipix3 and Timepix3 are now level, and EIGER2 is still last.** Before the fix, Medipix3 led Timepix3 by 9,546 counts (±778). After it, the gap is 77 ± 763, so the two are level within simulation statistics. The cause: Allpix stops following the sensor charge after 25 ns by default, but electrons in 1 mm CdTe at −300 V to −400 V need about 26–32 ns to cross the sensor. Some charge was cut off, which hit Timepix3 (−300 V) hardest. We re-ran every affected configuration with 1 µs. Only configurations with a crossing time over 25 ns changed: 94 of 94 such runs with counts. None of the 99 faster runs changed, including EIGER2 at 0.75 mm and −375 V.

**EIGER2 sensitivity (old campaign only; EIGER2 is not in the new protocol).** EIGER2's place depends on how photons above 80 keV are treated. Rejected (the 4–80 keV two-threshold window, current): 36,637 ± 407, last. Counted (single-threshold mode, no upper edge): 92,542 ± 558, first, ahead of Medipix3 by 8,005 ± 777. No ruling is made on which mode applies; both are reported.

| Uniform 1 mm study, total counts (5 alloys, 10⁶ photons each) | Before (25 ns) | After (1 µs) | Change |
|---|---|---|---|
| Medipix3 | 81,072 ± 546 | 84,537 ± 540 | +4.3% |
| Timepix3 | 71,527 ± 553 | 84,459 ± 539 | +18.1% |
| EIGER2 (4–80 keV window) | 37,655 ± 416 | 36,637 ± 407 | −2.7% |
| Medipix3 − Timepix3 | 9,546 ± 778 (significant) | 77 ± 763 (level) | |

± = 95% CI from simulation statistics. Totals are expected counts, so a real measurement would add its own counting noise.

Caveat found on 2026-11-05: the simulated CdTe has density 6.2 g/cm³ (Geant4's G4_CADMIUM_TELLURIDE) instead of the real 5.85. This raises absolute efficiency by about 1% at 70 keV and up to about 6% at 300 keV for every chip alike, so rankings are unaffected but absolute counts are slightly high. A fix is pending a ruling.

**Scope (237 configurations re-run):**

| Campaign | Re-run | Crossing > 25 ns | Changed | Notes |
|---|---|---|---|---|
| Material penetration, uniform 1 mm | 101 | 84 | 72 | The other 12 have zero counts (fully absorbed behind copper). 17 alloy2 transport runs excluded: their detector file was switched to copper in July, so "before" and "after" simulate different metals. |
| Material penetration, original thicknesses | 62 | 17 | 16 | Timepix3 1 mm only; 1 run has zero counts |
| Phase 2 selection | 44 | 6 | 6 | Only the EIGER2 1 mm CdTe variants (+7–10% at 80–150 keV). The 0.75 mm runs used in Table 10 are unchanged. 14 untagged EIGER2 runs excluded (known-bad old files). |
| Chip comparison, scenarios, configs | 30 | 0 | 0 | all unchanged |

Per-run detail is in `integration_time_before_after.csv` and per-group detail in `integration_time_before_after_by_campaign.csv` (both in `analysis/protocol/audit/`).
