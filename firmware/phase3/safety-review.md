# Phase 3 source safety review

Independent read-only firmware/helper review, 2026-10-03: no blocking defects remain. S1–S6 and S8 pass within this source scope. S7 is unchanged; no hub/database implementation was edited.

- Offline firmware disables WiFi/MQTT and separates local prescriptions into `pump-bench` NVS.
- The private AP profile excludes local demo generation, uses the hub's `pump` NVS, and keeps discovery/reconnect on the network worker.
- All control helpers require the correct startup mode, simulated telemetry, and initial idle/no alarm/no pending state; connected helpers also match pump identity.
- Cleanup stops only a helper-started feed when permitted and preserves an active alarm.
- Connected freshness follows the actual HTTP API's `received_at`, matched to fresh MQTT device telemetry. The hub API omits `uptime_ms`.
- Replay evidence fails on any prescription event for the duplicate version. Reboot availability requires offline followed by a later online message.
- Helpers have bounded waits and leave the Mac's WiFi settings unchanged.

The subsequent real ESP32 reports establish the reviewed digital-simulation acceptance: connected programming, 200-character note, limit rejection, queued apply, replay, alarms, NVS reboot, Last Will, and WiFi-loss continuity. During the 30-second outage the modelled increase was 0.625 mL at 75 mL/hr, with unchanged prescription/settings. Physical peripherals and measured fluid delivery remain outside this scope.

The additional `NETWORK_BENCH` source review found no blocking defects. The station-only profile excludes AP/offline combinations, keeps WiFi changes on the network worker, suppresses reconnect while disconnected, preserves the Last Will by omitting MQTT DISCONNECT, and prioritizes shutdown. The WiFi helper requires matching caregiver-confirmed settings, checks advancing digital volume with unchanged settings, and restores its own connection/feed after write or flush failures while preserving alarms. Fifteen focused fake tests and the actual station/WiFi-loss runs passed. Normal firmware was restored afterward.

Rendered UI inspection and a later actual clinician-form/family-confirmation click-through are recorded separately. The UI-confirmed 90 mL/hr v5 applied only after confirmation; UI-confirmed 500 mL/hr v6 rejected, preserving v5. Normal firmware booted idle with v5 after the final reboot. Reports explicitly identify digital simulation, their firmware profiles, and historical versions. Person A's Phase 3 digital firmware acceptance passes; shared checklist/tag updates remain with the lead.
