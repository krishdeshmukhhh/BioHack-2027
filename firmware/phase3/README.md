# Phase 3 bench evidence

**Person A's Phase 3 digital ESP32 acceptance passed on 2026-10-03.** The board is a real ESP32-D0WD-V3; delivery and faults are digital, and no pump head is driven. Hub and web contracts were unchanged by the bench tests.

| Evidence | Observed result |
|---|---|
| [offline-bench.json](offline-bench.json) | Ten offline USB checks passed: mode/idle gates, local apply, delivery progress, pause, occlusion, clear-to-paused, resume, stop, and NVS recovery. |
| [network-bench.json](network-bench.json) | Thirteen real WiFi/MQTT/hub checks passed: confirmation gate, 200-character note, apply, silent replay, 500 mL/hr rejection, running delivery, pending update, alarms, idle apply, NVS reboot, and ordered availability. |
| [wifi-bench.json](wifi-bench.json) | Eleven real device-only WiFi-loss checks passed. Over 30 device seconds, v4 stayed at 75 mL/hr and modelled volume increased from 0.135 to 0.760 mL. Hub and Last Will showed offline; reconnect preserved the running feed; the helper stopped to idle. |
| [bag-empty-bench.json](bag-empty-bench.json) | Seven normal-firmware checks passed, including bag-empty alarm, zero rate/frozen volume, clear-to-paused, explicit resume, and stop to idle. |
| [ui-check.json](ui-check.json) | Actual rendered family/clinician pages showed connected idle v4, 75 mL/hr, simulated labels, active acknowledgement, and the earlier v3 rejection. |
| [ui-flow.json](ui-flow.json) | Actual clinician Propose change and family Confirm change buttons exercised the real ESP32: unconfirmed v5 left v4 unchanged; confirmed v5 applied at 90 mL/hr; confirmed v6 at 500 mL/hr rejected, preserving v5. Both pages showed the correct outcome and simulated labels. |
| [final-startup.json](final-startup.json) | Normal esp32dev restored the final UI-confirmed v5 at 90 mL/hr, target 5 mL, idle without alarm or pending update after reboot. No bench WiFi interruption controls are present in this profile. |
| [ap-startup.json](ap-startup.json) | Earlier private-AP startup/idle probe passed before router credentials were available. This is historical preparation evidence; AP mode is no longer flashed. |

The board currently runs normal esp32dev with privately configured router credentials in ignored firmware/include/secrets.h. No credentials were printed or committed. The Mac's network settings were not changed. UI checks used installed headless Chrome in isolated temporary profiles because the in-app browser had no available backend; the click-through used actual page controls, not direct API writes.

Software validation passed: ESP32 profiles compile; 24 native Unity tests including all 55 shared prescription cases; ten desktop digital tests; 42 helper tests (11 offline, 16 connected, 15 WiFi); repository tests (360 passed, 3 skipped); and repository lint. Independent source safety review found no blocking defects. Hardware results above come from actual board execution, not these software tests.

Physical buttons, OLED, sensors, calibrated fluid delivery, and a physical pump head were not tested. They are outside the user's chosen digital simulation scope. All values and users are fictional. The network tests used a separate hub database under /tmp/biohack-phase3/, preserving existing demo data and audit history; no audit rows were deleted. Historical evidence reports retain their original prescription versions and per-helper not_run fields.

See [firmware README](../README.md) for reproducing the checks and [safety review](safety-review.md) for review scope. Person D can update the shared Phase 3 checklist and tag after lane integration; only Person A's folders were edited here.
