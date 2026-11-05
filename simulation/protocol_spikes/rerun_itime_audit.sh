#!/bin/bash
# Re-run audit list with GenericPropagation integration_time = 1us (PH-12). Same configs, same seeds.
# Usage (repo root): docker compose run --rm -T --user 1000:1000 -e HOME=/tmp allpix bash /data/simulation/protocol_spikes/rerun_itime_audit.sh
set -uo pipefail
LIST=/data/simulation/protocol_spikes/rerun_list.txt
OUT=/data/output/audit_itime; mkdir -p $OUT
LOG=$OUT/rerun_log.csv; [ -f $LOG ] || echo "config,status,seconds" > $LOG
while read -r rel; do
  [ -z "$rel" ] && continue
  name=$(basename "$rel" .conf)
  [ -f "$OUT/$name.root" ] && continue   # resumable
  cfg="/data/${rel}"
  t0=$(date +%s)
  if allpix -c "$cfg" -o "GenericPropagation.integration_time=1us" -o root_file="$name" -o output_directory="$OUT" > "$OUT/$name.log" 2>&1 && [ -f "$OUT/$name.root" ]; then st=ok; else st=FAILED; fi
  echo "$rel,$st,$(( $(date +%s) - t0 ))" >> $LOG
done < "$LIST"
echo "done: $(grep -c ',ok,' $LOG) ok, $(grep -c FAILED $LOG) failed"
