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
