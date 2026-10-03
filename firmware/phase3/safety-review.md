# Phase 3 source safety review

Independent read-only firmware/helper review, 2026-10-03: no blocking defects remain. S1–S6 and S8 pass within this source scope. S7 is unchanged; no hub/database implementation was edited.

- Offline firmware disables WiFi/MQTT and separates local prescriptions into `pump-bench` NVS.
- The private AP profile excludes local demo generation, uses the hub's `pump` NVS, and keeps discovery/reconnect on the network worker.
- Serial helpers require the correct startup mode, simulated telemetry, matching pump identity, and initial idle/no alarm/no pending state before control.
- Cleanup stops only a helper-started feed when permitted and preserves an active alarm.
- Connected freshness follows the actual HTTP API's `received_at`, matched to fresh MQTT device telemetry. The hub API omits `uptime_ms`.
- Replay evidence fails on any prescription event for the duplicate version. Reboot availability requires offline followed by a later online message.
- Helpers have bounded waits and leave the Mac's WiFi settings unchanged.

The reviewer confirmed that the evidence distinguishes actual offline/AP startup checks from pending hardware MQTT integration and WiFi-loss checks. Phase 3 acceptance remains incomplete. This source review does not replace those physical checks.
