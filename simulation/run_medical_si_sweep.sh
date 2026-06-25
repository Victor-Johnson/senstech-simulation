#!/bin/bash
# =======================================================================
# Medical CT Suitability - Silicon Energy Sweep
# Mirrors the existing CdTe energy sweep (Scenario 1) at identical
# energies, so we get a direct head-to-head CdTe vs Si comparison
# across the full clinical-relevant energy range (20-150 keV).
#
# Silicon uses its own appropriate operating voltage (-100V) rather
# than CdTe's (-500V) - comparing each material at its proper
# operating point, not artificially handicapping either one.
# Chip electronics (noise, threshold) stay identical since those
# are ASIC properties, not material properties.
# =======================================================================

set -e

CONFIGS=/data/simulation/configs
OUTPUT=/data/output
SCENARIOS=$CONFIGS/scenarios

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

# Silicon detector config (default medipix3 sensor material is silicon
# unless sensor_material is explicitly overridden)
cat > $CONFIGS/detector_medipix3_si.conf << 'INNEREOF'
[medipix3_detector]
type = "medipix3"
position = 0 0 0
orientation = 0 0 0
number_of_pixels = 256 256
pixel_size = 55um 55um
sensor_thickness = 300um
INNEREOF

for ENERGY in 20 40 60 80 100 120 150; do

cat > $SCENARIOS/s1_si_${ENERGY}keV.conf << INNEREOF
[Allpix]
log_level = "WARNING"
number_of_events = 10000
detectors_file = "$CONFIGS/detector_medipix3_si.conf"
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
bias_voltage = -100V
depletion_voltage = -50V

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

    run_sim "$SCENARIOS/s1_si_${ENERGY}keV.conf" "s1_si_${ENERGY}keV"
done

echo ""
echo "======================================================="
echo "SILICON ENERGY SWEEP COMPLETE"
echo "======================================================="
ls -lh $OUTPUT/s1_si_*.root 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
