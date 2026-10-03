# Person A firmware agents

Person A owns `firmware/**` and `fpga/**`. The ESP32 is real; delivery is digitally simulated (`DELIVERY_SIMULATED=1`). Do not implement or enable a physical pump actuator for this task.

Read `../CLAUDE.md`, `../docs/TEAM.md` (Person A), `../docs/PROTOCOL.md`, `../docs/SAFETY.md`, and the shared schemas before changing firmware. Use the existing firmware and safety briefs under `../.claude/agents/`.

When asked to execute Person A's work with agents, delegate disjoint files:

- Firmware engineer: `prescription.*`, `pump_controller.*`, and native controller tests.
- Transport engineer: `mqtt_link.*`; all WiFi/MQTT and serial output belongs on the network worker.
- Lead: configuration, ESP32 integration, simulated actuator/buttons, native demo, and documentation.
- Safety reviewer: independent read-only review after implementation, then re-review fixes.

Do not edit Person B/C/D's lane or change shared contracts. Report required simulator parity and contract changes as a handoff. The approved R1 choice for this implementation is `256dpi/MQTT` with QoS 1, as described in PRD R1 option (b); this supersedes the older PubSubClient-only firmware guideline for this lane.

Run `make fw-build`, `pio test -d firmware -e native`, then `pio run -d firmware -e native`, and `.venv/bin/python -m pytest firmware/test/test_digital.py` from the repo root. Run the repo's `make test` and `make lint`. Never claim physical checks have passed solely because native tests or compilation succeeded. Preserve the hard limits and all S1–S8 invariants.
