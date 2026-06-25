#!/bin/bash
# =======================================================================
# Food Inspection - All Materials Contaminant Detection Simulation
# Physical model: Beer-Lambert attenuation (NIST data) + Allpix2 detector
#
# Covers three materials spanning the detectability spectrum:
#   STEEL - easiest to detect (high Z, high density)
#   GLASS - moderate, needs realistic fragment size to show contrast
#   BONE  - hardest to detect (low Z relative to steel, needs thick fragments)
#
# Background (clean food) reuses existing Scenario 1 energy sweep files:
#   s1_cdte_40keV.root, s1_cdte_60keV.root, s1_cdte_80keV.root
#
# All attenuation values calculated from NIST mass attenuation
# coefficients - see comments above each material block for sources.
# =======================================================================

set -e

CONFIGS=/data/simulation/configs
OUTPUT=/data/output
SCENARIOS=$CONFIGS/scenarios/food_inspection

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
# MATERIAL 1: STEEL (iron proxy)
# NIST mass attenuation coefficients for iron, density 7.87 g/cm3
# Thicknesses: 0.5mm, 1mm, 2mm (thin - steel is highly attenuating)
# =======================================================================
echo ""
echo "############################################"
echo "# MATERIAL 1: STEEL"
echo "############################################"

write_and_run 40 2398 "food_contam_40keV_0p5mm"
write_and_run 40 575  "food_contam_40keV_1mm"
write_and_run 40 33   "food_contam_40keV_2mm"
write_and_run 60 6224 "food_contam_60keV_0p5mm"
write_and_run 60 3874 "food_contam_60keV_1mm"
write_and_run 60 1501 "food_contam_60keV_2mm"
write_and_run 80 7912 "food_contam_80keV_0p5mm"
write_and_run 80 6260 "food_contam_80keV_1mm"
write_and_run 80 3919 "food_contam_80keV_2mm"

# =======================================================================
# MATERIAL 2: BONE (Cortical bone, ICRU-44)
# NIST mass attenuation coefficients for bone, density 1.92 g/cm3
# Thicknesses: 2mm, 5mm, 10mm (thick - bone barely attenuates)
# =======================================================================
echo ""
echo "############################################"
echo "# MATERIAL 2: BONE"
echo "############################################"

write_and_run 40 7745 "food_bone_40keV_2mm"
write_and_run 40 5279 "food_bone_40keV_5mm"
write_and_run 40 2787 "food_bone_40keV_10mm"
write_and_run 60 8861 "food_bone_60keV_2mm"
write_and_run 60 7392 "food_bone_60keV_5mm"
write_and_run 60 5464 "food_bone_60keV_10mm"
write_and_run 80 9180 "food_bone_80keV_2mm"
write_and_run 80 8074 "food_bone_80keV_5mm"
write_and_run 80 6518 "food_bone_80keV_10mm"

# =======================================================================
# MATERIAL 3: GLASS (Borosilicate proxy for food packaging glass)
# NIST mass attenuation coefficients for borosilicate, density 2.23 g/cm3
# Thicknesses: 1mm, 2mm, 5mm (moderate - realistic glass shard sizes)
# =======================================================================
echo ""
echo "############################################"
echo "# MATERIAL 3: GLASS"
echo "############################################"

write_and_run 40 9077 "food_glass_40keV_1mm"
write_and_run 40 8240 "food_glass_40keV_2mm"
write_and_run 40 6163 "food_glass_40keV_5mm"
write_and_run 60 9475 "food_glass_60keV_1mm"
write_and_run 60 8978 "food_glass_60keV_2mm"
write_and_run 60 7638 "food_glass_60keV_5mm"
write_and_run 80 9587 "food_glass_80keV_1mm"
write_and_run 80 9192 "food_glass_80keV_2mm"
write_and_run 80 8100 "food_glass_80keV_5mm"

# =======================================================================
# Summary
# =======================================================================
echo ""
echo "======================================================="
echo "ALL MATERIALS COMPLETE"
echo "======================================================="
echo ""
echo "Background (clean) files - already exist from Scenario 1:"
echo "  s1_cdte_40keV.root, s1_cdte_60keV.root, s1_cdte_80keV.root"
echo ""
echo "Steel files:"
ls -lh $OUTPUT/food_contam_*.root 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
echo ""
echo "Bone files:"
ls -lh $OUTPUT/food_bone_*.root 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
echo ""
echo "Glass files:"
ls -lh $OUTPUT/food_glass_*.root 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
echo ""
echo "Total new ROOT files:"
ls $OUTPUT/food_contam_*.root $OUTPUT/food_bone_*.root $OUTPUT/food_glass_*.root 2>/dev/null | wc -l
