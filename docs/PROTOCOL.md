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

If all checks pass:

- Pump is idle: apply, persist, publish `prescription_applied`, and report the new `prescription_version` in status.
- Pump is not idle: store as pending, publish `prescription_queued`, report `pending_version` in status, and apply on the next return to idle.

Because the prescription topic is retained, the pump will see the same message again on every reconnect. Check 4 makes that harmless. A version **equal to the current or the pending version** is a replay: the pump ignores it silently, with no event and no change to the status reject fields. Any other version that is not greater than both is rejected as `stale_version`.

### Rejections are also reported in status (R1)

The ESP32 can only publish QoS 0 (see `topics.md`), so a `prescription_rejected` event can be lost. Every rejection therefore also sets two status fields, which the pump repeats in every status message until the next rejection:

- `last_rejected_version`: the version just rejected (null until the first rejection since boot)
- `last_reject_reason`: the same reason as the event

A rejection event must carry a `version`. So a `malformed` payload with a readable integer `version` of at least 1 is rejected as usual. One without a readable `version` is dropped with a log line only, and the status fields stay unchanged.

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
