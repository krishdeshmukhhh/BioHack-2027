#!/usr/bin/env bash
# Docker version of scripts/reset_demo.sh: back to the DEMO.md starting state.
#
#   make docker-reset
#
# Stops the hub and any simulator, archives the hub database inside its volume
# (never deleted: the audit log is append-only, S7), clears the retained
# prescription on the broker, and starts the hub again (which regenerates the
# history so it ends today). Then start the pump: the ESP32, or make docker-sim.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
PUMP_ID="${PUMP_ID:-pump-001}"

docker compose --profile sim stop hub sim >/dev/null
docker compose up -d broker >/dev/null

# 1. Archive the database inside the hub-data volume.
docker compose run --rm --no-deps --entrypoint sh hub -c '
  stamp=$(date +%Y%m%d-%H%M%S)
  mkdir -p /data/archive
  for f in /data/hub.sqlite3 /data/hub.sqlite3-wal /data/hub.sqlite3-shm; do
    if [ -f "$f" ]; then mv "$f" "/data/archive/$(basename "$f").$stamp"; fi
  done
  echo "+ hub database archived to /data/archive ($stamp)"
'

# 2. Remove the retained prescription. An empty retained message deletes it; it is
#    not a prescription.
docker compose exec -T broker mosquitto_pub -t "pump/$PUMP_ID/prescription" -r -n
echo "+ retained prescription cleared on pump/$PUMP_ID/prescription"

# 3. Start the hub again; it regenerates the history on start.
docker compose up -d hub >/dev/null
echo "+ hub started"
echo
echo "Reset done. Start the pump: the ESP32, or make docker-sim (v7 at 60 mL/hr, idle)."
