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
    [timepix3_cdte]="61e"
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
    [timepix3_cdte]="61e"
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
# Passive-slab material per alloy for the transport cross-check.
# Allpix/Geant4 can only reference NIST built-ins, so ONLY alloy1 (pure Cu)
# maps to an EXACT material (G4_Cu). alloy2/3/4/5 have no exact built-in and
# are approximations only -- this is the same limitation that caused the
# G4_BRASS error, so they must not be treated as accurate transport of those
# compositions. Default cross-check runs alloy1 alone (composition-confound-free).
declare -A ALLOY_MATERIAL=(
    [alloy1]="G4_Cu"     # C11000 ETP copper, 99.9% Cu -- EXACT
    [alloy2]="G4_BRASS"  # C36000 -- APPROX ONLY (G4_BRASS != C36000)
    [alloy3]="G4_Cu"     # C70600 CuNi 90/10 -- APPROX (88.6% Cu)
    [alloy4]="G4_Cu"     # C95500 Al bronze -- POOR APPROX, do not trust
    [alloy5]="G4_Cu"     # C17200 BeCu -- APPROX (98% Cu)
)
read -ra TRANSPORT_ALLOYS <<< "${TRANSPORT_ALLOYS:-alloy1}"
read -ra TRANSPORT_ENERGIES <<< "${TRANSPORT_ENERGIES:-${ENERGIES[*]}}"
# Air gap (mm) between the slab's exit face and the sensor's entrance face.
# GAP_MM=0 reproduces the original contact geometry (max scatter capture);
# a realistic inspection standoff (e.g. 30) lets forward-scattered photons
# diverge past the sensor, so measured scatter buildup collapses toward 1.
# The parallel 1mm pencil beam still hits the sensor identically -- only
# scattered (divergent) photons are affected. Slab centre, source and world
# margin all shift with the gap to preserve the source->slab beam path.
GAP_MM=${GAP_MM:-0}
SLAB_Z=$((3 + GAP_MM))      # slab centre at z = -SLAB_Z mm (back face at -(0.5+GAP))
SOURCE_Z=$((10 + GAP_MM))   # source at z = -SOURCE_Z mm (preserves source->slab standoff)
WORLD_Z=$((20 + GAP_MM))    # world half-margin in z, enlarged to contain the longer path

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

    if [ "$include_brass" != "0" ] && [ -n "$include_brass" ]; then
        local alloy_tag="$include_brass"
        cat >> "$path" << INNEREOF

[${alloy_tag}_slab]
role = "passive"
type = "box"
material = "${ALLOY_MATERIAL[$alloy_tag]}"
position = 0 0 -${SLAB_Z}mm
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
world_minimum_margin = 10mm 10mm ${WORLD_Z}mm

[DepositionGeant4]
physics_list = QGSP_BERT
particle_type = "gamma"
source_energy = ${energy}keV
source_type = "beam"
beam_size = 1mm
beam_direction = 0 0 1
source_position = 0 0 -${SOURCE_Z}mm
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
        "material_penetration_uniform" "$OUTPUT_TAG" "${THICK[$chip]}" "${PITCH[$chip]}" "${NPIX[$chip]// /x}" \
        "${THRESH[$chip]}" "${NOISE[$chip]}" "${BIAS[$chip]}" "${DEPL[$chip]}" "$RANDOM_SEED" \
        "$passive" "$alloy" "${GAP_MM:-0}" "$det_config" \
        "$(csv_safe "$ALLPIX_IMAGE_REF")" "$(csv_safe "$ALLPIX_IMAGE_DIGEST")" "$(csv_safe "$ALLPIX_VERSION")" "$(csv_safe "$DRIVER_NAME")" "$(csv_safe "$DRIVER_GIT_REV")" \
        "$started" "$finished" "$status" "$rsha" "$rbytes" "2" "driver" >> "$MANIFEST"

    [ "$status" = ok ] || return 1
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
        for alloy in "${TRANSPORT_ALLOYS[@]}"; do
            for energy in "${TRANSPORT_ENERGIES[@]}"; do
                should_run_energy "$energy" || continue
                write_and_run "transport" "$chip" "$energy" "$VALIDATION_EVENTS" "$alloy" "mpu_transport_${chip}_${alloy}_${energy}keV"
            done
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
