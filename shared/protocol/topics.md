# MQTT topics

`{id}` is the pump id, for example `pump-001`.

| Topic | Direction | Publish QoS | Retained | Payload | Purpose |
|---|---|---|---|---|---|
| `pump/{id}/prescription` | hub to pump | 1 | yes | `prescription.schema.json` | The latest caregiver-confirmed prescription |
| `pump/{id}/status` | pump to hub | 0 | no | `status.schema.json` | Telemetry, every 2 seconds |
| `pump/{id}/event` | pump to hub | 1 | no | `event.schema.json` | Things that happened: applied, rejected, queued, alarms, state changes |
| `pump/{id}/availability` | pump to hub | 1 (`online`, and the Last Will `offline`) | yes | plain text `online` or `offline` | `online` on connect. `offline` is the MQTT Last Will, and the pump also publishes it itself before a graceful disconnect (PRD R8) |

## QoS notes

- The ESP32 firmware uses 256dpi `arduino-mqtt`, which can publish QoS 1 (PRD R1 option b). The simulator publishes at the same QoS so it matches the firmware on the wire. Status stays QoS 0: it repeats every 2 s anyway.
- QoS 1 means **at least once**, so the hub can receive the same event twice. It must not double-count, for example the alarms in the `night_alarms` exception. Lifecycle updates are already idempotent.
- Events can still be lost: QoS 1 does not help while the pump is offline or rebooting. Every outcome that matters is also in telemetry: `prescription_version` (applied), `pending_version` (queued), `last_rejected_version` and `last_reject_reason` (rejected), and `alarm`. The hub treats status as authoritative and events as the fast path.
- The pump subscribes to `pump/{id}/prescription` at QoS 1, so the retained prescription arrives reliably.

No other topics. Add a row here before using a new one.
