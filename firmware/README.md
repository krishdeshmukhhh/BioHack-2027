# Person A: ESP32 with digital delivery

The ESP32 runs the real controller, WiFi, MQTT, buttons, and NVS persistence. Delivery is modelled from elapsed time and the accepted rate; no pump head is driven. `DELIVERY_SIMULATED=1` is required and every status/event carries `simulated: true`. Prototype/demo only, never connected to a person.

## Agents and ownership

The firmware engineer implements the portable parser/controller and native tests. The transport engineer implements the core-0 network worker. The lead integrates the ESP32 entry point, simulated actuator, buttons, and desktop harness. The safety reviewer independently reviews S1–S8. Existing briefs live in `.claude/agents/firmware-engineer.md` and `.claude/agents/safety-reviewer.md`; Codex instructions are in `firmware/AGENTS.md`.

## Implemented software

- Strict JSON, schema shape/date-time checks, pump identity, confirmation, versions, and compile-time limits, in protocol order.
- Idle-only apply, pending updates during a feed, persistence before `prescription_applied`, and silent replay of the current version.
- One controller state machine; simulated delivery advances only in running. Clearing an alarm enters paused and requires a separate resume action.
- One NVS key `current` in namespace `pump` stores the prescription and version together. Restore always boots idle and never automatically resumes delivery.
- QoS 1 prescription subscription, events, availability and Last Will; status every two seconds at QoS 0.
- WiFi/TCP/MQTT reconnect and serial output run on a separate FreeRTOS task. The delivery loop uses zero-wait queues, bounded input handling, and no `delay()`.
- Local event buffering reserves space for prescription outcomes and backpressures inbound prescriptions when full. Diagnostic state/alarm events can be dropped during extended outages; latest state/alarm remains in status. Buffers are volatile and finite, not a durable event journal.

R1 uses the documented `arduino-mqtt` alternative from `docs/research/PRD.md`: unlike PubSubClient, it can publish QoS 1, preserving `shared/protocol/topics.md` without additional status fields. Its constructor allocates the receive buffer before connection; no PubSubClient `setBufferSize()` is involved. Buffer capacity is 2048 bytes, covering the tested 200-character ASCII and UTF-8 emoji notes with demo metadata. Other protocol strings are unbounded; oversized packets are refused, never truncated. Highly escaped or unusually long metadata may exceed this transport limit.

## Build and run the digital checks

From the repo root:

```bash
make setup
.venv/bin/pip install platformio
export PATH="$PWD/.venv/bin:$PATH"
export PLATFORMIO_CORE_DIR="$PWD/firmware/.pio/core"
make fw-build
pio test -d firmware -e native
pio run -d firmware -e native
.venv/bin/python -m pytest firmware/test/test_digital.py
.venv/bin/python firmware/tools/demo.py
make test
make lint
```

Run `pio run -e native` **after** `pio test`: PlatformIO uses the same native executable path for the demo and Unity test runner. The offline demo exercises the same C++ core as the ESP32: v7 applies, delivery increases, v8 queues, v9 at 500 demo mL/hr rejects, occlusion stops delivery, clear pauses, resume continues, and stop applies v8 while idle. These are test values, not clinical guidance.

The native executable accepts JSON lines with `command`: `start`, `pause`, `resume`, `stop`, `occlusion`, `bag_empty`, `clear`, `status`, `tick` with `elapsed_ms`, or `prescription` with a JSON `payload`. Time advances explicitly through `tick`; this is a deterministic test harness, not the separate MQTT simulator in `sim/`. Output is `{topic,payload}` envelopes matching the shared protocol. Pass a file path as the first argument to persist prescriptions between desktop runs; omit it for an ephemeral test.

## Run on your ESP32

Copy `include/secrets.example.h` to `include/secrets.h` and enter your network/broker details locally. Confirm the ESP32 board and pins in `config.h` before uploading. Credentials are ignored by git; a missing secrets file permits compilation with nonfunctional example credentials.

```bash
make fw-upload
make fw-monitor
```

Serial monitor at 115200 baud accepts `start`, `pause`, `resume`, `stop`, `occlusion`, `bag_empty`, `clear`, `status`, and `reboot` (idle only). Use a newline after each command. Fault injection is therefore digital even without physical buttons. Reboot latches the controller idle while publishing retained offline; if offline cannot be acknowledged, the transport closes without MQTT DISCONNECT to preserve the Last Will.

Optional active-low buttons connect GPIO32 (occlusion), GPIO33 (bag empty), and GPIO27 (start/pause/resume/clear) to ground. A short pause-button release starts when idle, pauses when feeding, resumes when paused, or clears when alarmed. Hold for 1.5 seconds to cancel a feed and return idle; an alarm must first be cleared. GPIO25 can drive an LED with an appropriate series resistor as an activity indicator. The LED does not measure delivery. OLED, sensors, stepper calibration, and FPGA are unimplemented stretch work.

For standalone bench tests while the hub is under development, start the broker with `make broker`, observe `pump/#`, and explicitly confirm a fixed demo fixture:

```bash
.venv/bin/python firmware/tools/publish_demo.py --broker 192.168.1.10 --version 8 --rate 90 --confirmed-by care-01
```

Use a version newer than both current and pending. This helper is a test fixture injector with fixed demo identities; the hub remains responsible for the clinician/caregiver workflow. Broker acknowledgement means sent, and only pump telemetry proves applied or rejected. Use serial `start` after an idle apply; remote prescription updates do not start feeding.

## Remaining checks and team handoff

Hardware has not been flashed or bench-tested in this workspace. On the ESP32, verify broker messages validate, NVS survives restart, a 200-character note arrives, WiFi loss leaves delivery advancing at the accepted rate, occlusion stops delivery, clear remains paused, and power loss/graceful restart produces offline availability. Board-specific wiring is still unverified.

Person D must mirror the core behavior in `sim/pump_sim.py`, which is still a scaffold: strict shape/confirmation/date-time checks, replay/order/limits, pending apply at idle, clear-to-paused, explicit resume, and persistence before active reporting. Person B should consume the existing QoS 1 events and schema-valid status. Whole-system loop acceptance and simulator parity are not claimed here.

Protocol handoff: `event.schema.json` requires a positive `version` even for `malformed`. Completely unparseable or unversioned input is rejected without state change and logged locally; a version is never fabricated to reject an unrelated prescription. Versioned malformed objects do emit `prescription_rejected`. Person D should decide how unversioned diagnostics belong in the shared contract. No shared-schema changes were made in Person A's lane.
