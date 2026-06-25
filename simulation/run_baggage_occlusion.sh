#!/bin/bash
# =======================================================================
# Baggage Inspection - Occlusion/Clutter Penetration Test
# Physical model: TWO sequential Beer-Lambert attenuation layers
#   Layer 1: Water-equivalent clutter (NIST data) - proxy for generic
#            bag contents (clothes, books, electronics casings)
#   Layer 2: Steel threat object, 1mm (reusing validated NIST iron
#            data from the food inspection work)
#
# Total transmission = transmission_clutter x transmission_threat
# (Beer-Lambert layers in series multiply)
#
# The "sparse" -> "extreme" labels match the packing-complexity
# language from the baggage metrics list (Category 6: sensitivity
# analysis under increasing packing complexity).
#
# Baseline (no clutter, threat alone in air) already exists from
# the food inspection work:
#   food_contam_40keV_1mm.root, food_contam_60keV_1mm.root,
#   food_contam_80keV_1mm.root
#
# NOTE: 40keV/extreme produces only 3 incident events - essentially
# zero signal penetrates at all. This is itself a valid finding
# (near-total occlusion blocks detection at this energy) but the
# statistics are too sparse for a reliable CNR number.
# =======================================================================

set -e

CONFIGS=/data/simulation/configs
OUTPUT=/data/output
SCENARIOS=$CONFIGS/scenarios/baggage_inspection

mkdir -p $SCENARIOS

run_sim() {
    local config_path=$1
    local output_name=$2
    echo ""
    echo "======================================================="
    echo "Running: $output_name"
    echo "======================================================="
    allpix -c "$config_path" 2>&1 | tail -8
    if [ -f "$OUTPUT/modules.root" ]; then
        mv "$OUTPUT/modules.root" "$OUTPUT/${output_name}.root"
        echo "SAVED: ${output_name}.root"
    else
        echo "FAILED: no output for $output_name"
    fi
}

write_and_run() {
    local energy=$1
    local n_events=$2
    local output_name=$3
    local config_path=$SCENARIOS/${output_name}.conf

cat > $config_path << INNEREOF
[Allpix]
log_level = "WARNING"
number_of_events = ${n_events}
detectors_file = "$CONFIGS/detector_medipix3_cdte.conf"
random_seed = 42

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
physics_list = QGSP_BERT
particle_type = "gamma"
source_energy = ${energy}keV
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
INNEREOF

    run_sim "$config_path" "$output_name"
}

# =======================================================================
# 40 keV - steel threat (1mm) under increasing water-equivalent clutter
# =======================================================================
echo ""
echo "############################################"
echo "# 40 keV - OCCLUSION SWEEP"
echo "############################################"

write_and_run 40 336 "baggage_occl_40keV_sparse"
write_and_run 40 150 "baggage_occl_40keV_medium"
write_and_run 40 39  "baggage_occl_40keV_cluttered"
write_and_run 40 3   "baggage_occl_40keV_extreme"

# =======================================================================
# 60 keV - steel threat (1mm) under increasing water-equivalent clutter
# =======================================================================
echo ""
echo "############################################"
echo "# 60 keV - OCCLUSION SWEEP"
echo "############################################"

write_and_run 60 2566 "baggage_occl_60keV_sparse"
write_and_run 60 1384 "baggage_occl_60keV_medium"
write_and_run 60 494  "baggage_occl_60keV_cluttered"
write_and_run 60 63   "baggage_occl_60keV_extreme"

# =======================================================================
# 80 keV - steel threat (1mm) under increasing water-equivalent clutter
# =======================================================================
echo ""
echo "############################################"
echo "# 80 keV - OCCLUSION SWEEP"
echo "############################################"

write_and_run 80 4335 "baggage_occl_80keV_sparse"
write_and_run 80 2498 "baggage_occl_80keV_medium"
write_and_run 80 997  "baggage_occl_80keV_cluttered"
write_and_run 80 159  "baggage_occl_80keV_extreme"

# =======================================================================
# Summary
# =======================================================================
echo ""
echo "======================================================="
echo "BAGGAGE OCCLUSION SWEEP COMPLETE"
echo "======================================================="
echo ""
echo "Baseline (no clutter) files - already exist from food inspection:"
echo "  food_contam_40keV_1mm.root, food_contam_60keV_1mm.root, food_contam_80keV_1mm.root"
echo ""
echo "New occlusion files:"
ls -lh $OUTPUT/baggage_occl_*.root 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
echo ""
echo "Total new ROOT files:"
ls $OUTPUT/baggage_occl_*.root 2>/dev/null | wc -l
