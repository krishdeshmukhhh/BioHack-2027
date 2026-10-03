# MQTT topics

`{id}` is the pump id, for example `pump-001`.

| Topic | Direction | QoS | Retained | Payload | Purpose |
|---|---|---|---|---|---|
| `pump/{id}/prescription` | hub to pump | 1 | yes | `prescription.schema.json` | The latest caregiver-confirmed prescription |
| `pump/{id}/status` | pump to hub | 0 | no | `status.schema.json` | Telemetry, every 2 seconds |
| `pump/{id}/event` | pump to hub | 1 | no | `event.schema.json` | Things that happened: applied, rejected, queued, alarms, state changes |
| `pump/{id}/availability` | pump to hub | 1 | yes | plain text `online` or `offline` | Set to `online` on connect; `offline` is the MQTT Last Will |

No other topics. Add a row here before using a new one.
