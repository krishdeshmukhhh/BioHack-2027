---
paths:
  - "hub/**"
---

# Hub rules (Python, FastAPI, SQLite)

- Python 3.11, type hints on public functions, `ruff` clean.
- Use the standard library `sqlite3` module. No ORM. Schema lives in `hub/app/schema.sql`.
- Prescription lifecycle states: `proposed`, `confirmed`, `sent`, `active`, `rejected`, `superseded`. Only the MQTT ingest path may set `active` or `rejected`, based on pump telemetry or events (S5).
- Publishing a prescription requires a stored caregiver confirmation (S2). Enforce it in one function and test it.
- Every state change writes an audit row: who, what, when, old value, new value (S7). No update or delete statements on the audit table.
- Validate all MQTT payloads against `shared/protocol/` schemas.
- Publish prescriptions retained with QoS 1 so a pump that reconnects gets the latest one.
- The hub must run with no internet. No cloud SDKs, no CDN links.
- Each endpoint gets at least one pytest test. Test the unhappy paths for the prescription flow (unconfirmed, out of range, stale version, pump offline).
- Read config from environment variables (see `.env.example`).
