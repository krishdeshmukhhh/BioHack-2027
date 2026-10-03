# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Smart Pump (Bio Hack 2026)

Prototype smart enteral feeding pump system for families tube feeding at home. Hackathon project: optimise for a reliable live demo, not for production.

**Not a medical device. Never connect to a person. All patient data is fictional.**

## The one idea

A closed loop. Remote programming goes down to the pump, telemetry comes back up and proves the change took effect.

1. Clinician proposes a prescription in the portal.
2. Caregiver confirms it in the family app.
3. Hub publishes the confirmed prescription to the pump.
4. Pump checks it against hard limits, applies it in a safe state, and reports the new version in its status.
5. Portal shows "active on pump" only after that status arrives.

## Architecture

```
web/clinician  ─┐                       ┌─ firmware (ESP32 pump)
                ├─ HTTP ─ hub (Pi) ─ MQTT ┤
web/family     ─┘        SQLite          └─ sim (software pump)
```

- **Hub** is the only thing the web apps talk to. Web apps never speak MQTT.
- **Pump** (real or simulated) only speaks MQTT. It never talks HTTP.
- **Simulator** must behave exactly like the firmware on the wire, so the software team is never blocked on hardware.

Where the invariants are enforced (read these before touching the prescription flow):
- `hub/app/prescriptions.py`: lifecycle (proposed, confirmed, sent, active, rejected, superseded). `publish_prescription` is the single publish gate and refuses anything without a stored confirmation (S2).
- `hub/app/service.py`: `handle_message()` is the only MQTT ingest path and the only caller of the pump-driven lifecycle functions, so only pump data can set active/rejected/superseded (S5).
- `hub/app/mqtt_bridge.py`: paho runs in its own thread and hands messages to the asyncio loop with `call_soon_threadsafe`. `hub/app/live.py` fans updates out to SSE clients.
- Status is authoritative, events are the fast path. Events are QoS 1 (may arrive twice, so the hub dedups) and can be lost while offline; every outcome is also in status (`prescription_version`, `pending_version`, `last_rejected_version`, `alarm`). Topics and QoS: `shared/protocol/topics.md`.
- `sim/pump_sim.py`: `PumpCore` is the pump logic with no I/O (validation, S3/S4 queueing, state machine); `MqttLink` wraps it in paho. Tests and `web/_mock` drive `PumpCore` directly.

## Layout

- `firmware/` ESP32, PlatformIO, Arduino framework, C++
- `hub/` Python 3.11, FastAPI, paho-mqtt, SQLite
- `web/clinician/`, `web/family/` static HTML, CSS, vanilla JS, served by the hub. No build step.
- `sim/` Python pump simulator and 30-day history generator
- `shared/protocol/` JSON Schemas and example messages. This is the contract.
- `fpga/` stretch: hardware watchdog
- `docs/` PLAN, ARCHITECTURE, PROTOCOL, SAFETY, DEMO, PITCH (talk and slides outline), API (hub HTTP/SSE contract), PARALLEL (lanes and worktrees), TEAM (4-person split)
- `docs/research/` PRD, Mermaid architecture diagrams, references with documentation excerpts

## Commands

```bash
make setup       # venv + deps
make broker      # Mosquitto with scripts/mosquitto.conf
make hub         # FastAPI on :8000 with reload
make sim         # simulated pump
make history     # generate 30 days of fictional history
make test        # pytest (hub, sim, protocol examples)
make lint        # ruff
make fw-build    # pio run
make fw-upload   # flash the ESP32
make fw-monitor  # serial monitor
```

The Makefile includes and exports `.env` (copy from `.env.example`: `MQTT_HOST`, `HUB_PORT`, `HUB_DB_PATH`, `PUMP_ID`). Firmware needs `firmware/include/secrets.h` copied from `secrets.example.h`. `make lanes` / `make lanes-status` create and inspect the lane worktrees (`scripts/worktrees.sh`).

Run `make test` before saying a task is done. Run `make fw-build` after any firmware change.

Single test: `.venv/bin/python -m pytest sim/test_pump_sim.py::test_apply_in_idle` (or `-k pattern`). Test paths are set in `pyproject.toml` (`hub/tests`, `shared/protocol`, `sim`, `web/_mock`).

Useful sim flags (`python -m sim.pump_sim --help`): `--speed 60` compresses feed time, `--demo-seed` starts from the `docs/DEMO.md` reset state, `--scenario <name>` runs a scripted rehearsal (`--list-scenarios`), `--state-file` persists the applied prescription like NVS.

Web work without the hub or a broker: `python web/_mock/mock_api.py` (stdlib only, http://localhost:8003, `--speed 60`) fakes the `docs/API.md` contract over real `PumpCore` pumps; `/_mock/` has controls for feeds, faults, and wifi drop.

No `make` (e.g. Windows): the Makefile targets are one-liners, so run them directly. On Windows the venv interpreter is `.venv/Scripts/python`, not `.venv/bin/python`, e.g. `.venv/Scripts/python -m pytest`, `-m ruff check .`, `-m uvicorn hub.app.main:app --reload`, `-m sim.pump_sim`.

Testing notes:
- Unit tests need no broker: MQTT is exercised with fake paho clients (see `sim/test_pump_sim_mqtt.py`). Only `make sim`/`make hub` against a real pump need Mosquitto running.
- `sim/test_limits_match_firmware.py` parses `firmware/include/limits.h` and asserts the simulator's `LIMIT_*` constants match. Changing a limit means changing both.
- `shared/protocol/test_examples.py` validates every file in `shared/protocol/examples/` against its schema, matched by filename prefix (`status.running.json` → `status.schema.json`). New examples must follow that naming.
- Windows: two protocol-case tests fail because `read_text()` without `encoding="utf-8"` decodes `shared/protocol/cases/prescription_cases.json` as cp1252. Set `PYTHONUTF8=1` until the fix (`encoding="utf-8"`) lands in `shared/protocol/test_examples.py` and `sim/test_protocol_cases.py`.

Current status and next steps per person: checkboxes in `docs/TEAM.md` and `docs/PLAN.md`; the hub lane keeps a detailed hand-off in `hub/NEXT_STEPS.md` (on `lane/hub`).

## Safety invariants (never weaken these)

Full text in `docs/SAFETY.md`. Short form:

- **S1** Hard limits live in `firmware/include/limits.h`. Out-of-range prescriptions are rejected and reported, never clamped silently.
- **S2** The hub never publishes a prescription that has no caregiver confirmation. The pump rejects one that lacks `confirmed_by`.
- **S3** Prescription versions only go up. The pump ignores a version less than or equal to its current one.
- **S4** A new prescription is applied only when the pump is idle. If a feed is running it is queued, not applied mid-feed.
- **S5** The portal shows a prescription as active only after the pump reports that version in telemetry.
- **S6** Losing wifi never stops or changes a feed. The pump keeps running the last accepted prescription.
- **S7** The audit log is append-only.
- **S8** Simulated data is always labelled as simulated, in the data and on screen.

If a task seems to require breaking one of these, stop and ask.

## Working agreements

- **Protocol first.** Any change to a message starts in `shared/protocol/`, with an updated example, then firmware, sim, and hub follow. See `docs/PROTOCOL.md`.
- **Firmware and sim stay in step.** A behaviour change in one needs the same change in the other in the same piece of work.
- **Small, demoable steps.** Follow the phases in `docs/PLAN.md`. Finish a phase's acceptance check before starting the next.
- **Keep it simple.** No frameworks, build tools, ORMs, or cloud services unless the plan says so. The demo must run on a Pi with no internet.
- **Accessibility is a deliverable, not polish.** Family app rules are in `.claude/rules/web.md`.
- Per-area rules live in `.claude/rules/` (`firmware.md`, `hub.md`, `protocol.md`, `web.md`, `safety.md`). Read the one for the area you are editing.
- **Secrets** go in `.env` and `firmware/include/secrets.h`. Both are gitignored. Never print or commit them.

## Subagents

Defined in `.claude/agents/`. Use them for work inside their area.

- `firmware-engineer` ESP32 firmware
- `hub-engineer` hub API, database, MQTT bridge
- `web-engineer` clinician portal and family app
- `sim-engineer` pump simulator and demo data
- `safety-reviewer` read-only review against the safety invariants and the protocol. Run it before merging anything that touches prescriptions, limits, or the state machine.

## Parallel lanes

Work runs as one lead on `main` plus lane worktrees (`lane/hub`, `lane/sim`, `lane/web`, optional `lane/fw`), each owning only its folders. Read `docs/PARALLEL.md` before starting. If a `.lane` file exists at the repo root you are in a lane: edit only that lane's folders (enforced by `.claude/hooks/lane_guard.py`) and report contract changes to the lead instead of making them. The guard only covers Edit/Write, so don't use shell redirects to get around it. All lanes share one broker; each uses its own `PUMP_ID` so their topics never cross.

## Definition of done

- Tests pass (`make test`), firmware builds if touched.
- Protocol examples still validate.
- No safety invariant weakened; `safety-reviewer` run if relevant.
- The relevant line in `docs/PLAN.md` is ticked.
