# Person A: ESP32 with digital delivery

The ESP32 runs the real controller, WiFi, MQTT, buttons, and NVS persistence. Delivery is modelled from elapsed time and the accepted rate; no pump head is driven. `DELIVERY_SIMULATED=1` is required and every status/event carries `simulated: true`. Prototype/demo only, never connected to a person.

## Start without WiFi or a broker

After uploading this firmware, open the serial monitor at 115200 baud. Enter each command followed by Enter:

```text
demo
start
status
occlusion
clear
resume
stop
```

`demo` explicitly loads a fictional, confirmed local test prescription while idle (60 demo mL/hr, target 5 mL), using a version newer than the current version. It never starts delivery automatically and cannot replace an active or pending prescription. `start` begins digital delivery; status reports an increasing `delivered_ml` every two seconds (about 1 mL after a minute running). `occlusion` stops it, `clear` leaves it paused, `resume` continues, and `stop` returns idle. These are test values, not clinical guidance. WiFi/broker credentials are needed only for MQTT integration.

To display typed commands and send complete lines, use:

```bash
pio device monitor --baud 115200 --echo --filter send_on_enter
```

Exit a running monitor with Ctrl+C before uploading again. A banner reading `smart-pump firmware scaffold` and only `state=idle` means the old scaffold was uploaded; rebuild/upload this version. The new banner says `ESP32 with simulated delivery` and explains `demo` then `start`.

## Agents and ownership

The firmware engineer implements the portable parser/controller and native tests. The transport engineer implements the core-0 network worker. The lead integrates the ESP32 entry point, simulated actuator, buttons, and desktop harness. The safety reviewer independently reviews S1–S8. Existing briefs live in `.claude/agents/firmware-engineer.md` and `.claude/agents/safety-reviewer.md`; Codex instructions are in `firmware/AGENTS.md`.

## Implemented software

- Strict JSON, schema shape/date-time checks, pump identity, confirmation, versions, and compile-time limits, in protocol order.
- Idle-only apply, pending updates during a feed, persistence before `prescription_applied`, and silent replay of both current and pending versions.
- Rejections repeat `last_rejected_version` and `last_reject_reason` in status, so a lost event can be recovered. Replay never sets or changes those fields.
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

The native harness also accepts `demo`, using the same fixture helper as the ESP32 serial command. Native Unity tests consume all 55 current cases directly from `shared/protocol/cases/prescription_cases.json`, checking parser, events, and status. They also check rejection telemetry survives later replay, queue, apply, and dropped malformed input. For an isolated build outside this repo, set `FIRMWARE_PROTOCOL_CASES` to that file's absolute path.

## Run on your ESP32

Copy `include/secrets.example.h` to `include/secrets.h` and enter your network/broker details locally. Confirm the ESP32 board and pins in `config.h` before uploading. Credentials are ignored by git; a missing secrets file permits compilation with nonfunctional example credentials.

```bash
make fw-upload
make fw-monitor
```

Serial monitor at 115200 baud accepts `demo`, `start`, `pause`, `resume`, `stop`, `occlusion`, `bag_empty`, `clear`, `status`, and `reboot` (idle only). Use a newline after each command. Fault injection is therefore digital even without physical buttons. Reboot latches the controller idle while publishing retained offline; if offline cannot be acknowledged, the transport closes without MQTT DISCONNECT to preserve the Last Will.

Optional active-low buttons connect GPIO32 (occlusion), GPIO33 (bag empty), and GPIO27 (start/pause/resume/clear) to ground. A short pause-button release starts when idle, pauses when feeding, resumes when paused, or clears when alarmed. Hold for 1.5 seconds to cancel a feed and return idle; an alarm must first be cleared. GPIO25 can drive an LED with an appropriate series resistor as an activity indicator. The LED does not measure delivery. OLED, sensors, stepper calibration, and FPGA are unimplemented stretch work.

For standalone bench tests while the hub is under development, start the broker with `make broker`, observe `pump/#`, and explicitly confirm a fixed demo fixture:

```bash
.venv/bin/python firmware/tools/publish_demo.py --broker 192.168.1.10 --version 8 --rate 90 --confirmed-by care-01
```

Use a version newer than both current and pending. This helper is a test fixture injector with fixed demo identities; the hub remains responsible for the clinician/caregiver workflow. Broker acknowledgement means sent, and only pump telemetry proves applied or rejected. Use serial `start` after an idle apply; remote prescription updates do not start feeding.

## Remaining checks and team handoff

Hardware has not been flashed or bench-tested in this workspace. On the ESP32, verify broker messages validate, NVS survives restart, a 200-character note arrives, WiFi loss leaves delivery advancing at the accepted rate, occlusion stops delivery, clear remains paused, and power loss/graceful restart produces offline availability. Board-specific wiring is still unverified.

Firmware now matches the simulator on all 55 shared prescription cases, including the pending replay that caused commit `e091d59` to revert the earlier firmware merge. Both status and event fields follow the current contract. Completion returns idle after five seconds; alarm status reports rate zero; alarm and clear events precede their state changes. Person B can consume the existing QoS 1 events and rejection recovery fields. Whole-system ESP32 loop acceptance and timing parity on real hardware still require bench checks.

Digital fault commands apply only while running or paused, as in the simulator. The shared fixture covers prescription behavior, not every hardware failure. Persistence failures remain a deliberate difference: firmware preserves the old applied version, keeps the new one pending, and refuses to start until it can persist; the simulator currently logs a failed file write after applying. Person D should align that failure path without weakening the firmware's persistence gate.

`event.schema.json` requires a positive `version` even for `malformed`. Completely unparseable or unversioned input is dropped without state change and logged locally; a version is never fabricated to reject an unrelated prescription. Versioned malformed objects emit `prescription_rejected`, including a readable version alongside an unrepresentably large rate. This follows the current protocol and shared cases. No shared-schema changes were made in Person A's lane.
