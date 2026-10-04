# Protocol

The contract between the hub and the pump. The schemas in `shared/protocol/` are the source of truth; this page explains them.

## Topics

See `shared/protocol/topics.md`.

## Messages

- **Prescription** (`prescription.schema.json`): hub to pump. Always caregiver-confirmed. Retained.
- **Status** (`status.schema.json`): pump to hub every 2 seconds.
- **Event** (`event.schema.json`): pump to hub when something happens.
- **Availability**: plain text `online` or `offline`, retained, with `offline` as the Last Will.

Examples are in `shared/protocol/examples/` and are validated by `make test`.

## How the pump handles a prescription

Checks run in this order. The first failure wins, the pump publishes `prescription_rejected` with that reason, and nothing changes.

| Order | Check | Reason on failure |
|---|---|---|
| 1 | Payload parses and has the required fields and types | `malformed` |
| 2 | `pump_id` matches this pump | `wrong_pump` |
| 3 | `confirmed_by` and `confirmed_at` present and non-empty | `not_confirmed` |
| 4 | `version` greater than the current and pending versions | `stale_version` |
| 5 | `rate_ml_hr` within the limits in `limits.h` | `rate_out_of_range` |
| 6 | `volume_ml` within the limits in `limits.h` | `volume_out_of_range` |

Check 1 is the prescription schema, so the firmware and the simulator agree exactly. The payload is malformed unless it is a JSON object where:

- there are no keys other than those in `prescription.schema.json`
- `pump_id`, `mode`, `proposed_by` and `proposed_at` are present and are non-empty strings
- `mode` is `continuous` or `bolus`
- `proposed_at` is an RFC 3339 date-time
- `version` is a JSON integer from 1 to 2147483647 (a signed 32-bit int on the ESP32)
- `rate_ml_hr` and `volume_ml` are present and are finite numbers. Their range is checked in 5 and 6, not here, so `0` or `-5` gives `rate_out_of_range` or `volume_out_of_range`
- `confirmed_by`, `confirmed_at` and `note` are each either missing or a string
- `confirmed_at`, when non-empty, is an RFC 3339 date-time
- `note`, when present, is at most 200 Unicode characters of valid UTF-8

Edge cases for check 1, the same in the firmware and the sim:

- A number too large to represent (for example a 400-digit integer) is malformed, never an error that stops the pump's MQTT handling.
- A boolean is never a number. `version` must be a JSON integer: `3.0` is malformed.
- A payload that is not valid JSON (including `NaN` or `Infinity`) has no readable version, so it is dropped with a log line. This includes the zero-byte message the demo reset publishes to clear the retained prescription (`topics.md`, "Demo reset").
- The limits in checks 5 and 6 are inclusive at both ends.
- Duplicate keys are malformed, compared after decoding escapes (`"rate_ml_\u0068r"` is the same key as `"rate_ml_hr"`). If the duplicated key is the top-level `version`, the version is unreadable, so the payload is dropped with a log line only (no event, status reject fields unchanged). Any other duplicate with a readable `version` is rejected as `malformed`.

Check 3 then handles confirmation: if `confirmed_by` or `confirmed_at` is missing or empty, the reason is `not_confirmed`. (A non-string value is already `malformed` in check 1.)

If all checks pass:

- Pump is idle: apply, persist, publish `prescription_applied`, and report the new `prescription_version` in status.
- Pump is not idle: store as pending, publish `prescription_queued`, report `pending_version` in status, and apply on the next return to idle.
- The pump cannot persist an accepted prescription while idle (a storage fault): it does not apply it, keeps it as pending (status shows `pending_version` while `idle`), publishes no event, refuses to start a feed, and retries the write. It is never reported as applied until persisted.

Because the prescription topic is retained, the pump will see the same message again on every reconnect. Check 4 makes that harmless. A version **equal to the current or the pending version** is a replay: the pump ignores it silently, with no event and no change to the status reject fields. Any other version that is not greater than both is rejected as `stale_version`.

### Rejections are also reported in status (R1)

The ESP32 can only publish QoS 0 (see `topics.md`), so a `prescription_rejected` event can be lost. Every rejection therefore also sets two status fields, which the pump repeats in every status message until the next rejection:

- `last_rejected_version`: the version just rejected (null until the first rejection since boot)
- `last_reject_reason`: the same reason as the event

A rejection event must carry a `version`. So a `malformed` payload with a readable integer `version` from 1 to 2147483647 is rejected as usual. One without a readable `version` is dropped with a log line only, and the status fields stay unchanged.

## Shared test cases

`shared/protocol/cases/prescription_cases.json` is the executable form of the check order above: about 55 cases, each with the pump's starting setup, the exact payload text, and the expected outcome (`applied`, `queued`, `ignored`, `dropped`, or `rejected` with a reason) plus the status fields afterwards. Both pumps must pass every case:

- **Simulator:** `sim/test_protocol_cases.py`, part of `make test`.
- **Firmware:** the native Unity tests read the same file and feed each `payload` to `parsePrescription` and the controller from the given `setup` (a persisted v7 at 60 mL/hr and 500 mL; `running` means a feed started and past priming; a pending version is queued from a running feed).

Payloads are stored as raw text so number edge cases (`8.0`, `1e999`, a 400-digit integer, `NaN`) are exact. Cases marked `beyond_schema` are the check 1 edge cases above that JSON Schema cannot express; every other case agrees with `prescription.schema.json` (checked in `shared/protocol/test_examples.py`).

Adding a behaviour rule means adding a case here first; that is the protocol-first rule in practice.

## Pump behaviour the hub can see

- **Status `rate_ml_hr`:** the applied prescription's rate, `0` when no prescription is applied, and `0` in `alarm` (the actuator is stopped).
- **`complete` to `idle`:** automatic, 5 seconds after reaching `complete`. Any pending prescription is applied on that entry to idle.
- **Feed start:** only from `idle` with a prescription applied. `delivered_ml` resets to 0 at the start of each feed.
- **Event order:** an alarm sends `alarm_raised` then `state_changed`. A clear sends `alarm_cleared` then `state_changed` to `paused`. A queued apply sends `state_changed` to `idle` then `prescription_applied`.
- **Timing:** status goes out on the 2 s timer only, not immediately after an event.
- **Pending:** a newer valid prescription replaces an older pending one.

## How the hub decides lifecycle state

| Hub state | Set when |
|---|---|
| `proposed` | Clinician submits |
| `confirmed` | Caregiver confirms |
| `sent` | Hub publishes to the broker |
| `active` | `prescription_applied` event, or a status with that `prescription_version` |
| `rejected` | `prescription_rejected` event, a status whose `last_rejected_version` is that version, or the caregiver declines |
| `superseded` | A newer version becomes active, or (R6) a newer version is reported as pending or active while this one is still `sent` |

## Conventions

- `snake_case` names with units in the name.
- The pump sends `uptime_ms`; the hub records wall-clock receive time.
- `simulated` is true for the simulator and for firmware built with `DELIVERY_SIMULATED 1`.

## Changes

Record any rename, removal, or change of meaning here with the date.

- 2026-10-03 (`contract-v1`): added the optional status fields `last_rejected_version` and `last_reject_reason` (PRD R1). Pump-to-hub publishes are QoS 0 to match PubSubClient; `topics.md` was corrected. A replay equal to the pending version is now ignored silently, like one equal to the current version. Additive only; no field renamed or removed.
- 2026-10-03: clarified check 1 edge cases, status `rate_ml_hr` in idle and alarm, and the automatic `complete` to `idle` after 5 s. Clarifications only; nothing renamed or removed.
- 2026-10-03: `version` in a prescription has a maximum of 2147483647 (schema and check 1), and an unrepresentable number is `malformed`. From the sim safety review.
- 2026-10-03 (Sync 1): check 1 is now the full prescription schema shape (unknown keys, `proposed_*`, date-times, note length), adopted from the firmware, which is the stricter and safer of the two. A non-string `confirmed_by`/`confirmed_at` is `malformed`; missing or empty is still `not_confirmed`. Rate or volume of 0 or less is still `*_out_of_range`. Pump events and `online` are now published at QoS 1 (the firmware uses 256dpi arduino-mqtt); see `topics.md`.
- 2026-10-03: added the shared prescription test cases. No behaviour change; they encode the rules above.
- 2026-10-03: duplicate keys are malformed and a duplicated `version` is dropped (with shared cases); an unpersisted prescription stays pending while idle. Clarifications; nothing renamed or removed.
