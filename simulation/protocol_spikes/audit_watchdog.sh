#!/bin/bash
# Host-side watchdog for the integration-time audit: kill any allpix process older than LIMIT seconds in the
# audit container (single-event hangs with 1 us integration; allpix ignores SIGTERM while an event runs -> SIGKILL), move its partial ROOT file aside, log it.
C=$1; LIMIT=${LIMIT:-1800}; R=$(cd "$(dirname "$0")/../.." && pwd); H=$R/data/audit_itime/hung; mkdir -p $H
while docker ps --format '{{.Names}}' | grep -q "^$C$"; do
  docker exec $C ps -o pid=,etimes=,args= -C allpix 2>/dev/null | while read -r pid et args; do
    if [ "$et" -gt "$LIMIT" ]; then
      name=$(echo "$args" | grep -oE 'root_file=[^ ]+' | cut -d= -f2)
      docker exec $C kill -9 "$pid"; sleep 5
      mv "$R/data/audit_itime/$name.root" "$H/" 2>/dev/null
      echo "$(date -Is),$name,killed after ${et}s" >> $H/watchdog_log.csv
    fi
  done
  sleep 60
done
