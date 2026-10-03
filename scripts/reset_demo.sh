#!/usr/bin/env bash
# Reset to the DEMO.md starting state between rehearsals: a fresh hub database, no
# retained prescription on the broker, and history dated to end today. Then start the
# hub and the pump again (see the message at the end).
#
#   make reset-demo        (reads .env through the Makefile)
#
# Run with the broker up and the hub and simulator stopped. The old hub database is
# moved to hub/data/archive/, never deleted: the audit log is append-only (S7).
# Demo data only; nothing here touches a real pump's limits or confirmation rules.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

MQTT_HOST="${MQTT_HOST:-localhost}"
MQTT_PORT="${MQTT_PORT:-1883}"
PUMP_ID="${PUMP_ID:-pump-001}"
HUB_DB_PATH="${HUB_DB_PATH:-hub/data/hub.sqlite3}"
PY="${PY:-.venv/bin/python}"

die() { echo "reset_demo: $*" >&2; exit 1; }

if pgrep -f "uvicorn hub.app.main" >/dev/null; then
  die "the hub is running. Stop it first (Ctrl+C in its terminal); it holds the database open."
fi
if pgrep -f "sim.pump_sim" >/dev/null; then
  die "a simulator is running. Quit it first (q in its terminal), so it publishes offline."
fi
command -v mosquitto_pub >/dev/null || die "mosquitto_pub not found (apt install mosquitto-clients)"

# 1. Archive the hub database (and its WAL files) instead of deleting it.
if [[ -f "$HUB_DB_PATH" ]]; then
  archive="$(dirname "$HUB_DB_PATH")/archive"
  stamp="$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$archive"
  for f in "$HUB_DB_PATH" "$HUB_DB_PATH-wal" "$HUB_DB_PATH-shm"; do
    if [[ -f "$f" ]]; then mv "$f" "$archive/$(basename "$f").$stamp"; fi
  done
  echo "+ hub database archived to $archive/ ($stamp)"
else
  echo "= no hub database at $HUB_DB_PATH"
fi

# 2. Remove the retained prescription, so the pump is not handed the last rehearsal's
#    version on connect. An empty retained message deletes it; it is not a prescription.
mosquitto_pub -h "$MQTT_HOST" -p "$MQTT_PORT" -t "pump/$PUMP_ID/prescription" -r -n \
  || die "could not reach the broker at $MQTT_HOST:$MQTT_PORT. Is make broker running?"
echo "+ retained prescription cleared on pump/$PUMP_ID/prescription"

# 3. History that ends today, so the dashboard's "last 3 days" rules line up.
"$PY" -m sim.generate_history
echo

cat <<EOF
Reset done. Now start, each in its own terminal:
  make hub
  python -m sim.pump_sim --demo-seed     (simulated pump: v7 at 60 mL/hr, idle)
For the ESP32 instead of the simulator: its prescription lives in NVS, so it keeps
its last version after a rehearsal. The hub numbers the next proposal above whatever
the pump reports, so the loop still works; to show "v7" again, Person A resets NVS.
EOF
