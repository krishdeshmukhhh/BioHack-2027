#!/usr/bin/env bash
# One-time setup on the Raspberry Pi (Raspberry Pi OS). Run from the repo root.
set -euo pipefail

sudo apt-get update
sudo apt-get install -y mosquitto mosquitto-clients python3-venv

# We run our own Mosquitto instance with scripts/mosquitto.conf (make broker),
# so stop the system service to free port 1883.
sudo systemctl disable --now mosquitto || true

make setup
[ -f .env ] || cp .env.example .env

echo "Done. Next: make broker, make hub, make sim (each in its own terminal)."
