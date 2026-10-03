# Person A: ESP32 with digital delivery

The ESP32 runs the real controller, WiFi, MQTT, buttons, and NVS persistence. Delivery is modelled from elapsed time and the accepted rate; no pump head is driven. `DELIVERY_SIMULATED=1` is required and every status/event carries `simulated: true`. Prototype/demo only, never connected to a person.

## Start without WiFi or a broker

Upload the explicitly offline environment from the repo root, then open the serial monitor at 115200 baud:

```bash
pio run -d firmware -e esp32dev_offline -t upload
pio device monitor --baud 115200 --echo --filter send_on_enter
```

Enter each command followed by Enter:

```text
demo
start
status
occlusion
clear
resume
stop
```

`demo` exists only in `esp32dev_offline`. That build disables WiFi/MQTT and stores local prescriptions in the separate `pump-bench` NVS namespace, so local versions cannot reach the hub or replace its stored prescription. It explicitly loads a fictional, confirmed local test prescription while idle (60 demo mL/hr, target 5 mL), using a version newer than the current version. It never starts delivery automatically and cannot replace an active or pending prescription. `start` begins digital delivery; status reports an increasing `delivered_ml` every two seconds (about 1 mL after a minute running). `occlusion` stops it, `clear` leaves it paused, `resume` continues, and `stop` returns idle. These are test values, not clinical guidance.

To display typed commands and send complete lines, use:

```bash
pio device monitor --baud 115200 --echo --filter send_on_enter
```

Exit a running monitor with Ctrl+C before uploading again. A banner reading `smart-pump firmware scaffold` and only `state=idle` means the old scaffold was uploaded; rebuild/upload this version. Current firmware prints `ESP32 with simulated delivery` followed by its offline or hub mode. Hub builds require a caregiver-confirmed prescription from the hub before `start`.

## Agents and ownership

The firmware engineer implements the portable parser/controller and native tests. The transport engineer implements the core-0 network worker. The lead integrates the ESP32 entry point, simulated actuator, buttons, and desktop harness. The safety reviewer independently reviews S1–S8. Existing briefs live in `.claude/agents/firmware-engineer.md` and `.claude/agents/safety-reviewer.md`; Codex instructions are in `firmware/AGENTS.md`.

## Implemented software

- Strict JSON, schema shape/date-time checks, pump identity, confirmation, versions, and compile-time limits, in protocol order.
- Idle-only apply, pending updates during a feed, persistence before `prescription_applied`, and silent replay of both current and pending versions.
- Rejections repeat `last_rejected_version` and `last_reject_reason` in status, so a lost event can be recovered. Replay never sets or changes those fields.
- One controller state machine; simulated delivery advances only in running. Clearing an alarm enters paused and requires a separate resume action.
- One NVS key `current` stores the prescription and version together: namespace `pump` for hub builds and `pump-bench` for offline checks. Restore always boots idle and never automatically resumes delivery.
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

Serial monitor at 115200 baud accepts `start`, `pause`, `resume`, `stop`, `occlusion`, `bag_empty`, `clear`, `status`, and `reboot` (idle only). `demo` additionally exists in `esp32dev_offline`. Use a newline after each command. Fault injection is therefore digital even without physical buttons. Hub-mode reboot latches the controller idle while publishing retained offline; if offline cannot be acknowledged, the transport closes without MQTT DISCONNECT to preserve the Last Will.

Optional active-low buttons connect GPIO32 (occlusion), GPIO33 (bag empty), and GPIO27 (start/pause/resume/clear) to ground. A short pause-button release starts when idle, pauses when feeding, resumes when paused, or clears when alarmed. Hold for 1.5 seconds to cancel a feed and return idle; an alarm must first be cleared. GPIO25 can drive an LED with an appropriate series resistor as an activity indicator. The LED does not measure delivery. OLED, sensors, stepper calibration, and FPGA are unimplemented stretch work.

For standalone bench tests with **no hub running**, start the broker with `make broker`, observe `pump/#`, and send a fixed demo fixture (not retained, identity `bench-test`):

```bash
.venv/bin/python firmware/tools/publish_demo.py --bench-only --broker 192.168.1.10 --version 8 --rate 90
```

Use a version newer than both current and pending. This helper is a test fixture injector that bypasses the hub's publish gate (S2), so it is bench only; run `make reset-demo` before the hub is used again. The hub remains responsible for the clinician/caregiver workflow. Broker acknowledgement means sent, and only pump telemetry proves applied or rejected. Use serial `start` after an idle apply; remote prescription updates do not start feeding.

## Phase 3 results and team handoff

Person A's Phase 3 acceptance passed on a real ESP32 on 2026-10-03 with digitally simulated delivery and serial fault injection. Actual reports and their scope are indexed in [phase3/README.md](phase3/README.md): ten offline controller checks, thirteen hub/MQTT checks, eleven WiFi-loss checks, seven normal-firmware bag-empty checks, rendered app checks, and the clinician-form/family-confirmation click-through.

The confirmed 200-character note reached the ESP32; excessive rates rejected; pending updates waited for idle; replay was silent; alarms stopped delivery and cleared to paused; NVS survived reboot; and availability went offline/online correctly. During an actual 30-second ESP32 WiFi disconnection, v4 continued at 75 mL/hr and modelled volume increased by 0.625 mL. The Mac's network was unchanged. The normal `esp32dev` profile is restored, and the final UI-confirmed v5 prescription is 90 mL/hr with a 5 mL target, idle. The UI-confirmed v6 at 500 mL/hr was rejected. These are fictional test values.

Physical button wiring, OLED, sensors, measured fluid delivery, and pump calibration were not tested; the user selected digital simulation. Person D can use the evidence to update the shared Phase 3 checklist and decide the hardware-loop tag. Shared documents and other lanes were not edited.

## Connected bench without a router

`esp32dev_ap` creates a password-protected private WiFi network at `192.168.4.1`. It accepts one station and discovers that station's DHCP address as the broker address. The Mac runs Mosquitto and the hub locally; they do not require internet. This profile uses the hub's `pump` NVS namespace and has no local `demo` command. The default `esp32dev` profile continues to join a configured WiFi network.

Put `BENCH_AP_SSID` and `BENCH_AP_PASSWORD` in ignored `include/secrets.h`; the password must contain 8–63 bytes. This workspace has privately generated credentials there. Keep the password local. Compile/upload from the repo root:

```bash
pio run -d firmware -e esp32dev_ap -t upload --upload-port /dev/cu.usbserial-120
```

The startup line `ESP32 private test network ready` confirms that the board created the AP. Joining `BioHack-ESP32-Bench` on the Mac temporarily disconnects its existing WiFi internet connection. Join manually only when ready, using the password from the local file, then return to the usual network after testing. Firmware and the bench helpers never switch the Mac's WiFi themselves. Keep USB attached and close serial monitors before running a helper.

For a fresh connected bench, run the broker with `scripts/mosquitto.conf` (listens on all interfaces), and the hub with an isolated database so existing demo data and audit history are preserved:

```bash
mkdir -p .mosquitto /tmp/biohack-phase3
mosquitto -c scripts/mosquitto.conf
# In another terminal:
HUB_DB_PATH=/tmp/biohack-phase3/hub.sqlite3 MQTT_HOST=127.0.0.1 MQTT_PORT=1883 \
  PUMP_ID=pump-001 .venv/bin/python -m uvicorn hub.app.main:app \
  --host 0.0.0.0 --port 8000
```

If those services are already running, use the existing instances. Open `http://localhost:8000` for the apps. Wait for fresh ESP32 telemetry before proposing a prescription: older firmware may have stored a version under `pump`, and the hub's allocator uses the reported version to choose the next one.

After joining the network, run the connected helper, then press the ESP32 reset button when it starts listening:

```bash
.venv/bin/python firmware/tools/network_bench.py --port /dev/cu.usbserial-120 \
  --hub http://127.0.0.1:8000 --broker 127.0.0.1 \
  --output /tmp/esp32-network-bench.json
```

It requires a hub-mode startup marker, simulated telemetry, and an initially idle pump with no alarm or pending prescription. Through the real HTTP/MQTT path it proposes a fictional 90 mL/hr prescription with a 200-character note, confirms it as the demo caregiver, checks pump acknowledgement, replays the exact confirmed MQTT payload, and confirms a 500 mL/hr case that the ESP32 must reject. It starts digital delivery, queues a new 75 mL/hr version without changing the running feed, checks pause/alarm/clear/resume, stops to apply the pending update, and verifies NVS and ordered offline/online availability across an idle reboot. It ends idle after success. It creates test prescriptions and audit entries in the selected hub database; use the isolated Phase 3 database above. Defaults limit the run to three minutes and individual waits to 15 seconds.

The connected helper does not disconnect WiFi or stop the broker; `wifi_loss` is explicitly `not_run`. Run the separate device WiFi interruption check below for S6. Do not mark Phase 3 complete solely from a successful connected-helper report.

```bash
.venv/bin/python -m pytest firmware/test/test_network_bench.py
```

## Device WiFi interruption check

The `esp32dev_network_test` profile joins the configured router using the private `WIFI_SSID`, `WIFI_PASSWORD`, `MQTT_HOST`, and `MQTT_PORT` in `include/secrets.h`. It adds only the bench commands `wifi_off` and `wifi_on`. Those commands queue atomic requests; the network worker changes the ESP32 station connection, while the delivery loop continues. This profile cannot be combined with offline or AP mode. It does not change the Mac's WiFi or stop the broker.

First run the connected helper successfully so there is an active caregiver-confirmed prescription in the hub and NVS. Then upload this profile and run its helper, pressing ESP32 reset when the helper starts listening:

```bash
pio run -d firmware -e esp32dev_network_test -t upload --upload-port /dev/cu.usbserial-120
.venv/bin/python firmware/tools/wifi_bench.py --port /dev/cu.usbserial-120 \
  --hub http://127.0.0.1:8000 --broker 127.0.0.1 \
  --output /tmp/esp32-wifi-bench.json
```

The helper requires the additional `Network bench controls enabled; simulated=true` startup marker, idle/no alarm/no pending state, and a matching active caregiver-confirmed hub prescription. It starts a digital feed, waits for an actual ESP32 WiFi-disconnection acknowledgement, and checks increasing volume with unchanged version/rate/settings for at least 30 device seconds. It checks hub offline state and broker Last Will availability, re-enables WiFi, requires fresh online hub/MQTT telemetry with the same running feed, and stops to idle. Defaults bound the run to three minutes. On failure it attempts to restore only a connection it disabled and stop only a feed it started; it preserves alarms. A reconnect acknowledgement alone does not count as successful recovery.

After checking the report, restore the normal profile so interruption controls are absent:

```bash
pio run -d firmware -e esp32dev -t upload --upload-port /dev/cu.usbserial-120
.venv/bin/python -m pytest firmware/test/test_wifi_bench.py
```

Passing fake helper tests or compiling this profile does not establish S6 on hardware. Only an actual successful `wifi_bench.py` report establishes the tested digital-delivery outage behavior.

Firmware now matches the simulator on all 55 shared prescription cases, including the pending replay that caused commit `e091d59` to revert the earlier firmware merge. Both status and event fields follow the current contract. Completion returns idle after five seconds; alarm status reports rate zero; alarm and clear events precede their state changes. Person B can consume the existing QoS 1 events and rejection recovery fields. The real ESP32 programming loop and delivery continuity across WiFi loss have passed; optional physical peripherals and measured delivery remain outside the tested digital scope.

Digital fault commands apply only while running or paused, as in the simulator. The shared fixture covers prescription behavior, not every hardware failure. Persistence failures remain a deliberate difference: firmware preserves the old applied version, keeps the new one pending, and refuses to start until it can persist; the simulator currently logs a failed file write after applying. Person D should align that failure path without weakening the firmware's persistence gate.

`event.schema.json` requires a positive `version` even for `malformed`. Completely unparseable or unversioned input is dropped without state change and logged locally; a version is never fabricated to reject an unrelated prescription. Versioned malformed objects emit `prescription_rejected`, including a readable version alongside an unrepresentably large rate. This follows the current protocol and shared cases. No shared-schema changes were made in Person A's lane.

## Phase 3 serial evidence helper

`tools/bench.py` checks the ESP32 digital-delivery controller over USB and writes a JSON evidence report. Close other serial monitors first. It opens the port with DTR/RTS deasserted and does not deliberately reset the board. Press the ESP32 reset button after the helper starts listening so it can read the startup mode marker. Each step has a bounded deadline; missing markers or telemetry fail the report.

Read-only inspection works with either firmware build and sends no serial commands:

```bash
.venv/bin/python firmware/tools/bench.py --port /dev/cu.usbserial-120 \
  --probe --timeout 20 --output /tmp/esp32-probe.json
```

For automatic control checks, upload the `esp32dev_offline` environment first. This helper requires the exact startup line `Mode: offline bench; local demo enabled; simulated=true` and fresh telemetry with `simulated=true`. It refuses the default hub build, an active feed, an alarm, or a pending prescription. Run with the ESP32 initially idle:

```bash
.venv/bin/python firmware/tools/bench.py --port /dev/cu.usbserial-120 \
  --timeout 20 --output /tmp/esp32-offline-bench.json
```

The control run applies a fictional local demo at a newer version (persisted to NVS), starts delivery, checks increasing volume, pauses and checks frozen volume, raises occlusion and checks rate zero/frozen volume, clears to paused, separately resumes, stops to idle, and reboots only from idle. The reboot check requires a new startup marker, decreasing uptime, and restoration of the same prescription version, rate, and target without automatic delivery. A successful run takes about 40 seconds after reset and ends idle. Failures stop a feed started by this helper when the last observed state permits stopping; an active alarm is preserved for manual inspection and never automatically cleared.

The JSON report marks each serial check as `pass`, `fail`, or `not_run`, includes the latest device status and mode, and always marks network checks `not_run`. Passing this helper does not establish MQTT integration, delivery during WiFi loss, the 200-character network prescription check, or the clinician/caregiver loop. Those Phase 3 integration checks still need a configured hub and broker. This is a prototype with digitally simulated delivery; never connect it to a person.

Helper safety/freshness tests:

```bash
.venv/bin/python -m pytest firmware/test/test_bench.py
```
