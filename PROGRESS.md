# PROGRESS: protocol programme running log

Newest entries first. Updated after every task. A new session resumes from **Current state** and **Open issues**.
See ROADMAP.md (milestones), `analysis/protocol/inputs_register.csv` (inputs) and `analysis/protocol/experiment_register.md` (experiments).

## Current state (2026-11-05, end of session)

- **Milestone:** M1 done. ROADMAP written; **waiting for user go-ahead before starting M3**.
- **Branch:** `protocol-programme`. The last commit (279d194) is step 0 + feasibility; **everything since is uncommitted**.
- **Background jobs:** none running.
- **Next task:** M3.1, the timing layer + analytic tests (`analysis/protocol/timing.py`, `tests/test_timing.py`).

## How to run things

| Step | Command |
|---|---|
| Stage B generate | `PYTHONPATH=. ./venv/bin/python -m analysis.protocol.stageb generate <campaign>` |
| Stage B run | `docker compose run --rm -T --user 1000:1000 -e HOME=/tmp allpix bash /data/simulation/protocol_runs/stageB/run_list.sh <campaign>` (also writes `_depths.csv` via the C++ reader) |
| Stage B convert | `PYTHONPATH=. ./venv/bin/python -m analysis.protocol.stageb convert <campaign>` |
| Stage B analysis | `analysis/protocol/milestone1.py`, `exp0_v1.py`, `exp0_v1_fwhm.py`, `beam_bell_vs_flat.py` |
| Tests | `./venv/bin/python -m pytest -q` (fast, 1299 pass); `-m slow` nightly |
| Audit | `audit_compare.py`, `audit_headline_ci.py <before_out> <after_out>` |

Rebuild the C++ reader (in the container):

```
g++ -O2 -o /data/output/protocol_runs/bin/mctrack_depths mctrack_depths.cc $(root-config --cflags --libs) -I/usr/local/include -L/usr/local/lib -lAllpixObjects -Wl,-rpath,/usr/local/lib
```

## Run IDs (2026-11-05)

| Campaign | Runs | Notes |
|---|---|---|
| `milestone1` (flat beam, fiducial) | 90 | LINDA 16×16 (fid 4×4), Medipix3 64×64 (fid 16×16), VAREX 32×32 (fid 8×8); 20k events; seed 101; 3,060 s |
| `exp0_v1_am241` | 5 | Medipix3, 50k events, seed 201 (Timepix3 shares it) |
| `exp0_v1_fwhm` | 6 | base / notrap / nofano / ideal / transient / transient_mutau1e-5; seed 301 |
| `milestone1_bellbeam`, `exp0_v1_am241_bellbeam` | | superseded (Allpix rectangle beam is bell-shaped); kept for comparison |
| `data/audit_itime/` | 237 | integration-time re-runs. `mpu_bare_timepix3_cdte_50keV` uses seed 43 (seed 42 hangs). 17 `mpu_transport_*_alloy2` simulated **Cu**: do not use |
| `tests/fixtures/mctrack_fixture_*` | | 300 events, seed 4242 |

## Decisions log

| Date | Decision | Ref |
|---|---|---|
| 11-05 | Flat GPS beam + central fiducial scoring for all Stage B; real-array edges modelled separately at system level; Exp 4 flat field must be uniform | PH-20 |
| 11-05 | CSM noise: 80 e⁻ on every pixel around the seed (empties too), before block choice; block = largest noisy sum (chip-like, default); noiseless choice is diagnostic only | D-M04, PH-22 |
| 11-05 | Medipix3 threshold dispersion 40 e⁻ (A, 20–80) | D-M12 |
| 11-05 | Fano 0.24 used, but **PH-06 conflict stays open** (0.10/0.15/0.24) | PH-06, PH-19 |
| 11-05 | Ballistic deficit not modelled; X0-CSA required; V1 sim peak expected slightly narrow | PH-21 |
| 11-05 | Transient hole runs deferred unless a result depends on μτh = 1e-5 | PH-23 |
| 11-05 | integration_time 1 µs + validation rule; audit done | PH-12 |
| 11-05 | Fast tests on push/PR, slow tests nightly (`.github/workflows/`); no lint/type tooling configured | -- |
| 11-05 | Provisional (tag A) column in every output table | ROADMAP |

## Log

- **2026-11-05**
  - Integration-time audit complete: 237 re-runs, 31 excluded (invalid "before").
    - Ranking change: Medipix3 vs Timepix3 now level (77 ± 763 counts at 95%; was 9,546 ± 778).
    - Note for Alex: `analysis/protocol/audit/alex_integration_time_note.md`.
  - EIGER2 80 keV window traced:
    - it is an analysis mask, chosen by M. Sultana on 07-25 to model the dual-threshold window;
    - with no upper edge EIGER2 ranks 1st;
    - with no upper edge for ANY chip, all three tie at the CdTe ceiling.
    - Output: `audit/eiger2_upper_edge_scenarios.csv`.
  - alloy2 provenance: `audit/alloy2_provenance.md`.
    - Every pre-07-25 alloy2 transport run is G4_BRASS (fingerprinted).
    - The original report (`material_penetration_report.md`/.docx) and `results/material_penetration/table_values.md` label G4_BRASS transport as C36000: **mismatch**.
    - `notes/Material_Penetration_Experiment2_filled.md` is a possible mismatch.
  - Milestone 1 (flat beam) analysed:
    - η within the XCOM ceiling except 70 keV LINDA/Medipix3 (+0.7–0.8%, ~4σ; open issue).
    - The bell beam biased LINDA only (edge loss).
  - LINDA lost vs clip at 225/300 kVp behind CuZn39Pb3 done: `exp2/linda_above_range_bins.csv`.
  - V1 CSM 59.5 keV: 1.84 keV FWHM (noise budget closes).

## Open issues

1. η exceeds the single-pass XCOM ceiling at 70 keV by ~0.8% (LINDA, Medipix3; ~4σ). Hypothesis: backscatter from the ASIC/support in the Allpix `medipix3` model. Explain in M4.
2. 17 `mpu_transport_*_alloy2` configs now simulate Cu under a brass name (shared detector file regenerated 07-25). Fix needs a decision plus chown of root-owned configs.
3. Root-owned `simulation/` and `data/` files: `sudo chown -R victor-pc:victor-pc simulation data` (user to run).
4. `requirements.txt`: the user is resolving local edits; pytest and xraydb are not listed.
5. Stale documents with the alloy2 label mismatch (see provenance note), plus the `_uniform_short_report.md` mention of the removed EIGER2 correction.
6. Untagged `p2_bare_eiger2` originals in `data/` are corrupt. Valid 0.75 mm re-runs exist in `data/audit_itime/`; replacing the originals needs the user's OK.
7. V1 reference spectra, V2/V3 literature, and all partner questionnaires are outstanding (see register MISSING rows).
