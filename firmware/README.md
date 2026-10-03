# Firmware (ESP32)

The pump controller. Receives confirmed prescriptions over MQTT, checks them against hard limits, runs the feed state machine, and publishes status and events.

- `include/limits.h`: hard safety limits (S1). Compile-time only.
- `include/config.h`: pump id, pins, tunables.
- `include/secrets.h`: wifi and broker details. Copy from `secrets.example.h`. Gitignored.
- `include/pump_state.h`: state names, matching the protocol.
- `src/main.cpp`: entry point.

Planned modules (phase 3): `prescription` (validate, queue, apply, persist), `state_machine`, `actuator`, `mqtt_link`, `faults` (buttons), `level_sensor` (optional), `display` (optional).

Build with `make fw-build`, flash with `make fw-upload`, watch serial with `make fw-monitor`.
