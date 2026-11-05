#!/bin/bash
# =======================================================================
# Material Penetration Experiment - hybrid validated workflow
#
# Workhorse:
#   4 CdTe detector models x 14 spectrum energies = 56 bare-detector
#   Allpix runs. These runs contain no alloy and define the intrinsic
#   detector response per incident photon at each energy.
#
# Validation:
#   12 passive-alloy transport cross-checks: all 4 detectors + Alloy 2 brass
#   at 40, 80, and 120 keV. These are not the production result engine;
#   they are evidence for the analytical Beer-Lambert approximation.
#
# Useful controls:
#   DRY_RUN=1       generate configs/manifest without launching Allpix
#   RUN_BARE=0      skip the 56 bare-detector runs
#   RUN_VALIDATION=0 skip the 3 passive-material runs
#   BARE_EVENTS=... default 10000
#   VALIDATION_EVENTS=... default 10000
# =======================================================================

set -euo pipefail

CONFIGS=/data/simulation/configs
OUTPUT=/data/output
SCENARIOS=$CONFIGS/scenarios/material_penetration
MANIFEST=$OUTPUT/material_penetration_run_manifest.csv

RUN_BARE=${RUN_BARE:-1}
RUN_VALIDATION=${RUN_VALIDATION:-1}
DRY_RUN=${DRY_RUN:-0}
BARE_EVENTS=${BARE_EVENTS:-10000}
VALIDATION_EVENTS=${VALIDATION_EVENTS:-10000}
ONLY_DETECTOR=${ONLY_DETECTOR:-}
ONLY_ENERGY=${ONLY_ENERGY:-}

mkdir -p "$SCENARIOS"
# Manifest is APPEND-ONLY by default. It used to be truncated on every
# invocation, which silently destroyed earlier rows when a second batch ran.
RESET_MANIFEST=${RESET_MANIFEST:-0}
OUTPUT_TAG=${OUTPUT_TAG:-}

# Provenance passed in from the host wrapper (simulation/run.sh). The driver
# runs inside the container and cannot inspect its own image.
RANDOM_SEED=${RANDOM_SEED:-42}
ALLPIX_IMAGE_REF=${ALLPIX_IMAGE_REF:-unknown}
ALLPIX_IMAGE_DIGEST=${ALLPIX_IMAGE_DIGEST:-unknown}
DRIVER_GIT_REV=${DRIVER_GIT_REV:-unknown}
# Every manifest field goes through this: a newline or comma in any value
# silently corrupts the CSV, and the values come from external commands.
csv_safe() { printf '%s' "$1" | tr -d ',\n\r'; }

# `head -1` SIGPIPEs allpix mid-write, which intermittently captured MULTIPLE
# lines and embedded a newline in the manifest row, splitting it in two. sed -n
# '1p' consumes the whole stream instead, and tr strips any stray separator.
ALLPIX_VERSION=$(allpix --version 2>/dev/null | sed -n '1p' | tr -d ',\n' || echo unknown)
[ -n "$(csv_safe "$ALLPIX_VERSION")" ] || ALLPIX_VERSION=unknown

DRIVER_NAME=$(basename "${BASH_SOURCE[0]}")

MANIFEST_HEADER="mode,detector,energy_keV,n_events,output_name,config_path,campaign,output_tag,sensor_thickness,pixel_pitch,n_pixels,threshold_e,noise_e,bias_V,depletion_V,random_seed,passive_material,alloy,gap_mm,detector_config_path,image_ref,image_digest,allpix_version,driver_name,driver_git_rev,started_utc,finished_utc,status,root_sha256,root_bytes,schema_version,provenance_source"

if [ "$RESET_MANIFEST" = "1" ] || [ ! -f "$MANIFEST" ]; then
    printf "%s\n" "$MANIFEST_HEADER" > "$MANIFEST"
fi
# Upgrade a v1 (6-column) manifest in place before appending v2 rows, otherwise
# the file becomes ragged and pd.read_csv fails. Legacy rows keep their four
# real fields and are marked schema_version=1 / provenance_source=legacy so the
# analysis side can tell reconstructed provenance from recorded provenance.
migrate_manifest_v1() {
    [ -f "$MANIFEST" ] || return 0
    local first
    first=$(head -1 "$MANIFEST")
    [ "$first" = "$MANIFEST_HEADER" ] && return 0
    if [ "$first" = "mode,detector,energy_keV,n_events,output_name,config_path" ]; then
        echo "Migrating v1 manifest -> v2: $MANIFEST"
        cp "$MANIFEST" "${MANIFEST%.csv}.v1.bak"
        {
            printf "%s\n" "$MANIFEST_HEADER"
            tail -n +2 "${MANIFEST%.csv}.v1.bak" | awk -F, 'NF>0 {
                printf "%s", $0
                for (i = NF; i < 30; i++) printf ","
                printf ",1,legacy\n"
            }'
        } > "$MANIFEST"
    fi
}
migrate_manifest_v1

ENERGIES=(20 30 40 50 60 70 80 90 100 110 120 130 140 150)
if [ -n "${VALIDATION_ENERGIES_OVERRIDE:-}" ]; then
    read -ra VALIDATION_ENERGIES <<< "$VALIDATION_ENERGIES_OVERRIDE"
else
    VALIDATION_ENERGIES=(40 80 120)
fi
DETECTORS=(medipix3 eiger2 hexitec_proxy timepix3_cdte)

# CdTe pair-creation energy locked to the methodology value:
# epsilon_CdTe = 4.43 eV/e-h pair. Lower thresholds below are rounded.
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
declare -A THICK=(
    [medipix3]="300um"
    [eiger2]="750um"
    [hexitec_proxy]="1000um"
    [timepix3_cdte]="1000um"
)
# EIGER2 noise/smearing is an estimate: no vendor ENC figure was available,
# so we use the mean of the other three chips' ENC (80/50/90e) rather than
# an unphysical 0e, which would give EIGER2 an ideal-threshold advantage
# the other chips don't have.
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
random_seed = ${RANDOM_SEED}

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

    # OUTPUT_TAG must be part of the detector config name, or thickness
    # variants overwrite each other's geometry record.
    local det_config=$SCENARIOS/detector_${chip}_${mode}${OUTPUT_TAG}.conf
    local sim_config=$SCENARIOS/${output_name}.conf

    write_detector_config "$chip" "$det_config" "$include_brass"
    write_sim_config "$chip" "$energy" "$n_events" "$output_name" "$det_config" "$sim_config"

    local alloy="" passive=""
    if [ "$include_brass" != "0" ] && [ -n "$include_brass" ]; then
        alloy="$include_brass"
        passive="${ALLOY_MATERIAL[$include_brass]}"
    fi

    # A dry run generates configs and simulates nothing, so it must not append
    # a manifest row -- that would record a run that never happened as ok.
    if [ "$DRY_RUN" = "1" ]; then
        echo "DRY_RUN=1: wrote $sim_config (no simulation, no manifest row)"
        return 0
    fi

    # Run FIRST, then record. The row used to be written before the simulation,
    # so a failed run left a row claiming success.
    local started finished status=ok
    started=$(date -u +%FT%TZ)
    run_sim "$sim_config" "$output_name" || status=failed
    finished=$(date -u +%FT%TZ)

    local rsha="" rbytes=""
    if [ -f "$OUTPUT/${output_name}.root" ]; then
        rsha=$(sha256sum "$OUTPUT/${output_name}.root" | cut -d' ' -f1)
        rbytes=$(stat -c%s "$OUTPUT/${output_name}.root")
    fi

    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$mode" "$chip" "$energy" "$n_events" "$output_name" "$sim_config" \
        "material_penetration" "$OUTPUT_TAG" "${THICK[$chip]}" "${PITCH[$chip]}" "${NPIX[$chip]// /x}" \
        "${THRESH[$chip]}" "${NOISE[$chip]}" "${BIAS[$chip]}" "${DEPL[$chip]}" "$RANDOM_SEED" \
        "$passive" "$alloy" "${GAP_MM:-0}" "$det_config" \
        "$(csv_safe "$ALLPIX_IMAGE_REF")" "$(csv_safe "$ALLPIX_IMAGE_DIGEST")" "$(csv_safe "$ALLPIX_VERSION")" "$(csv_safe "$DRIVER_NAME")" "$(csv_safe "$DRIVER_GIT_REV")" \
        "$started" "$finished" "$status" "$rsha" "$rbytes" "2" "driver" >> "$MANIFEST"

    [ "$status" = ok ] || return 1
}

if [ "$RUN_BARE" = "1" ]; then
    echo ""
    echo "############################################"
    echo "# 56 bare-detector intrinsic response runs"
    echo "############################################"

    for chip in "${DETECTORS[@]}"; do
        should_run_detector "$chip" || continue
        for energy in "${ENERGIES[@]}"; do
            should_run_energy "$energy" || continue
            write_and_run "bare" "$chip" "$energy" "$BARE_EVENTS" "0" "mp_bare_${chip}_${energy}keV"
        done
    done
fi

if [ "$RUN_VALIDATION" = "1" ]; then
    echo ""
    echo "############################################"
    echo "# 12 passive-alloy transport validation runs"
    echo "# (all 4 detectors x Alloy 2 brass x 3 energies)"
    echo "############################################"

    for chip in "${DETECTORS[@]}"; do
        should_run_detector "$chip" || continue
        for energy in "${VALIDATION_ENERGIES[@]}"; do
            should_run_energy "$energy" || continue
            write_and_run "transport" "$chip" "$energy" "$VALIDATION_EVENTS" "1" "mp_transport_${chip}_alloy2_${energy}keV"
        done
    done
fi

echo ""
echo "======================================================="
echo "MATERIAL PENETRATION CONFIGURATION COMPLETE"
echo "======================================================="
echo "Manifest: $MANIFEST"
echo "Bare ROOT files:       $(ls "$OUTPUT"/mp_bare_*.root 2>/dev/null | wc -l)"
echo "Transport ROOT files:  $(ls "$OUTPUT"/mp_transport_*.root 2>/dev/null | wc -l)"
