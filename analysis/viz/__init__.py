"""Reproducible per-run visualization pipeline for the Allpix2 simulation study.

Layer map
---------
registry    filename <-> RunKey, both directions. THE source of truth for what
            a run is called and where its files live.
runreader   ROOT -> RunData: every histogram, class-dispatched, no exceptions
            for TProfile/TProfile2D.
provenance  what produced a run, how much of that is recorded vs reconstructed.
manifest    run-manifest schema v1/v2 read + merge.
quantities  Quantity/QRef: a number that carries its formula, inputs and origins.

Nothing here mutates global matplotlib state, and nothing here imports the
existing figure scripts. It may import material_penetration_experiment as a
library (constants, binomial_se) so the pages and the CSVs cannot diverge.
"""

__version__ = "0.1.0"
