
# Perovskite X-Ray Detector Feasibility Study
 
> iTEK Industry Collaboration — University of Surrey × Sens Tech  
> Academic Year 2025/26
 
A simulation-driven feasibility study investigating perovskite and CdTe as candidate materials for next-generation photon-counting X-ray detectors. We use Allpix Squared to model detector physics, configure virtual Hexitec and Medipix4 readout chips from datasheets, and apply Python-based ML pipelines for signal analysis and detector health monitoring.
 
---
 
## Project Overview
 
Current photon-counting X-ray detectors rely on Cadmium Telluride (CdTe) — a high-performance but expensive material. Perovskite semiconductors offer comparable X-ray absorption at significantly lower cost, but face challenges around stability and noise. This project assesses whether perovskite can serve as a viable alternative, and under which conditions.
 
Our approach simulates the full detector chain — from X-ray photon interaction through to digitised pixel output — without requiring physical hardware in the early stages. This allows rapid iteration over material compositions and chip configurations before committing to lab fabrication.
 
### Key Questions
- Which perovskite composition maximises photon capture and minimises noise?
- How do Hexitec and Medipix4 chips perform when coupled to perovskite vs CdTe?
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
Configure Allpix² to replicate the behaviour of the Hexitec (STFC) and Medipix4 (CERN) readout ASICs using published datasheets. This produces realistic digitised pixel output matching what a real chip would see.
 
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
├── simulation/
│   ├── configs/          # Allpix² detector and geometry config files
│   ├── materials/        # Custom material property definitions
│   └── scripts/          # Automation scripts for simulation sweeps
├── analysis/
│   ├── notebooks/        # Jupyter notebooks for signal analysis
│   ├── pipeline/         # Python modules: ingestion, processing, ML
│   └── plots/            # Output figures (generated, not committed)
├── data/
│   └── README.md         # Data access instructions (files not committed)
├── docs/
│   ├── references/       # Key papers and datasheets
│   └── meeting-notes/    # Project meeting logs
└── reports/              # Interim and final deliverables
```
 
> **Note:** ROOT files (`.root`) and raw data are excluded from version control due to size. See `data/README.md` for access instructions.
 
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