#!/bin/bash
# ─────────────────────────────────────────────────────────────────────
# 8-Scenario Simulation Batch — Medipix3 + CdTe
# Run inside the Allpix² container at /data
# Each scenario writes to its own uniquely named ROOT file
# ─────────────────────────────────────────────────────────────────────

set -e  # exit on error

CONFIGS=/data/simulation/configs
OUTPUT=/data/output
SCENARIOS=$CONFIGS/scenarios

mkdir -p $SCENARIOS
mkdir -p $OUTPUT

# ─────────────────────────────────────────────────────────────────────
# Helper function — runs a config and renames output
# ─────────────────────────────────────────────────────────────────────
run_sim() {
    local config_path=$1
    local output_name=$2
    echo ""
    echo "════════════════════════════════════════════════════"
    echo "Running: $output_name"
    echo "Config:  $config_path"
    echo "════════════════════════════════════════════════════"
    allpix -c "$config_path" 2>&1 | tail -20
    if [ -f "$OUTPUT/modules.root" ]; then
        mv "$OUTPUT/modules.root" "$OUTPUT/${output_name}.root"
        echo "✓ Saved: ${output_name}.root"
    else
        echo "✗ FAILED: no output file generated for $output_name"
    fi
}

# ─────────────────────────────────────────────────────────────────────
# Base detector config — CdTe on Medipix3
# ─────────────────────────────────────────────────────────────────────
cat > $CONFIGS/detector_medipix3_cdte.conf << 'EOF'
[medipix3_detector]
type = "medipix3"
position = 0 0 0
orientation = 0 0 0
number_of_pixels = 256 256
pixel_size = 55um 55um
sensor_thickness = 300um
sensor_material = "cadmium_telluride"
EOF

# ─────────────────────────────────────────────────────────────────────
# SCENARIO 1 — Energy Sweep (CdTe at 7 energies)
# Maps industry-relevant energy ranges
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▓▓▓ SCENARIO 1: Energy Sweep (CdTe) ▓▓▓"

for ENERGY in 20 40 60 80 100 120 150; do
cat > $SCENARIOS/s1_energy_${ENERGY}keV.conf << EOF
[Allpix]
log_level = "WARNING"
number_of_events = 10000
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
EOF
    run_sim "$SCENARIOS/s1_energy_${ENERGY}keV.conf" "s1_cdte_${ENERGY}keV"
done

# ─────────────────────────────────────────────────────────────────────
# SCENARIO 2 — Degradation Lifecycle (CdTe over time)
# Note: CdTe degrades slowly. We simulate radiation damage by
# enabling SRH recombination with progressively worse lifetimes
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▓▓▓ SCENARIO 2: Degradation Lifecycle ▓▓▓"

declare -A STAGES=(
    ["fresh"]="10000"
    ["3months"]="5000"
    ["6months"]="2000"
    ["1year"]="1000"
    ["2years"]="500"
    ["3years"]="200"
)

for STAGE in fresh 3months 6months 1year 2years 3years; do
    LIFETIME=${STAGES[$STAGE]}
cat > $SCENARIOS/s2_degradation_${STAGE}.conf << EOF
[Allpix]
log_level = "WARNING"
number_of_events = 10000
detectors_file = "$CONFIGS/detector_medipix3_cdte.conf"
random_seed = 42

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
physics_list = QGSP_BERT
particle_type = "gamma"
source_energy = 60keV
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
recombination_model = "srh"
trapping_model = "constant"
trapping_time_electrons = ${LIFETIME}ns
trapping_time_holes = ${LIFETIME}ns

[SimpleTransfer]
max_depth_distance = 5um

[DefaultDigitizer]
electronics_noise = 80e
threshold = 700e
threshold_smearing = 35e

[DetectorHistogrammer]
EOF
    run_sim "$SCENARIOS/s2_degradation_${STAGE}.conf" "s2_cdte_${STAGE}"
done

# ─────────────────────────────────────────────────────────────────────
# SCENARIO 3 — Threshold Sweep (CdTe at 60keV)
# Finds the noise vs sensitivity sweet spot
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▓▓▓ SCENARIO 3: Threshold Sweep ▓▓▓"

for THRESH in 300 500 700 1000 1500 2000; do
cat > $SCENARIOS/s3_threshold_${THRESH}e.conf << EOF
[Allpix]
log_level = "WARNING"
number_of_events = 10000
detectors_file = "$CONFIGS/detector_medipix3_cdte.conf"
random_seed = 42

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
physics_list = QGSP_BERT
particle_type = "gamma"
source_energy = 60keV
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
threshold = ${THRESH}e
threshold_smearing = 35e

[DetectorHistogrammer]
EOF
    run_sim "$SCENARIOS/s3_threshold_${THRESH}e.conf" "s3_cdte_thresh${THRESH}e"
done

# ─────────────────────────────────────────────────────────────────────
# SCENARIO 4 — Bias Voltage Sensitivity
# Operating voltage window analysis
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▓▓▓ SCENARIO 4: Bias Voltage Sweep ▓▓▓"

for VOLTAGE in 100 200 300 500 700 1000; do
    DEPLETION=$((VOLTAGE * 60 / 100))
cat > $SCENARIOS/s4_bias_${VOLTAGE}V.conf << EOF
[Allpix]
log_level = "WARNING"
number_of_events = 10000
detectors_file = "$CONFIGS/detector_medipix3_cdte.conf"
random_seed = 42

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
physics_list = QGSP_BERT
particle_type = "gamma"
source_energy = 60keV
source_type = "beam"
beam_size = 1mm
beam_direction = 0 0 1
source_position = 0 0 -1cm
number_of_particles = 1

[ElectricFieldReader]
model = "linear"
bias_voltage = -${VOLTAGE}V
depletion_voltage = -${DEPLETION}V

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
EOF
    run_sim "$SCENARIOS/s4_bias_${VOLTAGE}V.conf" "s4_cdte_bias${VOLTAGE}V"
done

# ─────────────────────────────────────────────────────────────────────
# SCENARIO 5 — Temperature Sensitivity
# Deployment condition analysis
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▓▓▓ SCENARIO 5: Temperature Sweep ▓▓▓"

for TEMP in 253 273 293 313 333; do
cat > $SCENARIOS/s5_temp_${TEMP}K.conf << EOF
[Allpix]
log_level = "WARNING"
number_of_events = 10000
detectors_file = "$CONFIGS/detector_medipix3_cdte.conf"
random_seed = 42

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
physics_list = QGSP_BERT
particle_type = "gamma"
source_energy = 60keV
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
temperature = ${TEMP}K
charge_per_step = 10
mobility_model = "jacoboni"

[SimpleTransfer]
max_depth_distance = 5um

[DefaultDigitizer]
electronics_noise = 80e
threshold = 700e
threshold_smearing = 35e

[DetectorHistogrammer]
EOF
    run_sim "$SCENARIOS/s5_temp_${TEMP}K.conf" "s5_cdte_${TEMP}K"
done

# ─────────────────────────────────────────────────────────────────────
# SCENARIO 6 — Pixel Pitch Comparison
# Spectroscopic vs fine pitch mode
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▓▓▓ SCENARIO 6: Pixel Pitch Comparison ▓▓▓"

declare -A PITCHES=(
    ["fine"]="55um 55um"
    ["spectro"]="110um 110um"
    ["coarse"]="250um 250um"
)

declare -A NPIXELS=(
    ["fine"]="256 256"
    ["spectro"]="128 128"
    ["coarse"]="80 80"
)

for MODE in fine spectro coarse; do
    PITCH=${PITCHES[$MODE]}
    NPIX=${NPIXELS[$MODE]}

cat > $SCENARIOS/detector_pitch_${MODE}.conf << EOF
[medipix3_detector]
type = "medipix3"
position = 0 0 0
orientation = 0 0 0
number_of_pixels = ${NPIX}
pixel_size = ${PITCH}
sensor_thickness = 300um
sensor_material = "cadmium_telluride"
EOF

cat > $SCENARIOS/s6_pitch_${MODE}.conf << EOF
[Allpix]
log_level = "WARNING"
number_of_events = 10000
detectors_file = "$SCENARIOS/detector_pitch_${MODE}.conf"
random_seed = 42

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
physics_list = QGSP_BERT
particle_type = "gamma"
source_energy = 60keV
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
EOF
    run_sim "$SCENARIOS/s6_pitch_${MODE}.conf" "s6_cdte_pitch${MODE}"
done

# ─────────────────────────────────────────────────────────────────────
# SCENARIO 7 — Beam Intensity Scaling
# Multiple photons per event simulates higher flux
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▓▓▓ SCENARIO 7: Beam Intensity Scaling ▓▓▓"

for NPART in 1 5 10 50 100; do
cat > $SCENARIOS/s7_flux_${NPART}.conf << EOF
[Allpix]
log_level = "WARNING"
number_of_events = 1000
detectors_file = "$CONFIGS/detector_medipix3_cdte.conf"
random_seed = 42

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
physics_list = QGSP_BERT
particle_type = "gamma"
source_energy = 60keV
source_type = "beam"
beam_size = 1mm
beam_direction = 0 0 1
source_position = 0 0 -1cm
number_of_particles = ${NPART}

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
EOF
    run_sim "$SCENARIOS/s7_flux_${NPART}.conf" "s7_cdte_flux${NPART}"
done

# ─────────────────────────────────────────────────────────────────────
# SCENARIO 8 — Sensor Thickness Optimisation
# Cost vs performance tradeoff
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "▓▓▓ SCENARIO 8: Sensor Thickness Sweep ▓▓▓"

for THICKNESS in 100 300 500 750 1000 1500; do

cat > $SCENARIOS/detector_thickness_${THICKNESS}um.conf << EOF
[medipix3_detector]
type = "medipix3"
position = 0 0 0
orientation = 0 0 0
number_of_pixels = 256 256
pixel_size = 55um 55um
sensor_thickness = ${THICKNESS}um
sensor_material = "cadmium_telluride"
EOF

cat > $SCENARIOS/s8_thickness_${THICKNESS}um.conf << EOF
[Allpix]
log_level = "WARNING"
number_of_events = 10000
detectors_file = "$SCENARIOS/detector_thickness_${THICKNESS}um.conf"
random_seed = 42

[GeometryBuilderGeant4]
world_material = "air"

[DepositionGeant4]
physics_list = QGSP_BERT
particle_type = "gamma"
source_energy = 60keV
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
EOF
    run_sim "$SCENARIOS/s8_thickness_${THICKNESS}um.conf" "s8_cdte_thick${THICKNESS}um"
done

# ─────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════"
echo "ALL SCENARIOS COMPLETE"
echo "════════════════════════════════════════════════════"
echo ""
echo "Output files in $OUTPUT:"
ls -lh $OUTPUT/*.root 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
echo ""
echo "Total ROOT files generated:"
ls $OUTPUT/*.root 2>/dev/null | wc -l