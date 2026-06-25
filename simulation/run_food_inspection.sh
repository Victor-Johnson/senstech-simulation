#!/bin/bash
# ─────────────────────────────────────────────────────────────────────
# Food Inspection — Metal Contaminant Detection Simulation
# Physical model: Beer-Lambert attenuation (NIST data) + Allpix² detector response
#
# We do NOT simulate the contaminant object directly (Allpix² has no
# upstream object/phantom support). Instead:
#   1. Steel attenuation calculated analytically from NIST mass
#      attenuation coefficients for iron at each energy
#   2. The resulting transmission fraction sets number_of_events for
#      the "contaminant present" simulation — fewer photons reach the
#      detector because the metal absorbed/scattered the rest
#   3. The detector's response to that reduced flux is what Allpix²
#      actually simulates — this is the part Allpix² is good at
#
# Background (clean food) reuses existing Scenario 1 energy sweep files:
#   s1_cdte_40keV.root, s1_cdte_60keV.root, s1_cdte_80keV.root
# ─────────────────────────────────────────────────────────────────────

set -e

CONFIGS=/data/simulation/configs
OUTPUT=/data/output
SCENARIOS=$CONFIGS/scenarios/food_inspection

mkdir -p $SCENARIOS

run_sim() {
    local config_path=$1
    local output_name=$2
    echo ""
    echo "════════════════════════════════════════════════════"
    echo "Running: $output_name"
    echo "════════════════════════════════════════════════════"
    allpix -c "$config_path" 2>&1 | tail -8
    if [ -f "$OUTPUT/modules.root" ]; then
        mv "$OUTPUT/modules.root" "$OUTPUT/${output_name}.root"
        echo "✓ Saved: ${output_name}.root"
    else
        echo "✗ FAILED: no output for $output_name"
    fi
}

# ─────────────────────────────────────────────────────────────────────
# Steel contaminant — transmission-adjusted event counts
# Calculated from NIST iron mass attenuation coefficients
# (Steel density 7.87 g/cm³; values rounded from exact calculation)
# ─────────────────────────────────────────────────────────────────────

declare -A N_EVENTS
N_EVENTS["40_0p5mm"]=2398
N_EVENTS["40_1mm"]=575
N_EVENTS["40_2mm"]=33
N_EVENTS["60_0p5mm"]=6224
N_EVENTS["60_1mm"]=3874
N_EVENTS["60_2mm"]=1501
N_EVENTS["80_0p5mm"]=7912
N_EVENTS["80_1mm"]=6260
N_EVENTS["80_2mm"]=3919

for ENERGY in 40 60 80; do
    for THICK in 0p5mm 1mm 2mm; do

        KEY="${ENERGY}_${THICK}"
        N=${N_EVENTS[$KEY]}

cat > $SCENARIOS/food_contam_${ENERGY}keV_${THICK}.conf << INNER_EOF
[Allpix]
log_level = "WARNING"
number_of_events = ${N}
detectors_file = "$CONFIGS/detector_medipix3_cdte.conf"
random_seed = 42

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
physics_list = QGSP_BERT
particle_type = "gamma"
source_energy = ${ENERGY}keV
source_type = "beam"
beam_size = 1mm
beam_direction = 0 0 1
source_position = 0 0 -1cm
number_of_particles = 1

[ElectricFieldReader]
model = "linear"
bias_voltage = -500V
depletion_voltage = -300V

[GenericPropagation]
temperature = 293K
charge_per_step = 10
mobility_model = "jacoboni"

[SimpleTransfer]
max_depth_distance = 5um

[DefaultDigitizer]
electronics_noise = 80e
threshold = 700e
threshold_smearing = 35e

[DetectorHistogrammer]
INNER_EOF

        run_sim "$SCENARIOS/food_contam_${ENERGY}keV_${THICK}.conf" \
                "food_contam_${ENERGY}keV_${THICK}"
    done
done

echo ""
echo "════════════════════════════════════════════════════"
echo "FOOD INSPECTION CONTAMINANT SIMS COMPLETE"
echo "════════════════════════════════════════════════════"
echo ""
echo "Background (clean) files — already exist from Scenario 1:"
echo "  s1_cdte_40keV.root, s1_cdte_60keV.root, s1_cdte_80keV.root"
echo ""
echo "New contaminant files:"
ls -lh $OUTPUT/food_contam_*.root 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
