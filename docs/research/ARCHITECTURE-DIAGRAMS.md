# Architecture diagrams

*Companion to [`PRD.md`](PRD.md) and [`../ARCHITECTURE.md`](../ARCHITECTURE.md). Mermaid renders on GitHub, in VS Code (Markdown Preview Mermaid Support), and at mermaid.live. `R#` labels refer to the recommendations in PRD section 10. Prototype, not a medical device.*

1. [System context](#1-system-context)
2. [Deployment on the demo network](#2-deployment-on-the-demo-network)
3. [Hub internals](#3-hub-internals)
4. [Remote programming loop: happy path](#4-remote-programming-loop-happy-path)
5. [Remote programming loop: unhappy paths](#5-remote-programming-loop-unhappy-paths)
6. [Pump prescription validation](#6-pump-prescription-validation)
7. [Pump state machine](#7-pump-state-machine)
8. [Hub prescription lifecycle](#8-hub-prescription-lifecycle)
9. [Data model](#9-data-model)
10. [Alarm to plain-language alert](#10-alarm-to-plain-language-alert)
11. [Connectivity loss and reconnect](#11-connectivity-loss-and-reconnect)
12. [Defence in depth](#12-defence-in-depth)

---

## 1. System context

```mermaid
flowchart LR
    clin["Clinician<br/>(web/clinician)"]
    fam["Caregiver<br/>(web/family)"]
    subgraph pi["Raspberry Pi hub (offline)"]
        hub["Hub<br/>FastAPI + SQLite"]
        broker[("Mosquitto<br/>MQTT broker")]
    end
    pump["ESP32 pump<br/>(firmware)"]
    sim["Simulator<br/>(sim/pump_sim.py)"]
    fpga["FPGA watchdog<br/>(stretch)"]

    clin -- "HTTP + SSE" --> hub
    fam -- "HTTP + SSE" --> hub
    hub <-- "MQTT" --> broker
    broker <-- "MQTT" --> pump
    broker <-. "MQTT (wire-identical)" .-> sim
    fpga -. "monitors STEP, cuts ENABLE" .-> pump
```

Rules shown: browsers never use MQTT, pumps never use HTTP, and the hub is the only component with a database.

## 2. Deployment on the demo network

```mermaid
flowchart TB
    subgraph net["Private demo Wi-Fi (own router or Pi as AP), no internet"]
        subgraph pi["Raspberry Pi (fixed IP / hostname)"]
            mosq["mosquitto :1883<br/>persistence true (R3)"]
            uv["uvicorn hub.app.main:app :8000"]
            db[("hub.sqlite3")]
            static["/web static files"]
            uv --- db
            uv --- static
            uv -- "paho-mqtt 2.x" --- mosq
        end
        esp["ESP32<br/>PubSubClient, ArduinoJson<br/>NVS Preferences<br/>buffer 1024 B (R2)"]
        laptop["Laptop browser<br/>clinician portal"]
        phone["Android phone browser<br/>family app (R7)"]
        simhost["Laptop: make sim<br/>(fallback pump)"]
    end
    esp -- "MQTT 3.1.1, keepalive 15 s" --> mosq
    simhost -. "MQTT" .-> mosq
    laptop -- "HTTP :8000" --> uv
    phone -- "HTTP :8000" --> uv
```

## 3. Hub internals

paho-mqtt runs its network loop in a background thread (`loop_start()`), and FastAPI runs on asyncio. The handoff between them must go through `loop.call_soon_threadsafe` (R5).

```mermaid
flowchart LR
    subgraph mqttThread["paho network thread"]
        onmsg["on_message"]
        onconn["on_connect<br/>(re)subscribe pump/+/status,<br/>event, availability"]
    end
    subgraph aio["asyncio event loop (uvicorn)"]
        q[["asyncio.Queue"]]
        ingest["Ingest<br/>validate schema (format_checker, R4)<br/>add received_at<br/>store"]
        life["Lifecycle engine<br/>sets active / rejected / superseded<br/>(ONLY from pump data, S5)"]
        bus["SSE broadcaster<br/>fastapi.sse.EventSourceResponse"]
        api["REST API<br/>propose / confirm / decline"]
        gate["Publish gate<br/>require confirmation (S2)<br/>validate outbound<br/>retain=True, qos=1"]
        repub["Re-publisher<br/>on startup and on availability=online (R3)"]
    end
    db[("SQLite<br/>audit triggers (S7)")]

    onmsg -- "call_soon_threadsafe" --> q
    q --> ingest --> db
    ingest --> life --> db
    ingest --> bus
    life --> bus
    api --> db
    api -- "confirm" --> gate
    repub --> gate
    gate -- "client.publish" --> mqttThread
    life -- "availability online" --> repub
```

## 4. Remote programming loop: happy path

```mermaid
sequenceDiagram
    autonumber
    actor C as Clinician
    participant P as Portal
    participant H as Hub
    participant DB as SQLite
    participant F as Family app
    actor G as Caregiver
    participant B as Broker
    participant U as Pump

    C->>P: Propose 90 mL/hr (demo value)
    P->>H: POST /api/pumps/pump-001/prescriptions
    H->>DB: insert v8 state=proposed, audit row
    H-->>P: SSE prescription v8 proposed (chip Pending)
    H-->>F: SSE change to review (old v7 vs new v8)
    G->>F: Confirm (button or voice)
    F->>H: POST .../prescriptions/8/confirm
    H->>DB: v8 confirmed, audit row
    H->>H: publish gate checks confirmed_by (S2)
    H->>B: PUBLISH pump/pump-001/prescription v8 retain qos1
    H->>DB: v8 sent, audit row
    H-->>P: SSE chip Sent
    B->>U: deliver v8
    U->>U: validate shape, pump, confirm, version, limits
    U->>U: state idle so apply and persist to NVS
    U->>B: event prescription_applied v8
    U->>B: status prescription_version=8
    B->>H: event and status
    H->>DB: v8 active, v7 superseded, audit rows
    H-->>P: SSE chip Active on pump (S5)
    H-->>F: SSE status rate 90
```

## 5. Remote programming loop: unhappy paths

```mermaid
sequenceDiagram
    participant H as Hub
    participant B as Broker
    participant U as Pump
    participant P as Portal

    rect rgba(200,80,80,0.12)
    Note over H,U: A. Out of range (demo step 5)
    H->>B: v9 rate 500 (confirmed)
    B->>U: v9
    U->>U: check 5 fails, change nothing (S1, no clamping)
    U->>B: event prescription_rejected v9 rate_out_of_range
    U->>B: status last_rejected_version=9 (R1, survives QoS0 loss)
    B->>H: event and/or status
    H-->>P: chip Rejected: rate out of range
    end

    rect rgba(80,120,200,0.12)
    Note over H,U: B. Pump busy (S4)
    H->>B: v10 (confirmed)
    B->>U: v10 while state=running
    U->>B: event prescription_queued v10, status pending_version=10
    Note over U: feed completes, back to idle
    U->>U: apply v10
    U->>B: event prescription_applied v10, status prescription_version=10
    B->>H: H marks v10 active
    end

    rect rgba(120,120,120,0.12)
    Note over H,U: C. Pump offline
    H->>B: v11 retained
    Note over H: v11 stays sent, UI shows offline since time
    U->>B: reconnect, subscribe
    B->>U: retained v11 delivered on subscribe
    U->>B: applied or queued or rejected as above
    end

    rect rgba(200,160,60,0.12)
    Note over H,U: D. Unconfirmed
    H->>H: publish gate refuses (S2), nothing sent
    Note over U: if one ever arrives, pump rejects not_confirmed
    end
```

## 6. Pump prescription validation

The same order runs in the firmware and the sim (`docs/PROTOCOL.md`). The first failure wins.

```mermaid
flowchart TD
    A([Message on pump/id/prescription]) --> B{Parses, required<br/>fields and types?}
    B -- no --> Rm[reject: malformed]
    B -- yes --> C{pump_id == mine?}
    C -- no --> Rw[reject: wrong_pump]
    C -- yes --> D{confirmed_by and<br/>confirmed_at non-empty?}
    D -- no --> Rc[reject: not_confirmed]
    D -- yes --> E{version == current?}
    E -- yes --> Ig([ignore silently<br/>retained replay, S3])
    E -- no --> F{version > current<br/>and > pending?}
    F -- no --> Rs[reject: stale_version]
    F -- yes --> G{LIMIT_RATE_MIN <= rate<br/><= LIMIT_RATE_MAX?}
    G -- no --> Rr[reject: rate_out_of_range]
    G -- yes --> H{LIMIT_VOLUME_MIN <= volume<br/><= LIMIT_VOLUME_MAX?}
    H -- no --> Rv[reject: volume_out_of_range]
    H -- yes --> I{state == idle?}
    I -- yes --> Ap[apply, persist NVS,<br/>event prescription_applied]
    I -- no --> Qu[store pending,<br/>event prescription_queued]

    Rm & Rw & Rc & Rs & Rr & Rv --> X[publish prescription_rejected + reason<br/>state unchanged]
```

## 7. Pump state machine

There is a single `transitionTo()`, which publishes `state_changed` on every transition.

```mermaid
stateDiagram-v2
    [*] --> idle: boot, load NVS
    idle --> priming: start
    priming --> running: primed
    running --> paused: pause
    paused --> running: resume
    running --> complete: delivered >= target
    complete --> idle
    running --> alarm: fault
    paused --> alarm: fault
    alarm --> paused: cleared by caregiver at pump

    note right of idle
        On entry: if pending_version is set,
        apply it (S4) and publish prescription_applied.
    end note
    note right of running
        delivered_ml accumulates only here.
        Wi-Fi/MQTT loss changes nothing (S6).
    end note
    note right of alarm
        Actuator stopped.
        occlusion, bag_empty, low_battery, sensor_mismatch
    end note
```

## 8. Hub prescription lifecycle

Transitions marked *pump* are allowed only on the MQTT ingest path (S5).

```mermaid
stateDiagram-v2
    [*] --> proposed: clinician POST
    proposed --> confirmed: caregiver confirm
    proposed --> rejected: caregiver decline
    confirmed --> sent: publish gate (S2)
    sent --> active: pump applied event or status version (pump)
    sent --> rejected: pump rejected event or status (pump)
    sent --> superseded: newer version reaches pump first (R6)
    active --> superseded: newer version active (pump)
    rejected --> [*]
    superseded --> [*]
```

## 9. Data model

```mermaid
erDiagram
    patients ||--o{ prescriptions : "has"
    patients ||--o{ status_samples : "pump reports"
    patients ||--o{ events : "pump reports"
    patients ||--o{ profiles : "uses"
    prescriptions ||--o{ audit : "changes logged"

    patients {
        text id PK
        text display_name "fictional"
        text pump_id UK
        real daily_goal_ml "demo value"
        int simulated
    }
    prescriptions {
        int id PK
        text pump_id
        int version "unique per pump, increasing"
        text mode "continuous or bolus"
        real rate_ml_hr
        real volume_ml
        text note
        text state "proposed confirmed sent active rejected superseded"
        text reject_reason
        text proposed_by
        text proposed_at
        text confirmed_by
        text confirmed_role
        text confirmed_at
        text sent_at
        text resolved_at
    }
    status_samples {
        int id PK
        text pump_id
        text received_at "hub wall clock"
        int uptime_ms
        text state
        real rate_ml_hr
        real delivered_ml
        real target_ml
        text alarm
        int prescription_version
        int pending_version
        int simulated
    }
    events {
        int id PK
        text pump_id
        text received_at
        int uptime_ms
        text type
        int version
        text reason
        text alarm
        text from_state
        text to_state
        int simulated
    }
    audit {
        int id PK "append-only, triggers RAISE ABORT"
        text at
        text actor "user id or pump id"
        text actor_role
        text entity "prescription, alarm, profile"
        text entity_id
        text action
        text old_value
        text new_value
    }
    profiles {
        int id PK
        text patient_id
        text name "e.g. overnight continuous"
        text mode
        real rate_ml_hr
        real volume_ml
    }
```

## 10. Alarm to plain-language alert

```mermaid
sequenceDiagram
    actor Pr as Presenter
    participant U as Pump
    participant H as Hub
    participant F as Family app
    participant P as Portal
    actor G as Caregiver

    Pr->>U: press occlusion button
    U->>U: transitionTo(alarm), stop actuator
    U->>H: event alarm_raised occlusion, state_changed running to alarm
    H->>H: map occlusion to strings: cause, steps, picture
    par to family
        H-->>F: SSE alert
        F->>F: aria-live assertive, picture plus steps
        F->>F: vibrate if supported (Android) (R7)
        F->>F: speechSynthesis speak (local voice)
    and to clinician
        H-->>P: SSE flag patient, exceptions first
    end
    G->>U: fix line, press clear at pump
    U->>H: event alarm_cleared, state alarm to paused
    H-->>F: clear alert
    H-->>P: clear flag
    G->>F: Resume
```

## 11. Connectivity loss and reconnect

```mermaid
sequenceDiagram
    participant U as Pump
    participant B as Broker
    participant H as Hub
    participant F as Apps

    Note over U: running v8 at demo rate
    U-xB: Wi-Fi drops
    Note over U: feed continues unchanged (S6), non-blocking reconnect timer
    B->>B: keepalive 15 s x 1.5 expires
    B->>H: Last Will: availability offline (retained)
    H-->>F: Pump offline, last update HH:MM:SS
    Note over H: new confirmed v9 published retained, stays sent
    U->>B: CONNECT with Will (offline, retained)
    U->>B: availability online (retained)
    U->>B: SUBSCRIBE pump/pump-001/prescription
    B->>U: retained v9
    U->>U: running so queue v9 (S4)
    U->>B: event prescription_queued v9
    B->>H: online plus queued
    H->>H: re-publisher no-op (v9 already retained) (R3)
    H-->>F: online again, v9 queued
```

## 12. Defence in depth

```mermaid
flowchart TB
    L1["1. Portal form validation<br/>stops typos"] --> L2
    L2["2. Hub validation + confirmation gate<br/>stops unconfirmed or malformed (S2)"] --> L3
    L3["3. Caregiver reviews old vs new<br/>stops changes that look wrong at the bedside"] --> L4
    L4["4. Pump hard limits in limits.h<br/>stops anything out of range, whatever the hub does (S1)"] --> L5
    L5["5. FPGA step-rate watchdog (stretch)<br/>stops motor overspeed from a firmware bug"]
```
