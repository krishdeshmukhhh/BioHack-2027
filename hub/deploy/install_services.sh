#!/usr/bin/env bash
# Pi only (Raspberry Pi OS). Start the broker and the hub on boot with systemd.
# Prototype demo setup, not a hardened deployment. Run from the repo root after
# scripts/setup_pi.sh:
#
#   hub/deploy/install_services.sh                 # keep the current hostname
#   hub/deploy/install_services.sh smartpump       # also set it: http://smartpump.local:8000
#
# Undo: sudo systemctl disable --now smart-pump-hub smart-pump-broker
set -euo pipefail

REPO="$(pwd)"
RUN_AS="$(id -un)"
[ -f "$REPO/hub/app/main.py" ] || { echo "run from the repo root" >&2; exit 1; }
[ -x "$REPO/.venv/bin/python" ] || { echo "no .venv: run scripts/setup_pi.sh first" >&2; exit 1; }
[ -f "$REPO/.env" ] || cp "$REPO/.env.example" "$REPO/.env"
mkdir -p "$REPO/.mosquitto" "$REPO/hub/data"

if [ $# -ge 1 ]; then
    sudo hostnamectl set-hostname "$1"
    sudo apt-get install -y avahi-daemon  # answers <name>.local on the demo network
fi

# The broker's persistence path in scripts/mosquitto.conf is relative, so it runs
# from the repo root, exactly like `make broker`.
sudo tee /etc/systemd/system/smart-pump-broker.service >/dev/null <<EOF
[Unit]
Description=Smart pump prototype: Mosquitto broker
After=network.target

[Service]
User=$RUN_AS
WorkingDirectory=$REPO
ExecStart=/usr/sbin/mosquitto -c scripts/mosquitto.conf
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

# Same as `make hub` without --reload.
sudo tee /etc/systemd/system/smart-pump-hub.service >/dev/null <<EOF
[Unit]
Description=Smart pump prototype: hub
After=network.target smart-pump-broker.service
Wants=smart-pump-broker.service

[Service]
User=$RUN_AS
WorkingDirectory=$REPO
Environment=HUB_PORT=8000
EnvironmentFile=$REPO/.env
ExecStart=/bin/sh -c 'exec $REPO/.venv/bin/python -m uvicorn hub.app.main:app --host 0.0.0.0 --port \$HUB_PORT'
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl disable --now mosquitto 2>/dev/null || true  # frees port 1883
sudo systemctl daemon-reload
sudo systemctl enable --now smart-pump-broker smart-pump-hub

echo "Running. Logs: journalctl -u smart-pump-hub -f"
echo "Portal: http://$(hostname).local:8000/clinician/  Family: http://$(hostname).local:8000/family/"
echo "Demo reset: sudo systemctl stop smart-pump-hub && make reset-demo && sudo systemctl start smart-pump-hub"
