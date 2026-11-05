#!/bin/bash
# Run mctrack_depths on every <name>_objects.root of a Stage B campaign -> <name>_depths.csv (skips existing).
# Usage (inside the allpix container): bash depths_campaign.sh <campaign>
D=/data/output/protocol_runs/stageB/$1
cd /tmp
for f in "$D"/*_objects.root; do
  out="${f%_objects.root}_depths.csv"
  [ -f "$out" ] && continue
  /data/output/protocol_runs/bin/mctrack_depths "$f" "$out.tmp" && mv "$out.tmp" "$out" || echo "FAILED $f"
done
