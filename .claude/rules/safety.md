# Safety rules (always apply)

This project controls a pump. Even as a prototype, treat the safety invariants in `docs/SAFETY.md` (S1 to S8) as fixed requirements.

- Never remove, loosen, or bypass a limit check, a confirmation check, or a version check to make a test or demo pass. Fix the test or the caller.
- Reject out-of-range values. Do not clamp them to the nearest allowed value.
- Hard limits are compile-time constants in `firmware/include/limits.h`. They must not be settable over MQTT, HTTP, or serial.
- A prescription is "active" only when pump telemetry reports its version. Never mark it active on send.
- Connectivity loss must never stop or alter a running feed.
- The audit log only gets new rows. No updates, no deletes.
- All patient names and data are fictional. Never add real patient data. Generated or simulated data carries `"simulated": true` and is labelled on screen.
- Do not write copy that implies the prototype is safe for clinical use. Use "prototype" and "demo".
- Do not give clinical guidance (rates, volumes, regimens) in code comments, UI text, or docs. Values in this repo are demo values.

If a request conflicts with any of these, stop and raise it instead of working around it.
