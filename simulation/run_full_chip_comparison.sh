#!/bin/bash
# =======================================================================
# FULL CHIP COMPARISON - HEXITEC vs Medipix3 vs EIGER2 (all CdTe)
# 4 categories: Food (5-material + energy sweep), Medical (reuses Food),
#               Baggage (occlusion), Chip Performance (degradation)
# Total: 59 new simulations
# =======================================================================

set -e

CONFIGS=/data/simulation/configs
OUTPUT=/data/output
SCENARIOS=$CONFIGS/scenarios/chip_comparison

mkdir -p $SCENARIOS

run_sim() {
    local config_path=$1
    local output_name=$2
    echo ""
    echo "======================================================="
    echo "Running: $output_name"
    echo "======================================================="
    allpix -c "$config_path" 2>&1 | tail -6
    if [ -f "$OUTPUT/modules.root" ]; then
        mv "$OUTPUT/modules.root" "$OUTPUT/${output_name}.root"
        echo "SAVED: ${output_name}.root"
    else
        echo "FAILED: no output for $output_name"
    fi
}

# =======================================================================
# CHIP PARAMETER TABLE (all confirmed/best-estimate, CdTe)
# =======================================================================
declare -A NPIX=( [hexitec]="80 80" [medipix3]="256 256" [eiger2]="256 256" )
declare -A PITCH=( [hexitec]="250um" [medipix3]="55um" [eiger2]="75um" )
declare -A THICK=( [hexitec]="1000um" [medipix3]="300um" [eiger2]="750um" )
declare -A NOISE=( [hexitec]="20e" [medipix3]="80e" [eiger2]="91e" )
declare -A THRESH=( [hexitec]="795e" [medipix3]="700e" [eiger2]="909e" )
declare -A SMEAR=( [hexitec]="20e" [medipix3]="35e" [eiger2]="114e" )
declare -A BIAS=( [hexitec]="-500V" [medipix3]="-500V" [eiger2]="-400V" )
declare -A DEPL=( [hexitec]="-300V" [medipix3]="-300V" [eiger2]="-250V" )

write_detector_config() {
    local chip=$1
    local path=$2
cat > $path << INNEREOF
[${chip}_detector]
type = "medipix3"
position = 0 0 0
orientation = 0 0 0
number_of_pixels = ${NPIX[$chip]}
pixel_size = ${PITCH[$chip]} ${PITCH[$chip]}
sensor_thickness = ${THICK[$chip]}
sensor_material = "cadmium_telluride"
INNEREOF
}

write_and_run() {
    local chip=$1
    local energy=$2
    local n_events=$3
    local output_name=$4
    local extra_propagation=$5  # optional: trapping params for degradation tests

    local det_config=$SCENARIOS/detector_${chip}.conf
    write_detector_config "$chip" "$det_config"

    local sim_config=$SCENARIOS/${output_name}.conf
cat > $sim_config << INNEREOF
[Allpix]
log_level = "WARNING"
number_of_events = ${n_events}
detectors_file = "${det_config}"
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
bias_voltage = ${BIAS[$chip]}
depletion_voltage = ${DEPL[$chip]}

[GenericPropagation]
temperature = 293K
charge_per_step = 10
mobility_model = "jacoboni"
${extra_propagation}

[SimpleTransfer]
max_depth_distance = 5um

[DefaultDigitizer]
electronics_noise = ${NOISE[$chip]}
threshold = ${THRESH[$chip]}
threshold_smearing = ${SMEAR[$chip]}

[DetectorHistogrammer]
INNEREOF

    run_sim "$sim_config" "$output_name"
}

CHIPS="hexitec medipix3 eiger2"

# =======================================================================
# CATEGORY 1a: 5-material food inspection @ 60 keV (15 sims)
# n_events = transmission through material alone, independent of chip
# =======================================================================
echo ""
echo "############################################"
echo "# CATEGORY 1a: 5-MATERIAL COMPARISON @ 60 keV"
echo "############################################"

declare -A MAT_N=( [steel]="3874" [bone]="7392" [glass]="7638" [stone]="7365" [rubber]="8885" )

for chip in $CHIPS; do
    for mat in steel bone glass stone rubber; do
        write_and_run "$chip" 60 "${MAT_N[$mat]}" "cat1_${chip}_60keV_${mat}"
    done
done

# =======================================================================
# CATEGORY 1b/2: Steel-only energy sweep, 4 energies (12 sims)
# Reused directly by Category 2 (Medical CT) - no separate medical sims needed
# =======================================================================
echo ""
echo "############################################"
echo "# CATEGORY 1b/2: STEEL ENERGY SWEEP (also serves Medical CT)"
echo "############################################"

declare -A STEEL_N=( [40]="575" [60]="3874" [80]="6260" [100]="7464" )

for chip in $CHIPS; do
    for E in 40 60 80 100; do
        write_and_run "$chip" "$E" "${STEEL_N[$E]}" "cat2_${chip}_${E}keV_steel"
    done
done

# =======================================================================
# CATEGORY 3: Baggage occlusion - 3 levels x (clutter+threat, clutter-alone)
# Plus clean background per chip (medipix3's already exists from category 1)
# =======================================================================
echo ""
echo "############################################"
echo "# CATEGORY 3: BAGGAGE OCCLUSION (corrected methodology)"
echo "############################################"

# Combined (clutter+steel threat) transmission at 60keV
declare -A OCCL_COMBINED=( [sparse]="2566" [medium]="1384" [cluttered]="494" )
# Clutter-ALONE transmission at 60keV (no threat) - the corrected reference
declare -A OCCL_CLUTTERONLY=( [sparse]="6627" [medium]="3572" [cluttered]="1276" )

for chip in $CHIPS; do
    for level in sparse medium cluttered; do
        write_and_run "$chip" 60 "${OCCL_COMBINED[$level]}" "cat3_${chip}_occl_${level}_threat"
        write_and_run "$chip" 60 "${OCCL_CLUTTERONLY[$level]}" "cat3_${chip}_occl_${level}_clutteronly"
    done
    # Clean background (no clutter, no threat) - needed for the "none" occlusion level
    write_and_run "$chip" 60 10000 "cat3_${chip}_clean_background"
done

# =======================================================================
# CATEGORY 4: Chip performance - degradation stress test
# Medipix3's already exists (s2_v4_*) - only run HEXITEC and EIGER2
# =======================================================================
echo ""
echo "############################################"
echo "# CATEGORY 4: DEGRADATION / DURABILITY (HEXITEC + EIGER2 only)"
echo "############################################"

declare -A TRAP_TIME=( [fresh]="10000" [light]="10" [moderate]="5" [heavy]="2" [severe]="1" [extreme]="0.5" )

for chip in hexitec eiger2; do
    for stage in fresh light moderate heavy severe extreme; do
        TRAP_NS="${TRAP_TIME[$stage]}"
        EXTRA="trapping_model = \"constant\"
trapping_time_electron = ${TRAP_NS}ns
trapping_time_hole = ${TRAP_NS}ns"
        write_and_run "$chip" 60 10000 "cat4_${chip}_degr_${stage}" "$EXTRA"
    done
done

# =======================================================================
# Summary
# =======================================================================
echo ""
echo "======================================================="
echo "FULL CHIP COMPARISON COMPLETE"
echo "======================================================="
echo ""
echo "Total new ROOT files:"
ls $OUTPUT/cat*.root 2>/dev/null | wc -l
echo ""
echo "By category:"
echo "  Category 1a (5-material):  $(ls $OUTPUT/cat1_*.root 2>/dev/null | wc -l)"
echo "  Category 1b/2 (energy sweep): $(ls $OUTPUT/cat2_*.root 2>/dev/null | wc -l)"
echo "  Category 3 (baggage):      $(ls $OUTPUT/cat3_*.root 2>/dev/null | wc -l)"
echo "  Category 4 (degradation):  $(ls $OUTPUT/cat4_*.root 2>/dev/null | wc -l)"
