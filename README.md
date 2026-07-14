
# Perovskite X-Ray Detector Feasibility Study
 
> iTEK Industry Collaboration — University of Surrey × Sens Tech  
> Academic Year 2025/26
 
A simulation-driven feasibility study investigating perovskite and CdTe as candidate materials for next-generation photon-counting X-ray detectors. We use Allpix Squared to model detector physics, configure virtual readout chips (Hexitec, Medipix3, Eiger2) from datasheets, and apply Python-based ML pipelines for signal analysis and detector health monitoring.
 
---
 
## Project Overview
 
Current photon-counting X-ray detectors rely on Cadmium Telluride (CdTe) — a high-performance but expensive material. Perovskite semiconductors offer comparable X-ray absorption at significantly lower cost, but face challenges around stability and noise. This project assesses whether perovskite can serve as a viable alternative, and under which conditions.
 
Our approach simulates the full detector chain — from X-ray photon interaction through to digitised pixel output — without requiring physical hardware in the early stages. This allows rapid iteration over material compositions and chip configurations before committing to lab fabrication.
 
### Key Questions
- Which perovskite composition maximises photon capture and minimises noise?
- How do Hexitec, Medipix3 and Eiger2 chips perform when coupled to perovskite vs CdTe (and Si)?
- How does detector performance degrade over time, and can ML detect this automatically?
---
 
## Methodology — 4 Phases
 
```
Phase 1          Phase 2          Phase 3          Phase 4
─────────────    ─────────────    ─────────────    ─────────────
Allpix²      →  Chip Config  →  Python ML    →  Lab Work
Simulation       Hexitec &        Pipeline         Crystal
CdTe vs          Medipix4         Signal           Growth &
Perovskite       from datasheets  Analysis &       CdTe Wafer
materials                         Anomaly Det.     Sourcing
```
 
### Phase 1 — Allpix² Material Simulation
Use [Allpix Squared](https://allpix-squared.docs.cern.ch/) (CERN's open-source semiconductor detector simulation framework) to model X-ray photon interactions with CdTe and various perovskite compositions. Geant4 handles the particle physics; Allpix² handles charge transport and digitisation.
 
### Phase 2 — Chip Configuration
Configure Allpix² to replicate the behaviour of real photon-counting readout ASICs using published datasheets — currently Hexitec (STFC), Medipix3 (CERN) and Eiger2 (Dectris). This produces realistic digitised pixel output matching what a real chip would see.
 
### Phase 3 — Python Analysis & ML Pipeline
Parse Allpix² ROOT output using `uproot`, extract signal spectra, and apply:
- **Isolation Forest** for detector degradation detection
- **Autoencoder** for noise characterisation and reduction
- **Lifetime simulation** via progressive material parameter degradation
### Phase 4 — Lab Material Work
Grow perovskite crystals (CsPbBr₃ / MAPbI₃) via solution processing and source commercial CdTe wafers as a validated benchmark. Real measurements feed back into the simulation for validation.
 
---
 
## Repository Structure

```
.
├── simulation/                   # Mounted into the container at /data/simulation
│   ├── configs/                  # Allpix² detector & geometry configs
│   │   └── scenarios/            # Per-experiment configs (baggage, food,
│   │                             #   chip comparison, material penetration,
│   │                             #   parameter sweeps s1–s8)
│   └── run_*.sh                  # Batch scripts that drive the sweeps
├── analysis/
│   ├── scripts/                  # Analysis pipeline & figure scripts
│   ├── notebooks/
│   │   ├── sweeps/               # Parameter-sweep notebooks (s1–s8, etc.)
│   │   ├── inspection/           # Application notebooks (baggage, food,
│   │                             #   medical, chip comparisons)
│   │   └── images/               # Figures exported from the notebooks
│   ├── results/                  # Generated CSV/PNG results per campaign
│   │   └── material_penetration*/
│   └── reports/                  # Written reports & presentation defenses
├── scripts/
│   └── make_spectrum.py          # Helper to build beam spectra
├── spectra/                      # Source spectra (e.g. 150 kVp weights)
├── notes/                        # Working notes & experiment write-ups
├── data/                         # Allpix² ROOT output (not committed;
│                                 #   mounted into the container at /data/output)
├── docker-compose.yml            # Allpix² container definition
└── requirements.txt              # Python analysis dependencies
```

> **Note:** ROOT files (`.root`) and raw data are excluded from version control due to size. See `data/README.md` for how to regenerate or obtain them.

---

## Getting Set Up

You need two things: **Docker** (the simulation runs inside CERN's official Allpix² container, so you never have to build Geant4 yourself) and **Python 3.11+** (the analysis runs on your host machine, not in the container). WSL2 on Windows works fine — this repo was developed on it.

```bash
# 1. Clone the repo
git clone <repo-url> senstech-simulation
cd senstech-simulation

# 2. Set up the Python analysis environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Start the Allpix² container (first run pulls the image, ~2 GB)
docker compose run allpix bash
```

That's the whole setup. The container drops you into a shell where the `allpix` binary is available. Two folders are shared between your machine and the container:

| On your machine | Inside the container | What it's for |
|---|---|---|
| `simulation/` | `/data/simulation` | configs and run scripts |
| `data/` | `/data/output` | ROOT files the simulation produces |

So anything you edit in `simulation/` is immediately visible in the container, and anything the simulation writes shows up in `data/` on your machine, ready for Python.

> **Note on data:** the `.root` files are not committed (hundreds of MB per sweep). You either regenerate them with the run scripts below, or ask a team member for a copy of `data/`. See `data/README.md`.

---

## Running the Existing Experiments

Inside the container, each experiment has a driver script that generates its configs and runs the whole sweep:

```bash
# inside the container
cd /data
./simulation/run_material_penetration.sh    # 4 detectors × 14 energies
./simulation/run_full_chip_comparison.sh    # Medipix3 vs Eiger2 vs Hexitec
./simulation/run_food_inspection.sh         # contaminant detection scenarios
./simulation/run_baggage_occlusion.sh       # threat detection under clutter
```

Most scripts take environment variables so you can do a quick pass before committing to a full run:

```bash
DRY_RUN=1 ./simulation/run_material_penetration.sh        # generate configs only, run nothing
BARE_EVENTS=1000 ./simulation/run_material_penetration.sh # fewer events = faster, noisier
ONLY_DETECTOR=medipix3 ONLY_ENERGY=60 ./simulation/run_material_penetration.sh
```

Then back on your machine (venv activated), run the analysis:

```bash
python analysis/scripts/material_penetration_experiment.py   # full pipeline: ROOT → CSVs + figures
jupyter lab                                                  # or explore in the notebooks
```

Results land in `analysis/results/<campaign>/` as CSVs and PNGs. The notebooks live in `analysis/notebooks/` — `sweeps/` for the single-parameter studies (s1–s8), `inspection/` for the application scenarios.

---

## Running Your Own Experiment

An Allpix² run is just two config files: a **main config** (source, physics, digitisation) that points at a **detector config** (geometry, material, pixel pitch). The fastest way to make your own is to copy an existing pair and edit:

```bash
# on your machine
cp simulation/configs/scenarios/material_penetration/mp_bare_medipix3_60keV.conf \
   simulation/configs/scenarios/my_test.conf
cp simulation/configs/scenarios/material_penetration/detector_medipix3_bare.conf \
   simulation/configs/scenarios/my_detector.conf
```

Things you'll typically want to change in the main config:

```ini
[Allpix]
number_of_events = 10000          # more events = smoother spectra, longer runs
detectors_file = "/data/simulation/configs/scenarios/my_detector.conf"   # container path!

[DepositionGeant4]
source_energy = 60keV             # beam energy

[DefaultDigitizer]
threshold = 1129e                 # counting threshold in electrons
```

And in the detector config:

```ini
sensor_material = "cadmium_telluride"   # or "silicon", etc.
sensor_thickness = 300um
pixel_size = 55um 55um
```

One gotcha: `detectors_file` must use the **container** path (`/data/simulation/...`), because that's where the config is read.

Then run it:

```bash
# inside the container
cd /data
allpix -c /data/simulation/configs/scenarios/my_test.conf

# Allpix writes its output as modules.root — rename it so it doesn't get overwritten
mv output/modules.root output/my_test_60keV.root
```

The file appears as `data/my_test_60keV.root` on your machine. Have a first look with uproot:

```python
import uproot
f = uproot.open("data/my_test_60keV.root")
f.keys()   # detector histograms: hit maps, charge spectra, cluster sizes...
```

From there, the notebooks in `analysis/notebooks/sweeps/` are good templates for pulling out spectra and hit maps.

If you want a fresh beam spectrum for spectral (rather than monoenergetic) studies, `scripts/make_spectrum.py` rebuilds `spectra/150kvp_weights.csv` from a 150 kVp tungsten tube model — that's what the material-penetration pipeline weights its energies with.

---

## Experiments So Far

| Experiment | Configs / scripts | Analysis |
|---|---|---|
| Parameter sweeps (energy, threshold, bias, temp, pitch, flux, thickness) | `scenarios/s1_*`–`s8_*` | `analysis/notebooks/sweeps/` |
| Three-chip comparison (Medipix3 vs Eiger2 vs Hexitec) | `scenarios/chip_comparison/` | `analysis/reports/three_chip_comparison_report.md` |
| Baggage inspection & occlusion | `scenarios/baggage_inspection/` | `analysis/notebooks/inspection/babbageinspection.ipynb` |
| Food inspection | `scenarios/food_inspection/` | `analysis/notebooks/inspection/food-inspection1.ipynb` |
| Material penetration (alloy discrimination) | `scenarios/material_penetration*/` | `analysis/reports/material_penetration_report.md` |

---
 
## Tech Stack
 
| Tool | Purpose |
|------|---------|
| [Allpix Squared](https://allpix-squared.docs.cern.ch/) | Semiconductor detector simulation |
| [Geant4](https://geant4.web.cern.ch/) | Particle physics engine (via Allpix²) |
| [uproot](https://uproot.readthedocs.io/) | Read ROOT files in Python |
| NumPy / Pandas | Signal data processing |
| Matplotlib | Spectrum and degradation plots |
| scikit-learn | Isolation Forest anomaly detection |
| TensorFlow / Keras | Autoencoder noise reduction |
| Docker | Allpix² containerised environment |