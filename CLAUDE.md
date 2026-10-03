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

Run `make test` before saying a task is done. Run `make fw-build` after any firmware change.

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
- **Secrets** go in `.env` and `firmware/include/secrets.h`. Both are gitignored. Never print or commit them.

## Subagents

Defined in `.claude/agents/`. Use them for work inside their area.

- `firmware-engineer` ESP32 firmware
- `hub-engineer` hub API, database, MQTT bridge
- `web-engineer` clinician portal and family app
- `sim-engineer` pump simulator and demo data
- `safety-reviewer` read-only review against the safety invariants and the protocol. Run it before merging anything that touches prescriptions, limits, or the state machine.

## Parallel lanes

Work runs as one lead on `main` plus lane worktrees (`lane/hub`, `lane/sim`, `lane/web`, optional `lane/fw`), each owning only its folders. Read `docs/PARALLEL.md` before starting. If a `.lane` file exists at the repo root you are in a lane: edit only that lane's folders (enforced by `.claude/hooks/lane_guard.py`) and report contract changes to the lead instead of making them.

## Definition of done

- Tests pass (`make test`), firmware builds if touched.
- Protocol examples still validate.
- No safety invariant weakened; `safety-reviewer` run if relevant.
- The relevant line in `docs/PLAN.md` is ticked.
