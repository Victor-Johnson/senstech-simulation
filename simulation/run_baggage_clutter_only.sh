#!/bin/bash
# =======================================================================
# Baggage Inspection - Clutter-ONLY Reference Baseline (no threat)
# Fixes a methodology bug: the original occlusion test compared
# clutter+threat against a totally clean/unoccluded background,
# which made MORE clutter look MORE detectable (wrong). The correct
# comparison is clutter+threat vs clutter-alone AT THE SAME THICKNESS.
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

# Clutter-alone transmission (water-equivalent, no steel threat)
echo ""
echo "############################################"
echo "# CLUTTER-ALONE REFERENCE - 40 keV"
echo "############################################"
write_and_run 40 5847 "baggage_clutteronly_40keV_sparse"
write_and_run 40 2614 "baggage_clutteronly_40keV_medium"
write_and_run 40 684  "baggage_clutteronly_40keV_cluttered"
write_and_run 40 47   "baggage_clutteronly_40keV_extreme"

echo ""
echo "############################################"
echo "# CLUTTER-ALONE REFERENCE - 60 keV"
echo "############################################"
write_and_run 60 6627 "baggage_clutteronly_60keV_sparse"
write_and_run 60 3572 "baggage_clutteronly_60keV_medium"
write_and_run 60 1276 "baggage_clutteronly_60keV_cluttered"
write_and_run 60 163  "baggage_clutteronly_60keV_extreme"

echo ""
echo "############################################"
echo "# CLUTTER-ALONE REFERENCE - 80 keV"
echo "############################################"
write_and_run 80 6927 "baggage_clutteronly_80keV_sparse"
write_and_run 80 3993 "baggage_clutteronly_80keV_medium"
write_and_run 80 1594 "baggage_clutteronly_80keV_cluttered"
write_and_run 80 254  "baggage_clutteronly_80keV_extreme"

echo ""
echo "======================================================="
echo "CLUTTER-ONLY REFERENCE COMPLETE"
echo "======================================================="
ls -lh $OUTPUT/baggage_clutteronly_*.root 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
