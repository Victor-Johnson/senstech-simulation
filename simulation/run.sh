#!/bin/bash
# =======================================================================
# Host-side wrapper for the Allpix2 simulation drivers.
#
# The drivers run INSIDE the container and cannot inspect their own image,
# so provenance that only exists on the host -- the image digest, the git
# revision of the driver -- has to be resolved here and forwarded in.
#
# Usage:
#   ./simulation/run.sh run_phase2_selection.sh
#   ONLY_DETECTOR=eiger2 THICK_OVERRIDE=1000um ./simulation/run.sh run_phase2_selection.sh
#
# Every environment variable the driver understands is passed through, so
# this is a drop-in replacement for:
#   docker compose run --rm allpix bash -c 'cd /data && bash ./simulation/<driver>'
# =======================================================================

set -euo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$REPO_ROOT"

if [ $# -lt 1 ]; then
    echo "usage: $0 <driver.sh> [args...]" >&2
    echo "" >&2
    echo "available drivers:" >&2
    ls -1 simulation/run_*.sh | grep -v 'simulation/run\.sh' | sed 's|simulation/|  |' >&2
    exit 2
fi

DRIVER=$1
shift

if [ ! -f "simulation/$DRIVER" ]; then
    echo "no such driver: simulation/$DRIVER" >&2
    exit 2
fi

# Resolve the image reference from docker-compose.yml, then its digest from the
# local image store. A floating tag still records WHICH digest actually ran.
IMAGE_REF=$(grep -oP '(?<=^\s{4}image:\s).*' docker-compose.yml | head -1 | tr -d '"'"'"' ')
IMAGE_DIGEST=$(docker image inspect --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}' \
    "$IMAGE_REF" 2>/dev/null || true)
: "${IMAGE_DIGEST:=unknown}"

DRIVER_GIT_REV=$(git rev-parse HEAD 2>/dev/null || echo unknown)
if ! git diff --quiet -- "simulation/$DRIVER" 2>/dev/null; then
    DRIVER_GIT_REV="${DRIVER_GIT_REV}-dirty"
fi
if ! git ls-files --error-unmatch "simulation/$DRIVER" >/dev/null 2>&1; then
    echo "WARNING: simulation/$DRIVER is not tracked in git." >&2
    echo "         Runs produced from it cannot be reproduced from a clone." >&2
    DRIVER_GIT_REV="untracked"
fi

echo "image   $IMAGE_REF"
echo "digest  $IMAGE_DIGEST"
echo "driver  $DRIVER @ $DRIVER_GIT_REV"
echo ""

exec docker compose run --rm \
    -e ALLPIX_IMAGE_REF="$IMAGE_REF" \
    -e ALLPIX_IMAGE_DIGEST="$IMAGE_DIGEST" \
    -e DRIVER_GIT_REV="$DRIVER_GIT_REV" \
    -e RANDOM_SEED \
    -e RESET_MANIFEST \
    -e DRY_RUN \
    -e RUN_BARE \
    -e RUN_VALIDATION \
    -e BARE_EVENTS \
    -e VALIDATION_EVENTS \
    -e ONLY_DETECTOR \
    -e ONLY_ENERGY \
    -e THICK_OVERRIDE \
    -e OUTPUT_TAG \
    -e GAP_MM \
    -e MOBILITY_MODEL \
    -e MOBILITY_ELECTRON \
    -e MOBILITY_HOLE \
    -e TRAPPING_TIME_ELECTRON \
    -e TRAPPING_TIME_HOLE \
    -e PROPAGATE_HOLES \
    -e WRITE_OBJECTS \
    -e TRANSPORT_ALLOYS \
    -e TRANSPORT_ENERGIES \
    -e VALIDATION_ENERGIES_OVERRIDE \
    allpix bash -c "cd /data && bash ./simulation/$DRIVER $*"
