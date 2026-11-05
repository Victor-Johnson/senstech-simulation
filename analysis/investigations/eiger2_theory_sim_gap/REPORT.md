# EIGER2 theory-vs-simulation gap — investigation

> **CORRECTION (2026-09-26).** The mechanism attribution below is incomplete.
> This report inferred Compton scattering from kinematics and consistency, with
> no per-event interaction records — none existed at the time. Those records have
> since been produced (`analysis/investigations/claim_confirmation/`, item 5),
> and they show the sub-80 keV deposits come from **two** routes, not one:
> **CdTe K-fluorescence escape** (a photoelectric absorption in which a ~25 keV
> Cd/Te K X-ray leaves the sensor) and Compton scattering. Weighted by each
> energy's actual contribution to the gap, the split is **≈55% fluorescence
> escape / ≈45% Compton**. Fluorescence escape dominates at 90–100 keV (74% /
> 61% of in-window events), which is where most of the excess counts come from;
> Compton dominates only at 120–150 keV, where the hardened beam is weakest,
> because E−25 keV no longer lands inside the 4–80 keV window there.
> The overall conclusion — that the gap is a real physical effect arising from
> deposited-vs-photon-energy windowing, not a counting bug — is unchanged and is
> now supported by interaction records rather than inference.

**Question.** Table 10 (native scenario, EIGER2 at its commercial 0.75 mm) reports
N_theory = 3,463, N_sim = 6,372 — a **+90.7% gap**, by far the largest of the six chips. Is this
a counting bug (double-counting, unit mismatch, a scaling factor applied twice) or a real
physical effect?

**Answer, upfront: it is a real physical effect, not a bug.** It is fully and quantitatively
explained by the difference between how the theory model and the simulation define "counted":
theory cuts on the photon's *original* energy; the simulation counts *deposited* energy. For a
narrow-window chip on a beam hardened to ~105 keV mean, that difference is large. No step in the
pipeline double-counts, mis-scales, or applies a factor twice — each of those hypotheses was
tested directly against the ROOT data and ruled out below.

Reproduce with: `PYTHONPATH=. ./venv/bin/python analysis/investigations/eiger2_theory_sim_gap/investigate.py`

---

## Stage-by-stage counts

Allpix's `DetectorHistogrammer` module saves only histograms, no per-event tree, so an exact
"fired → reaches detector → interacts → passes threshold → registered hits → reported" trace
isn't recoverable event-by-event. The stages available on disk:

| stage | what backs it | EIGER2 @ 100 keV |
|---|---|--:|
| fired | `number_of_events` in the per-run `.conf` | 10,000 |
| interacted (lower bound) | `charge/total_charge` histogram entries | 10,000 |
| detected events (≥1 cluster) | `event_size_clusters` sum of bin *heights* | 5,255 |
| total clusters | `charge/cluster_charge` histogram entries | 6,125 |
| clusters in the 4–80 keV window | same histogram, energy-masked | 2,139 |
| reported (production formula) | `bare_windowed_response(...) × fired` | 1,835 |

Full table for all 14 energies × 4 detectors (EIGER2 plus three wide-window controls) is in
[`stage_counts.csv`](stage_counts.csv).

**Note on "interacted":** `total_charge` entries equal `fired` at every energy shown — every
event contributes charge, which just says *nearly all* photons deposit *some* energy; it doesn't
distinguish full absorption from a stray Compton kick. It's a lower bound, stated as one, not
treated as more than it is.

---

## 1. Does one photon get counted as two "detected photons"?

Checked directly against the histogram's own axis, not assumed. `event_size_clusters`'
`fEntries` member is exactly 10,000 = the fired count, confirming the histogram is filled once
per event. But `sum(bin heights) = 5,255 < 10,000`, because the x-axis starts at 1 cluster —
**zero-cluster events fill no bin at all**. So the sum already counts *events*, not clusters.

Cross-check: reading the per-event cluster-count distribution off that same histogram's x-axis
(1 → 4,417 events, 2 → 806, 3 → 32) and multiplying out gives 4,417×1 + 806×2 + 32×3 = 6,125
clusters — which matches `cluster_charge`'s own entry count (6,125) exactly. The event/cluster
split is internally self-consistent. One incident photon that splits its charge across two
pixels is *not* reported as two detected photons at this stage — [`semantics_check.csv`](semantics_check.csv).

## 2. Is there a unit-mixing bug in the window formula?

The production formula (`phase2_selection_experiment.bare_windowed_response`) computes

```
result = N_det × (W / C)
```

where `N_det` = detected *events*, `C` = total *clusters*, `W` = clusters in-window. This does
mix an event-level fraction with a cluster-level one, which is worth being precise about. Bounded
it directly: for any way `W` in-window clusters could be distributed among `N_det` events,

```
lower = max(0, W − (C − N_det))          upper = min(N_det, W)
```

Checked at every energy — **the formula never exceeds `upper`** (algebraically guaranteed, since
`N_det·(W/C) ≤ min(N_det, W)` whenever `C ≥ N_det`, which always holds). So this is not a
double-counting bug: it cannot produce more "detected-in-window" counts than are physically
achievable under any assignment. Where the bound has slack (up to ~1,100 counts at 80 keV), the
formula sits near the *lower* bound, not the upper — i.e. any imprecision here is conservative,
not inflationary, and works against the excess rather than for it —
[`formula_bounds.csv`](formula_bounds.csv).

## 3. Is EIGER2 double-clustering more than other chips (charge-sharing bug)?

No — the opposite. EIGER2's multiplicity (clusters per detected event) is **lower** than
Medipix3's and Timepix4's at every single energy (e.g. at 100 keV: EIGER2 1.166, Medipix3 1.233,
Timepix4 1.238). If charge-sharing double-counting were driving EIGER2's gap, its multiplicity
would need to be *higher*, not lower — [`multiplicity_by_energy.csv`](multiplicity_by_energy.csv).

## 4. Units, geometry, scaling — is N0 or a chip-specific factor applied twice?

Checked the actual per-run `.conf` on disk
(`simulation/configs/scenarios/phase2_selection/p2_bare_eiger2_075mm_100keV.conf`):
`number_of_particles = 1` (no pileup), single `random_seed = 42`, one `DefaultDigitizer` block.
No dead-time, retrigger, or count-rate correction is implemented anywhere in *any* detector's
config — grepped every `.conf` in the campaign for `retrigger|dead_time|count_rate|pile`: zero
hits. So this is a modelling limitation shared identically by all six chips, not something applied
to EIGER2 only, and it can't explain a gap that is unique to EIGER2. The N₀ = 1,000,000 scaling
and spectrum weights are applied identically for every detector in
`phase2_selection_experiment.build_table()`; nothing chip-specific is folded into that scale
factor.

## 5. Detector settings: threshold, noise, bias

EIGER2's config: `threshold = 903e`, `electronics_noise = 107e`, `bias_voltage = -375V`. The
threshold in keV (4.00 keV) sits *below* the window's own lower edge (also 4.00 keV by design),
so it isn't the source of the high-energy excess — the excess is entirely at 90–150 keV beam
energy, far from the threshold's operating point.

## 6. Stripped-down test — is the excess physically required, or coincidental?

A live re-run with scattering disabled wasn't done (would need a Geant4 physics-list change and
a container run); instead the physics was checked analytically, which is decisive on its own.
Compton kinematics: the maximum electron recoil energy from a single scatter is

```
T_max(E) = 2E² / (mₑc² + 2E),   mₑc² = 511 keV
```

| beam energy | Compton edge | below EIGER2's 80 keV upper edge? |
|--:|--:|:--:|
| 90 keV | 23.4 keV | yes |
| 100 keV | 28.1 keV | yes |
| 120 keV | 38.4 keV | yes |
| 150 keV | 55.5 keV | yes |

For **every** beam energy above EIGER2's window, a single Compton scatter's maximum possible
deposit is comfortably below 80 keV. A 90–150 keV photon depositing <80 keV via one scatter isn't
a rare coincidence the simulation happens to catch — it is the *only* kinematically allowed
outcome of that interaction. The physical mechanism is not just plausible, it's guaranteed —
[`compton_edge_check.csv`](compton_edge_check.csv).

---

## Full decomposition (matches Table 10 exactly)

Spectrum-weighted, averaged over all 5 alloys, exactly as `phase2_selection_experiment.py`
computes it — [`gap_decomposition.csv`](gap_decomposition.csv):

| beam energy | in theory's window? | theory contrib. | sim contrib. | excess |
|--:|:--:|--:|--:|--:|
| ≤70 keV | yes | 1,498 | 1,515 | +17 |
| **80 keV** | yes | 1,965 | 1,572 | **−393** |
| **90–150 keV** | **no** | **0** | **3,285** | **+3,285** |
| **total** | | **3,463** | **6,372** | **+2,909** |

Two effects, opposite signs, netting the observed gap:

- **+3,285 (113% of the total excess) comes from 90–150 keV** — beam energies the theory model
  excludes *entirely* via its hard photon-energy step-cut, but which the simulation legitimately
  registers via the Compton mechanism above.
- **−393 at 80 keV specifically** — the simulation actually *undercounts* relative to theory's
  raw `P_CdTe` absorption probability here, because real threshold and charge-sharing losses (which
  the theory model, a pure interaction-probability calculation, doesn't represent) reduce the
  effective detection efficiency below the physical ceiling. This is the expected direction for a
  more realistic model, not an anomaly.

Net: +2,909, matching Table 10's 3,463 → 6,372 to the count.

---

## Conclusion

Every mechanism on the checklist was tested against real data and ruled out as the driver:
- No double-counting (histogram semantics verified directly; formula is mathematically bounded
  and sits conservative, not inflated).
- Not a charge-sharing/multiplicity artifact (EIGER2's multiplicity is *lower* than controls).
- Not a scaling or units bug (N₀, weights, seed, particle count all identical across chips;
  no dead-time/retrigger modelled anywhere, so it can't explain a chip-specific effect).
- Not a threshold misconfiguration (903 e⁻ / 4 keV sits at the window's own lower edge, nowhere
  near the 90–150 keV region where the excess lives).

What remains, and fully accounts for the number: EIGER2's **window is applied to deposited energy
in the simulation but to photon energy in the theory model**, and on a beam hardened to ~105 keV
mean, that distinction is worth 113% of EIGER2's gap. The routes by which a 90–150 keV photon
deposits under 80 keV are **K-fluorescence escape (~55%) and Compton scattering (~45%)** — see the
correction at the top; the Compton-only attribution originally given here was incomplete. This matches (and now
quantitatively grounds) the finding already on record in
`analysis/results/phase2_selection_framework/README.md §4`.

**What this does *not* mean:** it doesn't mean EIGER2's real-world count would match N_sim rather
than N_theory. Which one is closer to reality depends on whether EIGER2 is actually operated in
single-threshold or windowed-discriminator mode — the open question already flagged for vendor
follow-up in the handover document (§6, §8).
