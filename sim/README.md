# Simulator and demo data

- `pump_sim.py`: a software pump that behaves exactly like the firmware on MQTT, with fault injection and scripted scenarios. Lets the hub and web apps be built before hardware is ready, and is the fallback if hardware fails on demo day.
- `generate_history.py`: 30 days of fictional history for the clinician dashboard.

Everything here is flagged `"simulated": true`.

## Generated history (`generate_history.py`)

```bash
make history                      # same as: python -m sim.generate_history
python -m sim.generate_history --days 30 --seed 2026 --end-date 2026-10-03 --out sim/data/history.json
```

Writes one JSON file (default `sim/data/history.json`) for three invented patients, one pump each:

| patient | pump | pattern |
|---|---|---|
| `pat-01` Demo Child Aster | `pump-001` | `on_target` |
| `pat-02` Demo Child Bramble | `pump-002` | `drifting_under_target` (under 90% of prescribed for at least the last 5 days) |
| `pat-03` Demo Child Cobalt | `pump-003` | `night_occlusions` (2 to 4 occlusions on most nights, 22:00 to 06:00 UTC) |

Shape (a hand-off contract with the hub):

```
{"simulated": true, "seed": int, "generated_for_end_date": "YYYY-MM-DD",
 "patients": [{"id", "display_name", "pump_id", "pattern", "simulated"}],
 "daily":    [{"patient_id", "pump_id", "date", "delivered_ml", "prescribed_ml", "alarm_count", "simulated"}],
 "alarms":   [{"patient_id", "pump_id", "alarm", "raised_at", "cleared_at", "simulated"}]}
```

- `daily` is sorted by patient then date; `alarm_count` is the number of alarms whose `raised_at` falls on that UTC date.
- Alarm codes come from `shared/protocol/event.schema.json`; timestamps are ISO-8601 UTC with `Z`.
- Output is deterministic for a given `--seed`, `--days`, and `--end-date`. All values are demo values.

## Running the simulated pump

```bash
make sim                                        # PUMP_ID, MQTT_HOST, MQTT_PORT from .env
python -m sim.pump_sim --demo-feed --speed 60   # PLAN phase 1 check: starts v7 at 60 mL/hr at once
```

Keys (type, then Enter): `s` start, `p` pause/resume, `o` occlusion, `b` bag empty, `c` clear alarm, `d` drop/restore wifi, `i` status, `q` quit (publishes `offline` first).

`--demo-feed` loads the `docs/DEMO.md` starting state only if no prescription was loaded from `--state-file`, as if it came from the pump's own storage. Any later prescription still goes through every check in `docs/PROTOCOL.md`.
