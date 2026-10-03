---
paths:
  - "shared/protocol/**"
  - "firmware/**"
  - "hub/**"
  - "sim/**"
---

# Protocol rules

`shared/protocol/` is the single source of truth for every MQTT message.

- Change order: schema, then example in `shared/protocol/examples/`, then firmware and sim together, then hub.
- Every schema has at least one valid example. `make test` validates all examples.
- Topics are defined in `shared/protocol/topics.md`. Do not invent a topic in code.
- The hub validates every inbound and outbound MQTT payload against the schema and drops invalid inbound messages with a log line.
- Field names are `snake_case`. Units go in the name: `rate_ml_hr`, `delivered_ml`, `battery_pct`, `uptime_ms`.
- Adding an optional field is fine. Renaming, removing, or changing the meaning of a field needs a note in `docs/PROTOCOL.md` under "Changes".
- The pump has no reliable clock. It sends `uptime_ms`. The hub adds the wall-clock timestamp on receipt.
