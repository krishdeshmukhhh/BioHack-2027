# Product Requirements Document: Smart Pump

*Bio Hack 2026 · Draft 1 · 2026-10-03 · Prototype, not a medical device. All patient data is fictional. No value in this document is clinical guidance.*

Companion documents:
- [`ARCHITECTURE-DIAGRAMS.md`](ARCHITECTURE-DIAGRAMS.md): Mermaid diagrams for every flow named here
- [`REFERENCES.md`](REFERENCES.md): research report with sources and quoted documentation excerpts (cited below as `[R#]`)
- Existing sources of truth: [`../PLAN.md`](../PLAN.md), [`../ARCHITECTURE.md`](../ARCHITECTURE.md), [`../PROTOCOL.md`](../PROTOCOL.md), [`../SAFETY.md`](../SAFETY.md), [`../DEMO.md`](../DEMO.md)

This PRD does not replace those files. It collects them into one numbered set of requirements, adds what the research found, and lists the changes we recommend before Phase 1 starts (section 10).

---

## 1. Summary

Families who tube feed at home program the pump by hand at the bedside. The connected pumps on the market send data one way, to clinicians and support staff. We are building a **closed loop**:

1. A clinician proposes a prescription in the portal.
2. A caregiver confirms it in the family app.
3. The hub publishes it to the pump.
4. The pump checks it against its own hard limits and applies it only when idle.
5. The portal shows "Active on pump" only after the pump reports the new version.

The other half of the product is the family side: plain-language alerts, progress toward the day's goal, and an app built for one-handed use at night.

## 2. Problem

| Evidence | Source |
|---|---|
| Home enteral feeding brings practical safety problems: tube dislodgement, pump inaccuracy, frequent blockages, unsafe storage, and **disturbed sleep for carers at night** | Search summary of the Alsaeed et al. 2018 survey and related literature [R1]. *Not confirmed in the full text; see REFERENCES.* |
| **Poor knowledge of pump alarms** is reported as one of the main safety issues among caregivers | Search summary, same body of literature [R1]. *Not confirmed in the full text.* |
| 93% of carers gave medicines through the tube, but only 62% had advice from a professional and only 8% had read written information | Alsaeed et al. 2018, full text [R1] |
| Carers worked out their own methods when training fell short, some of them unsafe | Alsaeed et al. 2018 [R1] |
| Follow-up can be slow: some patients "were not contacted until seven days or more after discharge" | Ojo 2015, *Nutrients* [R2] |
| The leading connected pump (Kangaroo Connect) offers feeding history, an attainment report, remote troubleshooting, and remote software updates. **We found no evidence of remote prescription programming with caregiver confirmation.** | Cardinal Health product materials [R3] |
| The most common infusion pump problems reported to FDA are software defects, user interface issues, and mechanical or electrical failures. Enteral pumps are named in this category. | FDA [R4] |

**Problem statement.** A clinician cannot safely change a home feed without a visit or a phone call, cannot see whether the change took effect, and gets little interpreted data back. A caregiver at 3 a.m. gets an alarm code on a small screen.

**Our contribution** (inference from [R3] and [R4], not a market claim):
1. A remote change that the caregiver must confirm and the pump must acknowledge.
2. Telemetry that proves the change took effect.
3. A family app that explains alarms in plain words and is built for accessibility.

## 3. Users and personas

| Persona | Context | Needs | Primary surface |
|---|---|---|---|
| **Caregiver (parent)**: "Sam" | At home, often at night, one hand free, tired; may not speak English as a first language | Know the feed is OK at a glance; understand an alarm and what to do; approve or decline changes with confidence | Family app on a phone |
| **Secondary caregiver (school nurse)** | Daytime feeds at school | Same as above, with their own role and alert preferences recorded | Family app |
| **Clinician (dietitian or nurse)** | Clinic laptop, many patients | Change a regimen without a visit; see who needs attention; delivered versus prescribed | Clinician portal |
| **Demo judge** | Three-minute demo slot | See the loop close, see a refused change, see an alarm explained, hear the honest list of gaps | Both surfaces and the pump |

## 4. Goals and non-goals

### Goals (from PLAN section 1)

- **G1** Better communication and monitoring of a smart pump: the closed loop.
- **G2** Better accessibility and personalization while keeping costs low: ESP32 plus Raspberry Pi, no cloud, static web.

### Non-goals

- Real patients, real clinical data, clinical guidance.
- Real authentication. Users are fixed demo users, and the UI says so.
- Native mobile apps, cloud hosting, regulatory submission.
- Flow measurement accuracy. Delivery comes from motor steps or is modelled from time and rate.

## 5. Success metrics (demo-measurable targets)

These are team targets for the demo, not clinical performance claims.

| ID | Metric | Target | How we measure |
|---|---|---|---|
| M1 | Confirm tap to "Active on pump" (pump online and idle) | ≤ 5 s | Stopwatch during rehearsal; hub audit timestamps |
| M2 | Fault injected to alert shown on phone | ≤ 3 s | Stopwatch; event `received_at` minus SSE delivery time |
| M3 | Out-of-range proposal shows "Rejected: rate out of range" and the pump is unchanged | 100% of runs | DEMO step 5 |
| M4 | Confirm flow done with a screen reader alone, and in the second language with night mode | Pass | PLAN phase 5 check |
| M5 | Full demo with the internet off | 2 clean runs in a row | PLAN phase 6 check |
| M6 | Pump offline shown with time of last update | ≤ keepalive × 1.5 (≈ 23 s with PubSubClient defaults [R10]) | Pull pump power during rehearsal |
| M7 | Safety invariants S1 to S8 | No regressions; `safety-reviewer` clean | Agent run before each merge |

## 6. Functional requirements

Priority: **M** Must, **S** Should, **X** Stretch (as in PLAN section 3). Each requirement names the invariant (S#) and phase (P#) it belongs to.

### 6.1 Remote programming loop (core)

| ID | Requirement | Pri | Trace |
|---|---|---|---|
| FR-1 | A clinician can propose a prescription for a pump: mode (`continuous` or `bolus`), `rate_ml_hr`, `volume_ml`, and an optional note of up to 200 characters. The hub gives it the next version number. | M | P2 |
| FR-2 | The portal form validates the shape of the input (positive numbers, required fields) to catch typos. **It does not enforce the hard limits**, so the demo can show the pump refusing a change. | M | S1, P2 |
| FR-3 | The family app shows each pending proposal as **old versus new**, with Confirm and Decline buttons of equal size. Voice confirm is optional and always has a button for the same action. | M | S2, P2, P5 |
| FR-4 | The hub publishes a prescription only through **one publish gate** that refuses anything without a stored caregiver confirmation. It publishes to `pump/{id}/prescription`, retained, QoS 1. | M | S2, P2 |
| FR-5 | The pump validates in this order, and the first failure wins: `malformed`, `wrong_pump`, `not_confirmed`, `stale_version`, `rate_out_of_range`, `volume_out_of_range`. On failure it publishes `prescription_rejected` with the reason and changes nothing. | M | S1–S3, P2–P3 |
| FR-6 | If the pump is idle it applies the prescription, persists it, and publishes `prescription_applied`. Otherwise it stores it as pending, publishes `prescription_queued`, and applies it on the next return to idle. | M | S4 |
| FR-7 | The hub sets `active` or `rejected` **only** from pump events or status. The portal chip shows Pending, Sent, Active on pump, or Rejected with the reason, exactly as the hub reports it. | M | S5 |
| FR-8 | A caregiver decline sets `rejected` (reason `declined`, hub-side only). Nothing is published. | M | S2 |
| FR-9 | When version N becomes active, every older `active` version becomes `superseded`. A pending version that a newer one replaces before it is applied also becomes `superseded`. *(Recommendation R6.)* | M | S3 |
| FR-10 | If the pump is offline the prescription stays `sent`. The retained message delivers it when the pump reconnects. The UI shows "Sent: pump offline since HH:MM". | M | S5, S6 |

### 6.2 Monitoring and alerts

| ID | Requirement | Pri | Trace |
|---|---|---|---|
| FR-11 | The pump publishes status every 2 s: state, rate, delivered, target, alarm, `prescription_version`, `pending_version`, and `simulated`. | M | P1 |
| FR-12 | The hub validates every inbound MQTT payload against the schemas, adds a wall-clock `received_at`, stores it, and fans it out to browsers over server-sent events (SSE). | M | P1 |
| FR-13 | Both apps show live state and delivered volume, plus progress toward the day's goal in the family app. | M | P1, P4 |
| FR-14 | An occlusion (at minimum; also `bag_empty` and `low_battery`) shows in the family app as: picture, what happened, numbered steps to fix it, and a "Done" action. It goes through every available alert path (see NFR-A6). | M | P4 |
| FR-15 | The same alarm flags the patient in the portal, and the flag clears when `alarm_cleared` arrives. | M | P4 |
| FR-16 | Clearing an alarm needs a caregiver action **at the pump** (a button). After clearing, the pump goes to `paused`, not straight back to `running`. | M | P3 |
| FR-17 | Availability comes from a retained `online` message plus a retained Last Will of `offline`. Both apps show offline status and the time of the last update. | M | S6 |

### 6.3 Reporting

| ID | Requirement | Pri | Trace |
|---|---|---|---|
| FR-18 | The generated history covers 30 days for 3 fictional patients: on target, drifting under target, and repeated night occlusions. Every row has `simulated = true`. | S | S8, P4 |
| FR-19 | The patient list in the portal puts exceptions first. The rules: under target for 3 days, more than N alarms in a night, pump offline. | S | P4 |
| FR-20 | The patient detail page has a delivered versus prescribed chart and an alarm timeline. | S | P4 |
| FR-21 | A rule-based weekly summary as text. An LLM-drafted version is stretch only, and the rule-based one stays as the fallback. | S / X | P4 |
| FR-22 | Every screen that shows generated data carries a visible "Simulated data" label. | M | S8 |
| FR-23 | The audit view lists who proposed, who confirmed, when it was sent, and when the pump applied or rejected it. | M | S7 |
| FR-24 | FHIR export, mapped to `NutritionOrder.enteralFormula` [R14]. | X | — |

### 6.4 Accessibility and personalization

| ID | Requirement | Pri | Trace |
|---|---|---|---|
| FR-25 | All user-facing text comes from `strings.<lang>.js`: English plus one more language, with a language switch. | S | P5 |
| FR-26 | Night mode: dim, low blue, no flashing. `prefers-reduced-motion` is respected. | S | P5 |
| FR-27 | Spoken status through `speechSynthesis`, preferring voices with `localService === true` [R12]. | S | P5 |
| FR-28 | Feed profiles (for example "overnight continuous") that pre-fill a proposal. | S | P5 |
| FR-29 | Caregiver roles (parent, school nurse) recorded in the audit trail. Alert preferences per caregiver. | S | P5 |
| FR-30 | The pump's OLED shows rate, state, and "Updated remotely: v N". | S | P3 |

### 6.5 Stretch

| ID | Requirement |
|---|---|
| FR-X1 | A foil capacitive level sensor gives `level_pct`. If it disagrees with delivered volume, raise a `sensor_mismatch` alarm. |
| FR-X2 | An FPGA watchdog counts STEP pulses and cuts ENABLE if the step rate goes over a hard-wired maximum, latching a fault the ESP32 reports. |
| FR-X3 | Symptom logging and tolerance flags. |

## 7. Non-functional requirements

| ID | Area | Requirement |
|---|---|---|
| NFR-O1 | Offline | The whole system runs on the Pi with no internet: no CDN, no cloud SDK. Web assets are served by the hub. |
| NFR-O2 | Cost | Bill of materials: ESP32, Pi, stepper driver or LED, and optional OLED. No paid services. |
| NFR-R1 | Reliability | The firmware main loop never blocks: no `delay()` outside `setup()`. Reconnect is non-blocking, and the feed continues through wifi or broker loss (S6). |
| NFR-R2 | Reliability | The current prescription and version are persisted to NVS through `Preferences` and survive a reboot [R11]. |
| NFR-R3 | Reliability | The broker restart policy must not lose a confirmed prescription that has not been delivered yet (see R3). |
| NFR-R4 | Reliability | A lost pump event must not leave a prescription stuck at `sent` (see R1). |
| NFR-P1 | Performance | SSE fan-out to browsers in under 1 s from MQTT receipt. FastAPI's native SSE sends keep-alive pings every 15 s [R9]. |
| NFR-A1 | Accessibility | Touch targets at least 48×48 px, which is above WCAG 2.2 AA 2.5.8 (24×24) and AAA 2.5.5 (44×44) [R13]. Body text at least 18 px. |
| NFR-A2 | Accessibility | Contrast at least 4.5:1. Colour never carries meaning alone: always icon plus text. |
| NFR-A3 | Accessibility | Semantic HTML, labelled controls, visible focus, full keyboard operation. Live status uses `aria-live`. |
| NFR-A4 | Accessibility | Alerts in plain language with a cause and a fix. Never an error code on its own. |
| NFR-A5 | Accessibility | Voice input is optional, and a button always exists for the same action. |
| NFR-A6 | Accessibility | Alarms have a visual path plus at least one non-visual path. **`navigator.vibrate` does not work on iOS Safari or Firefox for Android [R12]**, so on those browsers the non-visual path is speech and/or an audio cue. Vibration also needs sticky user activation [R12], so the app asks for one tap on first load ("Enable alerts"). |
| NFR-S1 | Security (prototype) | Anonymous MQTT on a private network and no web authentication. Both are **disclosed as known gaps**. A real product would need TLS, per-device credentials, identity, roles, an SBOM, and penetration testing under FDA §524B cyber-device rules [R5]. |
| NFR-H1 | Honesty | A "Prototype, not for clinical use" footer on every page. A "Simulated data" label wherever it applies. |
| NFR-M1 | Maintainability | `shared/protocol/` is the contract. Change order: schema, example, firmware and sim together, then hub. |
| NFR-M2 | Testability | `make test` covers every endpoint and the unhappy paths: unconfirmed, out of range, stale version, pump offline. There is a limits parity test between firmware and sim. |

## 8. Interfaces

### 8.1 MQTT (existing contract, `shared/protocol/topics.md`)

| Topic | Direction | QoS | Retained |
|---|---|---|---|
| `pump/{id}/prescription` | hub to pump | 1 | yes |
| `pump/{id}/status` | pump to hub | 0 | no |
| `pump/{id}/event` | pump to hub | 1 (see R1) | no |
| `pump/{id}/availability` | pump to hub | 1 (Will) | yes |

### 8.2 HTTP API (proposed: the hub does not define it yet)

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/health` | any | Liveness (exists) |
| GET | `/api/patients` | clinician | List patients, exceptions first |
| GET | `/api/patients/{pid}` | clinician | Detail, daily totals, alarms |
| GET | `/api/pumps/{id}/status` | both | Latest status plus `received_at` plus `online` |
| GET | `/api/pumps/{id}/stream` | both | SSE: `status`, `event`, `availability`, `prescription` (lifecycle) |
| GET | `/api/pumps/{id}/prescriptions` | both | All versions with lifecycle state |
| POST | `/api/pumps/{id}/prescriptions` | clinician | Propose. Body: `mode`, `rate_ml_hr`, `volume_ml`, `note?`, `proposed_by` |
| POST | `/api/pumps/{id}/prescriptions/{v}/confirm` | caregiver | Confirm. Body: `confirmed_by`, `role` |
| POST | `/api/pumps/{id}/prescriptions/{v}/decline` | caregiver | Decline. Body: `declined_by`, `reason?` |
| GET | `/api/pumps/{id}/audit` | both | Append-only audit rows |
| GET | `/api/profiles` / POST | clinician | Feed profiles |

### 8.3 Data model

Tables as in `ARCHITECTURE.md`: `patients`, `prescriptions`, `status_samples`, `events`, `audit`, `profiles`. The ER diagram is in `ARCHITECTURE-DIAGRAMS.md` §9. The `audit` table is made append-only with `BEFORE UPDATE` and `BEFORE DELETE` triggers that call `RAISE(ABORT, …)` [R15]. That enforces S7 in the database itself, not only by convention.

## 9. Safety requirements traceability

| Invariant | Enforced where | Verified by |
|---|---|---|
| S1 Hard limits in the pump | `limits.h`, pump validation step 5 and 6 | Firmware unit test, sim test, limits parity test, demo step 5 |
| S2 Caregiver confirmation | Hub publish gate, plus pump check 3 | Hub test: publish without confirm raises. Sim test: missing `confirmed_by` gives `not_confirmed` |
| S3 Versions only go up | Hub version allocator, plus pump check 4 | Replay test: the retained message on reconnect causes no state change and no rejection when `v == current` |
| S4 No change mid-feed | Pump: apply only in `idle`, otherwise queue | Sim test: send during `running`, then `queued`, `pending_version` set, applied after `complete` then `idle` |
| S5 Active means pump said so | Only the MQTT ingest path sets `active` or `rejected` | Hub test: after publish the state is `sent`, not `active` |
| S6 Wifi loss does not affect the feed | Non-blocking loop, last accepted prescription in RAM and NVS | Bench test: pull the AP mid-feed |
| S7 Audit append-only | No UPDATE or DELETE in code, plus SQLite triggers | Test: UPDATE on `audit` raises `sqlite3.IntegrityError` |
| S8 Simulated labelled | `simulated` field, plus UI label | UI check on every screen; schema `required` |

## 10. Research-driven recommendations (decide before Phase 1)

Each item is a gap between the plan and the documented behaviour of the chosen tools. Excerpts are in `REFERENCES.md`.

| ID | Finding | Impact | Recommendation |
|---|---|---|---|
| **R1** | **PubSubClient "can only publish QoS 0 messages"** [R10]. `topics.md` specifies QoS 1 for `event`. | `prescription_rejected` or `alarm_raised` from the ESP32 can be lost. The hub would then leave the prescription at `sent` forever, which breaks M3 on hardware. | (a) Add optional status fields `last_rejected_version` and `last_reject_reason`, so S5-style "state from telemetry" also covers rejection. That is an additive change, allowed by the protocol rules. **Or** (b) switch to 256dpi `arduino-mqtt`, whose `publish(topic, payload, retained, qos)` supports QoS 1 [R10b]. **Recommend (a)**: it works with both libraries and needs no change to the firmware library rule. In either case, correct `topics.md` to say what the firmware actually does. |
| **R2** | PubSubClient's default `MQTT_MAX_PACKET_SIZE` is **256 bytes** including headers [R10]. `examples/prescription.json` is **249 bytes** compact, before the topic and MQTT header, and a 200-character note pushes it past 450. | The ESP32 silently fails to receive the prescription. **The core loop fails on hardware but works in the simulator.** | Call `mqtt.setBufferSize(1024)` before `connect()`. Add a test that the largest valid prescription fits in the firmware buffer. |
| **R3** | `scripts/mosquitto.conf` has `persistence false`. Retained messages are kept on disk only when persistence is on [R7]. | If the broker restarts while the pump is offline, the retained prescription is gone and the pump never gets it. | Set `persistence true` and `persistence_location` on the Pi. **And** have the hub re-publish the latest `sent` prescription when it starts and whenever availability goes to `online`. Duplicates are harmless because of S3. |
| **R4** | jsonschema does **not** enforce `format` by default, and `date-time` needs `rfc3339-validator` [R16]. | `proposed_at` and `confirmed_at` are never checked as timestamps in tests or in the hub. | Use `jsonschema[format]` in `requirements.txt` and pass `format_checker=Draft202012Validator.FORMAT_CHECKER`. |
| **R5** | FastAPI's native SSE (`fastapi.sse.EventSourceResponse`, with automatic keep-alive and anti-buffering headers) needs **FastAPI ≥ 0.135** [R9]. `requirements.txt` says `>=0.110`. paho-mqtt 2.x needs `CallbackAPIVersion` passed to `Client()` [R8]. Its network loop runs in its own thread, so handing messages to asyncio must use `loop.call_soon_threadsafe` [R17]. | An older FastAPI resolved on the Pi means no `fastapi.sse`. A cross-thread bug means SSE drops messages at random. | Pin `fastapi>=0.135`. Build the MQTT client with `CallbackAPIVersion.VERSION2`. Subscribe inside `on_connect` so subscriptions come back after a reconnect. Bridge into an `asyncio.Queue` with `call_soon_threadsafe`. |
| **R6** | The protocol says the pump rejects anything not newer than the current **and pending** versions, but the hub lifecycle has no rule for a pending vN replaced by vN+1. | The portal could show two "Sent" chips. | When vN+1 is `sent` while vN is `sent` and not yet active, mark vN `superseded` once the pump reports vN+1 pending or active. |
| **R7** | `navigator.vibrate` is not supported on iOS Safari (any version) or Firefox for Android, and needs sticky user activation [R12]. | An iPhone demo phone gets no vibration, and the rule "visual and vibration path" cannot be met there. | Use an Android Chrome phone for the demo. Add speech plus an audio cue as the non-visual path on iOS. Add an "Enable alerts" tap on first load. |
| **R8** | The Last Will is sent only on an *ungraceful* disconnect. A graceful `DISCONNECT` throws it away [R6]. | A sim that exits cleanly never shows as offline. | On graceful shutdown, the sim and firmware publish retained `offline` themselves before disconnecting. |

## 11. Risks (in addition to PLAN section 6)

| Risk | Likelihood | Mitigation |
|---|---|---|
| Hardware-only failure from R1 or R2 that the sim cannot show | High if not fixed | Fix R1 and R2 in Phase 3 entry. Bench test with a 200-character note. |
| Judges ask about standards | Medium | Name them honestly. IEC 60601-2-24 covers enteral nutrition pumps, including occlusion alarm thresholds [R18]. ISO 80369-3 (ENFit) covers connectors [R19]. FDA cybersecurity guidance (2023, updated 2025) applies to connected devices [R5]. **None was assessed.** |
| "This already exists" | Medium | Kangaroo Connect: history, attainment report, remote troubleshooting, software updates [R3]. Our differences: caregiver-confirmed remote programming with pump acknowledgement, and family-side interpretation. |

## 12. Milestones

As in PLAN section 5: P0 scaffold, P1 walking skeleton, P2 loop, P3 hardware ∥ P4 reporting, P5 accessibility, P6 hardening. **Add to the P0 or P1 exit checks:** R2, R3, R4, and R5 applied. Add R1 to the P3 entry check.

## 13. Open questions

From PLAN section 7, plus these from the research:

1. Which demo phone: iOS or Android? This decides R7.
2. R1: status-field redundancy, or swap the MQTT library?
3. Second language?
4. Is a clinician or a family available to check the alarm copy and the old-versus-new screen?
