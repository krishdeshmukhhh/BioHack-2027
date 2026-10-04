# Architecture

## Components

```
 Clinician laptop            Caregiver phone
 web/clinician               web/family
       \                        /
        \  HTTP + server-sent events
         \                    /
        +----------------------+
        |   Hub (laptop+Docker)|
        |   FastAPI + SQLite   |
        |   Mosquitto broker   |
        +----------+-----------+
                   | MQTT
        +----------+-----------+
        |                      |
  ESP32 pump (firmware)   Simulator (sim)
  optional FPGA watchdog
```

- The web apps only talk to the hub over HTTP. They never use MQTT.
- The pump only talks MQTT. It never uses HTTP.
- The hub is the only component that knows about both sides, and the only one with a database.
- The simulator and the firmware are interchangeable.

## The remote programming loop

```
Clinician        Hub                  Caregiver        Pump
   | propose      |                       |              |
   |------------->| store: proposed       |              |
   |              |---- notify ---------->|              |
   |              |<--- confirm ----------|              |
   |              | store: confirmed      |              |
   |              |---- publish (retained, QoS 1) ------>|
   |              | store: sent           |   validate: shape, confirmation,
   |              |                       |   version, limits
   |              |<--- event: applied / queued / rejected
   |              |<--- status: prescription_version = N |
   |              | store: active (or rejected)          |
   |<-- "Active on pump" --|              |              |
```

The hub marks a prescription active only when the pump says so. If the pump is offline the prescription stays at "sent", and because the message is retained the pump receives it when it reconnects.

## Pump state machine

```
            start            primed
   IDLE ----------> PRIMING --------> RUNNING ----> COMPLETE ---> IDLE
                                      |   ^            (target reached)
                              pause   |   | resume
                                      v   |
                                     PAUSED
   RUNNING or PAUSED -- fault --> ALARM -- cleared by caregiver --> PAUSED
```

- A new prescription is applied only in IDLE. In any other state it is queued and applied on the next return to IDLE.
- Delivered volume accumulates only in RUNNING.
- An alarm stops the actuator. Clearing it needs a caregiver action at the pump.

## Data stored by the hub

| Table | Contents |
|---|---|
| `patients` | Fictional patients and their pump id |
| `prescriptions` | Every version, its lifecycle state, who proposed and confirmed, timestamps |
| `status_samples` | Telemetry (downsampled for history) |
| `events` | Pump events with hub receive time |
| `audit` | Append-only log of every state change |
| `profiles` | Saved feed profiles and caregiver preferences |

## Why these choices

- **MQTT:** small, well supported on the ESP32, and retained messages plus Last Will give us "latest prescription on reconnect" and "pump offline" for free.
- **Hub on one laptop in Docker, no cloud** (a Pi was planned but broke; a real product would use a small dedicated computer): the demo works without internet, and it speaks to the connectivity and cost goals.
- **Web UI:** the Next.js dashboard (`web/dashboard/`, port 3000) is the main UI, proxying to the hub; the static hub-served pages (`web/family/`, `web/clinician/`) have no build step and remain the fallback if the dashboard breaks.
- **SQLite:** one file, no server.
