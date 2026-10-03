# MQTT topics

`{id}` is the pump id, for example `pump-001`.

| Topic | Direction | Publish QoS | Retained | Payload | Purpose |
|---|---|---|---|---|---|
| `pump/{id}/prescription` | hub to pump | 1 | yes | `prescription.schema.json` | The latest caregiver-confirmed prescription |
| `pump/{id}/status` | pump to hub | 0 | no | `status.schema.json` | Telemetry, every 2 seconds |
| `pump/{id}/event` | pump to hub | 0 | no | `event.schema.json` | Things that happened: applied, rejected, queued, alarms, state changes |
| `pump/{id}/availability` | pump to hub | 0 for `online`; 1 for the Last Will `offline` | yes | plain text `online` or `offline` | `online` on connect. `offline` is the MQTT Last Will, and the pump also publishes it itself before a graceful disconnect (PRD R8) |

## QoS notes

- The ESP32 firmware uses PubSubClient, which **can only publish QoS 0** (PRD R1). The simulator publishes at the same QoS so it matches the firmware on the wire. The Last Will is set at connect time and can be QoS 1.
- So pump events can be lost. Every outcome that matters is also in telemetry: `prescription_version` (applied), `pending_version` (queued), `last_rejected_version` and `last_reject_reason` (rejected), and `alarm`. The hub treats status as authoritative and events as the fast path.
- Subscribers use QoS 1. The pump subscribes to `pump/{id}/prescription` at QoS 1, so the retained prescription arrives reliably.

No other topics. Add a row here before using a new one.
