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
python -m sim.pump_sim --demo-seed              # DEMO.md reset state: v7 applied, pump idle
```

Keys (type, then Enter): `s` start, `p` pause/resume, `o` occlusion, `b` bag empty, `c` clear alarm, `d` drop/restore wifi, `i` status, `q` quit (publishes `offline` first).

`--demo-seed` loads the `docs/DEMO.md` reset state (v7 at 60 mL/hr applied, pump idle) and waits for a caregiver to start. `--demo-feed` loads the same state and starts a feed at once. Either one applies only if no prescription was loaded from `--state-file`, as if it came from the pump's own storage. Any later prescription still goes through every check in `docs/PROTOCOL.md`.

## Rehearsal scenarios

Scripted fault sequences, so nobody has to type keys at the right moment. Each step calls the same pump actions as the keyboard (start, pause/resume, occlusion, bag empty, clear, wifi drop/restore), and the keyboard stays live. A scenario cannot change limits, skip confirmation, or apply a prescription: it needs one already on the pump, and exits with an error (code 2) if there is none.

```bash
python -m sim.pump_sim --list-scenarios
python -m sim.pump_sim --demo-seed --scenario occlusion --speed 60
python -m sim.pump_sim --demo-seed --scenario bag_empty --speed 60
python -m sim.pump_sim --demo-seed --scenario wifi_drop --speed 60
python -m sim.pump_sim --demo-seed --scenario overnight --speed 600
```

| scenario | what it shows | suggested `--speed` | real time at that speed |
|---|---|---|---|
| `occlusion` | DEMO steps 6 to 8: feed starts, occlusion after 600 sim s, caregiver clears it 10 s later (pump goes to paused), resumes 3 s after that | 60 | about 26 s |
| `bag_empty` | the same with a bag empty alarm | 60 | about 26 s |
| `wifi_drop` | S6: feed starts, MQTT drops after 300 sim s for 30 real s, then reconnects. The hub shows the pump offline once the Last Will fires (about 23 s), the feed keeps running, and `delivered_ml` jumps forward on reconnect | 60 | about 38 s |
| `overnight` | 500 mL at 60 mL/hr compressed: occlusions at 2 h and 5 h of feed time, each cleared and resumed, then runs to complete and back to idle | 600 | under 2 minutes |

Timing: steps count SIM seconds from the previous step, so `--speed` compresses the feed. The moments people watch (the 3 s lead-in before the start, an alarm on screen before it is cleared, the 30 s wifi outage) are fixed REAL seconds so they stay visible at any speed. Each step prints as it fires, for example `[scenario] t=780s occlusion (occlusion detected)`, where `t` is sim seconds since the scenario began. A step the pump does not allow in its current state is printed as ignored, never forced.

Use `--demo-seed` with a scenario, not `--demo-feed`: the scenario starts the feed itself.
