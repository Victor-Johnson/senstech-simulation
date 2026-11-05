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
SCENARIOS=$CONFIGS/scenarios/phase2_selection
MANIFEST=$OUTPUT/phase2_selection_run_manifest.csv

RUN_BARE=${RUN_BARE:-1}
RUN_VALIDATION=${RUN_VALIDATION:-0}
DRY_RUN=${DRY_RUN:-0}
BARE_EVENTS=${BARE_EVENTS:-10000}
VALIDATION_EVENTS=${VALIDATION_EVENTS:-10000}
ONLY_DETECTOR=${ONLY_DETECTOR:-}
ONLY_ENERGY=${ONLY_ENERGY:-}
# Manifest is APPEND-ONLY by default. It used to be truncated on every
# invocation (APPEND_MANIFEST=0 default), which silently destroyed the 1 mm
# phase-2 rows when the 0.75 mm batch was run afterwards. Set RESET_MANIFEST=1
# only when you deliberately want to start a fresh manifest.
RESET_MANIFEST=${RESET_MANIFEST:-0}
# Native-thickness runs: override one detector's CdTe thickness and tag the
# output filename so the matched-thickness (1 mm) ROOTs are not clobbered.
# e.g. ONLY_DETECTOR=eiger2 THICK_OVERRIDE=750um OUTPUT_TAG=_075mm
THICK_OVERRIDE=${THICK_OVERRIDE:-}
OUTPUT_TAG=${OUTPUT_TAG:-}

# Provenance passed in from the host wrapper (simulation/run.sh). The driver
# runs inside the container and cannot inspect its own image, so these arrive
# as environment variables or stay "unknown".
RANDOM_SEED=${RANDOM_SEED:-42}

# --- Transport-physics overrides (item 2: CdTe transport sensitivity) ---------
# Defaults reproduce the published campaign byte-for-byte: when MOBILITY_MODEL is
# "jacoboni" and no trapping times are set, the emitted [GenericPropagation]
# block is character-identical to the one that produced the delivered results.
#
# Allpix v3.2.0 offers only silicon-fitted mobility parameterisations
# (jacoboni, canali, hamburg, masetti, arora, ruch_kino, quay, ...). The one
# route to CdTe-appropriate transport is mobility_model="constant" with explicit
# mobility values, which this build does accept.
MOBILITY_MODEL=${MOBILITY_MODEL:-jacoboni}
MOBILITY_ELECTRON=${MOBILITY_ELECTRON:-}   # e.g. 1100cm*cm/V/s  (CdTe)
MOBILITY_HOLE=${MOBILITY_HOLE:-}           # e.g. 100cm*cm/V/s   (CdTe)
# Charge trapping is OFF in the published campaign. CdTe's dominant real-world
# artefact is hole trapping; set both to enable. NOTE the SINGULAR key names --
# run_all_scenarios.sh uses plural forms that Allpix silently ignores.
TRAPPING_TIME_ELECTRON=${TRAPPING_TIME_ELECTRON:-}   # e.g. 1000ns
TRAPPING_TIME_HOLE=${TRAPPING_TIME_HOLE:-}           # e.g. 200ns
# Allpix propagates ELECTRONS ONLY by default. Hole trapping -- CdTe's dominant
# real-world artefact -- therefore cannot affect any result unless holes are
# explicitly propagated. Set to 1 to enable.
PROPAGATE_HOLES=${PROPAGATE_HOLES:-}

# Per-event object output (item 5: incident -> deposited -> counted at event
# level). OFF by default: it adds a second ROOT file per run and slows the run.
# MCTrack carries the Geant4 creation process, which is the only route to
# distinguishing Compton scatters from photoelectric absorption.
WRITE_OBJECTS=${WRITE_OBJECTS:-}
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

mkdir -p "$SCENARIOS"
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
# Phase 2 -- 6 candidate ASICs, parameters from Theoretical Reference Framework v2
# (Table 8 / 8a). Matrix sizes are a representative central patch (a 1 mm pencil
# beam only illuminates the centre; total module size does not affect counts),
# so all fine-pitch chips use 256x256 and HEXITEC 80x80 for sim speed.
DETECTORS=(medipix3 medipix4 timepix3_cdte timepix4 eiger2 hexitec_proxy)

declare -A NPIX=(
    [medipix3]="256 256"
    [medipix4]="256 256"
    [timepix3_cdte]="256 256"
    [timepix4]="256 256"
    [eiger2]="256 256"
    [hexitec_proxy]="80 80"
)
declare -A PITCH=(
    [medipix3]="55um"
    [medipix4]="75um"
    [timepix3_cdte]="55um"
    [timepix4]="55um"
    [eiger2]="75um"
    [hexitec_proxy]="250um"
)
# The deliberate change vs the baseline experiment:
# All sensors held at 1 mm CdTe (framework reference thickness; EIGER2 0.75mm
# commercial variant is a separate §11.5 follow-up).
declare -A THICK=(
    [medipix3]="1000um"
    [medipix4]="1000um"
    [timepix3_cdte]="1000um"
    [timepix4]="1000um"
    [eiger2]="1000um"
    [hexitec_proxy]="1000um"
)
# ENC noise (e-) -- framework Table 8. EIGER2 (107) and Medipix4 (211) are the
# derived values from §6.1; the rest are published figures.
declare -A NOISE=(
    [medipix3]="80e"
    [medipix4]="211e"
    [timepix3_cdte]="62e"
    [timepix4]="68e"
    [eiger2]="107e"
    [hexitec_proxy]="50e"
)
# Minimum operating threshold (e-) -- framework Table 8.
declare -A THRESH=(
    [medipix3]="700e"
    [medipix4]="1773e"
    [timepix3_cdte]="500e"
    [timepix4]="1000e"
    [eiger2]="903e"
    [hexitec_proxy]="452e"
)
declare -A SMEAR=(
    [medipix3]="80e"
    [medipix4]="211e"
    [timepix3_cdte]="62e"
    [timepix4]="68e"
    [eiger2]="107e"
    [hexitec_proxy]="50e"
)
# Bias (V) -- framework Table 8a. EIGER2 -375V is the §6.1 field-scaling estimate.
declare -A BIAS=(
    [medipix3]="-500V"
    [medipix4]="-500V"
    [timepix3_cdte]="-500V"
    [timepix4]="-500V"
    [eiger2]="-375V"
    [hexitec_proxy]="-500V"
)
# Depletion reference for the Allpix linear-field model (not published; weak
# effect on counts -- only guarantees a non-zero field across the sensor).
declare -A DEPL=(
    [medipix3]="-300V"
    [medipix4]="-300V"
    [timepix3_cdte]="-300V"
    [timepix4]="-300V"
    [eiger2]="-250V"
    [hexitec_proxy]="-300V"
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
        if [ -n "$WRITE_OBJECTS" ] && [ -f "$OUTPUT/objects.root" ]; then
            mv "$OUTPUT/objects.root" "$OUTPUT/${output_name}_objects.root"
            echo "SAVED: ${output_name}_objects.root"
        fi
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

# Per-event object writer, empty unless WRITE_OBJECTS is set.
DEPOSITION_EXTRA=""
OBJECTS_BLOCK=""
if [ -n "$WRITE_OBJECTS" ]; then
    DEPOSITION_EXTRA="
record_all_tracks = true"
    OBJECTS_BLOCK="

[ROOTObjectWriter]
file_name = \"objects\"
include = \"MCParticle\", \"MCTrack\", \"PixelHit\""
fi

# Extra [GenericPropagation] lines, empty unless an override is requested.
PROPAGATION_EXTRA=""
if [ "$MOBILITY_MODEL" = "constant" ]; then
    [ -n "$MOBILITY_ELECTRON" ] || { echo "MOBILITY_MODEL=constant requires MOBILITY_ELECTRON" >&2; exit 2; }
    [ -n "$MOBILITY_HOLE" ] || { echo "MOBILITY_MODEL=constant requires MOBILITY_HOLE" >&2; exit 2; }
    PROPAGATION_EXTRA="${PROPAGATION_EXTRA}
mobility_electron = ${MOBILITY_ELECTRON}
mobility_hole = ${MOBILITY_HOLE}"
fi
if [ -n "$PROPAGATE_HOLES" ]; then
    PROPAGATION_EXTRA="${PROPAGATION_EXTRA}
propagate_electrons = true
propagate_holes = true"
fi
if [ -n "$TRAPPING_TIME_ELECTRON" ] || [ -n "$TRAPPING_TIME_HOLE" ]; then
    [ -n "$TRAPPING_TIME_ELECTRON" ] && [ -n "$TRAPPING_TIME_HOLE" ] || {
        echo "set BOTH TRAPPING_TIME_ELECTRON and TRAPPING_TIME_HOLE" >&2; exit 2; }
    PROPAGATION_EXTRA="${PROPAGATION_EXTRA}
trapping_model = \"constant\"
trapping_time_electron = ${TRAPPING_TIME_ELECTRON}
trapping_time_hole = ${TRAPPING_TIME_HOLE}"
fi

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
number_of_particles = 1${DEPOSITION_EXTRA}

[ElectricFieldReader]
model = "linear"
bias_voltage = ${BIAS[$chip]}
depletion_voltage = ${DEPL[$chip]}

[GenericPropagation]
temperature = 293K
charge_per_step = 10
mobility_model = "${MOBILITY_MODEL}"${PROPAGATION_EXTRA}

[SimpleTransfer]
max_depth_distance = 5um

[DefaultDigitizer]
electronics_noise = ${NOISE[$chip]}
threshold = ${THRESH[$chip]}
threshold_smearing = ${SMEAR[$chip]}

[DetectorHistogrammer]${OBJECTS_BLOCK}
INNEREOF
}

write_and_run() {
    local mode=$1
    local chip=$2
    local energy=$3
    local n_events=$4
    local include_brass=$5
    local output_name=$6

    # The OUTPUT_TAG must be part of the detector config name. Without it every
    # thickness variant rewrites the previous variant's geometry record, so the
    # .conf no longer describes the run that referenced it. That is how the
    # untagged phase-2 EIGER2 runs lost their geometry provenance.
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

    # Run FIRST, then record. The manifest row used to be written before the
    # simulation, so a failed run left a row claiming success.
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
        "phase2_selection" "$OUTPUT_TAG" "${THICK[$chip]}" "${PITCH[$chip]}" "${NPIX[$chip]// /x}" \
        "${THRESH[$chip]}" "${NOISE[$chip]}" "${BIAS[$chip]}" "${DEPL[$chip]}" "$RANDOM_SEED" \
        "$passive" "$alloy" "$GAP_MM" "$det_config" \
        "$(csv_safe "$ALLPIX_IMAGE_REF")" "$(csv_safe "$ALLPIX_IMAGE_DIGEST")" "$(csv_safe "$ALLPIX_VERSION")" "$(csv_safe "$DRIVER_NAME")" "$(csv_safe "$DRIVER_GIT_REV")" \
        "$started" "$finished" "$status" "$rsha" "$rbytes" "2" "driver" >> "$MANIFEST"

    [ "$status" = ok ] || return 1
}

# optional thickness override. With ONLY_DETECTOR set it applies to that chip
# (native-thickness runs); without it, applies to ALL detectors (matched-0.75mm).
if [ -n "$THICK_OVERRIDE" ]; then
    if [ -n "$ONLY_DETECTOR" ]; then
        THICK[$ONLY_DETECTOR]="$THICK_OVERRIDE"
        echo "THICK override: ${ONLY_DETECTOR} -> ${THICK_OVERRIDE}"
    else
        for c in "${DETECTORS[@]}"; do THICK[$c]="$THICK_OVERRIDE"; done
        echo "THICK override: ALL detectors -> ${THICK_OVERRIDE}"
    fi
fi

if [ "$RUN_BARE" = "1" ]; then
    echo ""
    echo "############################################"
    echo "# Bare-detector intrinsic response runs"
    echo "############################################"

    for chip in "${DETECTORS[@]}"; do
        should_run_detector "$chip" || continue
        for energy in "${ENERGIES[@]}"; do
            should_run_energy "$energy" || continue
            write_and_run "bare" "$chip" "$energy" "$BARE_EVENTS" "0" "p2_bare_${chip}${OUTPUT_TAG}_${energy}keV"
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
                write_and_run "transport" "$chip" "$energy" "$VALIDATION_EVENTS" "$alloy" "p2_transport_${chip}_${alloy}_${energy}keV"
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
