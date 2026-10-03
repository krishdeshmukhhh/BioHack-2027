# Hub (Raspberry Pi)

The only thing the web apps talk to, and the bridge to the pump over MQTT. Runs with no internet.

Planned modules:

- `app/main.py`: FastAPI app, serves `web/` as static files
- `app/schema.sql`: SQLite tables (patients, prescriptions, status samples, events, audit)
- `app/db.py`: connection and queries, standard library `sqlite3`
- `app/mqtt_bridge.py`: subscribe to status, event, availability; publish prescriptions
- `app/prescriptions.py`: lifecycle (proposed, confirmed, sent, active, rejected, superseded) and the single publish gate (S2)
- `app/audit.py`: append-only audit log (S7)
- `app/reports.py`: daily totals, exceptions, weekly summary
- `app/live.py`: server-sent events for the web apps

Run with `make hub`. Test with `make test`.

## Demo reset and the Pi

- `python -m hub.reset` (hub stopped): moves the database to `hub/data/archive/` (audit rows kept, S7) and clears the retained prescription for `PUMP_ID`, so a pump reset to v7 is not handed the last demo's prescription. Then start the hub and `python -m sim.pump_sim --demo-seed` (no old `--state-file`), and wait for the pump to show online at v7 before proposing.
- `hub/deploy/install_services.sh [hostname]` (on the Pi, after `scripts/setup_pi.sh`): systemd services for the broker and the hub that start on boot, plus an optional `.local` hostname.
