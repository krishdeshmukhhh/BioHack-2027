# Smart Pump (Bio Hack 2026)

A prototype smart enteral feeding pump system: a clinician programs the pump remotely, a caregiver confirms the change, the pump applies it and reports back what it delivered.

**This is a hackathon prototype. It is not a medical device and must never be connected to a person.**

## What is in this repo

| Folder | What it is | Runs on |
|---|---|---|
| `firmware/` | Pump controller: state machine, safety limits, MQTT | ESP32 |
| `hub/` | Home hub: API, database, MQTT bridge, serves the web apps | Raspberry Pi (or a laptop) |
| `web/clinician/` | Clinician portal: prescriptions, exception dashboard | Browser |
| `web/family/` | Family app: confirm changes, progress, plain-language alerts | Browser (phone) |
| `sim/` | Software pump simulator and demo data generator | Laptop or Pi |
| `shared/protocol/` | JSON schemas for every MQTT message (the contract) | n/a |
| `fpga/` | Stretch goal: independent hardware safety watchdog | FPGA |
| `docs/` | Plan, architecture, protocol, safety, demo script | n/a |

## Quick start

```bash
make setup      # Python venv + dependencies
make broker     # start Mosquitto with our config
make hub        # start the hub on http://localhost:8000
make sim        # start a simulated pump (no hardware needed)
make test       # run all tests, including protocol example validation
```

Firmware (needs PlatformIO):

```bash
cp firmware/include/secrets.example.h firmware/include/secrets.h   # then edit
make fw-build
make fw-upload
```

Start with `docs/PLAN.md`, then `docs/TEAM.md` (who does what) and `docs/PARALLEL.md` (lanes and worktrees).
