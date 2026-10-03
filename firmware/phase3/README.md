# Phase 3 bench evidence

Run on 2026-10-03 with a real ESP32-D0WD-V3 over `/dev/cu.usbserial-120`. Delivery and faults are digital; no pump head is driven.

| Evidence | Observed result |
|---|---|
| [offline-bench.json](offline-bench.json) | All ten serial checks passed on `esp32dev_offline`: mode/idle gates, local apply, delivery progress, pause, occlusion, clear-to-paused, resume, stop, and NVS recovery after reboot. Ended idle. |
| [ap-startup.json](ap-startup.json) | `esp32dev_ap` started its private AP, identified itself as hub mode with simulated delivery, and booted idle with no pending prescription. No serial controller commands were sent during this probe. |

The board is currently flashed with `esp32dev_ap`. Private AP credentials are in ignored `firmware/include/secrets.h`. The Mac has not been switched to that network.

MQTT delivery, clinician/caregiver programming through the hub, a 200-character network note, device limit rejection through MQTT, queued updates through MQTT, availability/retained replay, and delivery across WiFi loss remain unverified on hardware. Phase 3 acceptance is pending those checks. Physical buttons/OLED were not tested; the user selected digital simulation.

Software validation passed: default, offline, and AP ESP32 builds; 24 native Unity tests including all 55 shared prescription cases; ten desktop digital tests; eleven offline-helper tests; sixteen connected-helper tests using fake HTTP/serial/MQTT; repository tests (360 passed, 3 skipped); and repository lint. Source review and software tests do not establish the pending physical network checks.

See [firmware README](../README.md) for upload, local service, and bench-helper instructions. Existing hub data and audit history are preserved by using a separate Phase 3 database under `/tmp/biohack-phase3/`.
