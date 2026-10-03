---
paths:
  - "firmware/**"
---

# Firmware rules (ESP32, PlatformIO, Arduino framework)

- The main loop never blocks. No `delay()` outside `setup()`. Use `millis()` timers.
- One state machine, in one place. All transitions go through a single `transitionTo()` function that logs and publishes a `state_changed` event.
- Motor control and safety checks must keep running when wifi or MQTT is down (S6). Reconnect in the background.
- Validate a prescription fully before touching any state: schema shape, `confirmed_by` present (S2), version greater than current (S3), limits (S1). On any failure publish `prescription_rejected` with a `reason` and change nothing.
- Apply a prescription only in `IDLE`. Otherwise store it as pending and publish `prescription_queued` (S4).
- Limits come from `include/limits.h` only. Never from the network.
- Persist the current prescription and version to NVS (`Preferences`) so a reboot does not lose them.
- Pins and tunables live in `include/config.h`. Wifi and broker credentials live in `include/secrets.h` (gitignored).
- Keep an actuator interface (`start`, `stop`, `setRateMlHr`) so a stepper, a DC motor, or an LED stand-in can be swapped without touching the state machine.
- Use ArduinoJson for payloads and PubSubClient for MQTT. Set the Last Will to `offline` on the availability topic.
- After any change run `make fw-build`.
