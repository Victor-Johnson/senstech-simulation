#!/bin/bash
# =======================================================================
# Material Penetration Experiment - UNIFORM SENSOR THICKNESS variant
#
# Same hybrid workflow as run_material_penetration.sh, but every detector
# uses a 1.0 mm CdTe sensor. This removes the thickness advantage so the
# comparison isolates the per-chip detection thresholds / energy windows:
#   medipix3      1129e  (5.0 keV)   window  5-460 keV
#   eiger2         903e  (4.0 keV)   window  4-80  keV
#   hexitec_proxy  452e  (2.0 keV)   window  2-200 keV
#   timepix3_cdte  650e  (2.88 keV)  window  2.88-120 keV
#
# hexitec_proxy and timepix3_cdte were already 1.0 mm in the baseline
# experiment, so their baseline ROOT files are bit-identical to what this
# script would produce (same seed, same configs). The driver below still
# supports running them, but the intended invocation is:
#   ONLY_DETECTOR=medipix3 ...  and  ONLY_DETECTOR=eiger2 ...
# with the unchanged detectors' files copied under the mpu_ prefix.
#
# Output prefix: mpu_ (material penetration uniform)
# Manifest:      /data/output/material_penetration_uniform_run_manifest.csv
#
# Controls: DRY_RUN, RUN_BARE, RUN_VALIDATION, BARE_EVENTS,
#           VALIDATION_EVENTS, ONLY_DETECTOR, ONLY_ENERGY,
#           VALIDATION_ENERGIES_OVERRIDE  (same as baseline script)
# =======================================================================

set -euo pipefail

CONFIGS=/data/simulation/configs
OUTPUT=/data/output
SCENARIOS=$CONFIGS/scenarios/material_penetration_uniform
MANIFEST=$OUTPUT/material_penetration_uniform_run_manifest.csv

RUN_BARE=${RUN_BARE:-1}
RUN_VALIDATION=${RUN_VALIDATION:-1}
DRY_RUN=${DRY_RUN:-0}
BARE_EVENTS=${BARE_EVENTS:-10000}
VALIDATION_EVENTS=${VALIDATION_EVENTS:-10000}
ONLY_DETECTOR=${ONLY_DETECTOR:-}
ONLY_ENERGY=${ONLY_ENERGY:-}
APPEND_MANIFEST=${APPEND_MANIFEST:-0}

mkdir -p "$SCENARIOS"
if [ "$APPEND_MANIFEST" != "1" ]; then
    printf "mode,detector,energy_keV,n_events,output_name,config_path\n" > "$MANIFEST"
fi

ENERGIES=(20 30 40 50 60 70 80 90 100 110 120 130 140 150)
if [ -n "${VALIDATION_ENERGIES_OVERRIDE:-}" ]; then
    read -ra VALIDATION_ENERGIES <<< "$VALIDATION_ENERGIES_OVERRIDE"
else
    VALIDATION_ENERGIES=(40 80 120)
fi
DETECTORS=(medipix3 eiger2 hexitec_proxy timepix3_cdte)

declare -A NPIX=(
    [medipix3]="256 256"
    [eiger2]="256 256"
    [hexitec_proxy]="80 80"
    [timepix3_cdte]="256 256"
)
declare -A PITCH=(
    [medipix3]="55um"
    [eiger2]="75um"
    [hexitec_proxy]="250um"
    [timepix3_cdte]="55um"
)
# The deliberate change vs the baseline experiment:
declare -A THICK=(
    [medipix3]="1000um"
    [eiger2]="1000um"
    [hexitec_proxy]="1000um"
    [timepix3_cdte]="1000um"
)
declare -A NOISE=(
    [medipix3]="80e"
    [eiger2]="75e"
    [hexitec_proxy]="50e"
    [timepix3_cdte]="90e"
)
declare -A THRESH=(
    [medipix3]="1129e"
    [eiger2]="903e"
    [hexitec_proxy]="452e"
    [timepix3_cdte]="650e"
)
declare -A SMEAR=(
    [medipix3]="80e"
    [eiger2]="75e"
    [hexitec_proxy]="50e"
    [timepix3_cdte]="90e"
)
declare -A BIAS=(
    [medipix3]="-400V"
    [eiger2]="-400V"
    [hexitec_proxy]="-500V"
    [timepix3_cdte]="-300V"
)
declare -A DEPL=(
    [medipix3]="-300V"
    [eiger2]="-250V"
    [hexitec_proxy]="-300V"
    [timepix3_cdte]="-200V"
)

run_sim() {
    local config_path=$1
    local output_name=$2

    echo ""
    echo "======================================================="
    echo "Running: $output_name"
    echo "======================================================="

    if [ "$DRY_RUN" = "1" ]; then
        echo "DRY_RUN=1: generated $config_path"
        return 0
    fi

    allpix -c "$config_path" 2>&1 | tail -8
    if [ -f "$OUTPUT/modules.root" ]; then
        mv "$OUTPUT/modules.root" "$OUTPUT/${output_name}.root"
        echo "SAVED: ${output_name}.root"
    else
        echo "FAILED: no output for $output_name" >&2
        return 1
    fi
}

should_run_detector() {
    local chip=$1
    [ -z "$ONLY_DETECTOR" ] || [ "$chip" = "$ONLY_DETECTOR" ]
}

should_run_energy() {
    local energy=$1
    [ -z "$ONLY_ENERGY" ] || [ "$energy" = "$ONLY_ENERGY" ]
}

write_detector_config() {
    local chip=$1
    local path=$2
    local include_brass=${3:-0}

    cat > "$path" << INNEREOF
[${chip}_detector]
type = "medipix3"
position = 0 0 0
orientation = 0 0 0
number_of_pixels = ${NPIX[$chip]}
pixel_size = ${PITCH[$chip]} ${PITCH[$chip]}
sensor_thickness = ${THICK[$chip]}
sensor_material = "cadmium_telluride"
INNEREOF

    if [ "$include_brass" = "1" ]; then
        cat >> "$path" << INNEREOF

[alloy2_brass_block]
role = "passive"
type = "box"
material = "G4_BRASS"
position = 0 0 -3mm
orientation = 0 0 0
size = 20mm 20mm 5mm
color = 0.85 0.58 0.16
opacity = 0.35
INNEREOF
    fi
}

write_sim_config() {
    local chip=$1
    local energy=$2
    local n_events=$3
    local output_name=$4
    local det_config=$5
    local sim_config=$6

    cat > "$sim_config" << INNEREOF
[Allpix]
log_level = "WARNING"
number_of_events = ${n_events}
detectors_file = "${det_config}"
random_seed = 42

[GeometryBuilderGeant4]
world_material = "air"
world_minimum_margin = 10mm 10mm 15mm

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

[SimpleTransfer]
max_depth_distance = 5um

[DefaultDigitizer]
electronics_noise = ${NOISE[$chip]}
threshold = ${THRESH[$chip]}
threshold_smearing = ${SMEAR[$chip]}

[DetectorHistogrammer]
INNEREOF
}

write_and_run() {
    local mode=$1
    local chip=$2
    local energy=$3
    local n_events=$4
    local include_brass=$5
    local output_name=$6

    local det_config=$SCENARIOS/detector_${chip}_${mode}.conf
    local sim_config=$SCENARIOS/${output_name}.conf

    write_detector_config "$chip" "$det_config" "$include_brass"
    write_sim_config "$chip" "$energy" "$n_events" "$output_name" "$det_config" "$sim_config"

    printf "%s,%s,%s,%s,%s,%s\n" "$mode" "$chip" "$energy" "$n_events" "$output_name" "$sim_config" >> "$MANIFEST"
    run_sim "$sim_config" "$output_name"
}

if [ "$RUN_BARE" = "1" ]; then
    echo ""
    echo "############################################"
    echo "# Bare-detector intrinsic response runs (uniform 1.0 mm CdTe)"
    echo "############################################"

    for chip in "${DETECTORS[@]}"; do
        should_run_detector "$chip" || continue
        for energy in "${ENERGIES[@]}"; do
            should_run_energy "$energy" || continue
            write_and_run "bare" "$chip" "$energy" "$BARE_EVENTS" "0" "mpu_bare_${chip}_${energy}keV"
        done
    done
fi

if [ "$RUN_VALIDATION" = "1" ]; then
    echo ""
    echo "############################################"
    echo "# Passive-alloy transport validation runs (uniform 1.0 mm CdTe)"
    echo "############################################"

    for chip in "${DETECTORS[@]}"; do
        should_run_detector "$chip" || continue
        for energy in "${VALIDATION_ENERGIES[@]}"; do
            should_run_energy "$energy" || continue
            write_and_run "transport" "$chip" "$energy" "$VALIDATION_EVENTS" "1" "mpu_transport_${chip}_alloy2_${energy}keV"
        done
    done
fi

echo ""
echo "======================================================="
echo "MATERIAL PENETRATION (UNIFORM THICKNESS) COMPLETE"
echo "======================================================="
echo "Manifest: $MANIFEST"
echo "Bare ROOT files:       $(ls "$OUTPUT"/mpu_bare_*.root 2>/dev/null | wc -l)"
echo "Transport ROOT files:  $(ls "$OUTPUT"/mpu_transport_*.root 2>/dev/null | wc -l)"
