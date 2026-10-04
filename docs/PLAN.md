# Project plan

Bio Hack 2026. Prototype, not a medical device.

## 1. Problem and goals

Families tube feeding at home use pumps that are programmed by hand at the bedside. Connected pumps exist, but the data mostly flows one way, to clinicians and support staff. Families get a small screen and alarms.

Our two goals (from the whiteboard):

1. Better communication and monitoring of a smart pump.
2. Better accessibility and personalization, while keeping costs low.

Our deliverables:

| Deliverable | What we will show |
|---|---|
| Remote programming | Clinician proposes, caregiver confirms, pump checks limits and applies, portal shows "active on pump" only after the pump acknowledges |
| Collect and monitor feeding | Live pump state and delivered volume, alarms with plain-language cause and fix |
| Report back data | Exception-based clinician dashboard, delivered versus prescribed, weekly summary |
| Easy interaction for accessibility | Family app built for one-handed night use: large targets, pictures, two languages, spoken status, night mode, vibration alerts |
| Personalization | Saved feed profiles, caregiver roles, alert preferences |

## 2. What we are building

Four parts, one loop. Details in `ARCHITECTURE.md`.

- **Pump** (ESP32): state machine, hard limits, MQTT. A motor if we have one, otherwise an LED or display stand-in with modelled delivery.
- **Hub** (one laptop running Docker; the Pi broke): MQTT broker, API, SQLite, serves the web apps. Works with no internet.
- **Clinician portal** and **family app** (static web pages).
- **Simulator**: a software pump identical on the wire, plus generated history. Unblocks software work and is our fallback on demo day.

## Decisions log

- 2026-10-03: the Raspberry Pi broke. The hub runs on one laptop in Docker (`compose.yaml`); `hub/deploy/laptop.ps1` is the native fallback.
- 2026-10-03: the Next.js dashboard in `web/dashboard/` is adopted as the main UI (port 3000). The hub-served static apps stay as the fallback. Rules updated in `CLAUDE.md` and `.claude/rules/web.md`; it needs a safety and accessibility review before the demo.

## 3. Scope

**Must have (the demo fails without these)**

- Remote programming loop end to end, including a rejected out-of-range change
- Live status in both apps
- One injected fault (occlusion) producing a plain-language alert in the family app and a flag in the portal
- Family app meeting the accessibility rules
- Audit trail of who proposed, who confirmed, when the pump applied

**Should have**

- Exception dashboard on 30 days of generated history
- Second language, night mode, spoken status
- Feed profiles and caregiver roles
- OLED on the pump showing rate and "updated remotely"

**Stretch (only after everything above works)**

- Foil capacitive level sensor as an independent delivery check (`sensor_mismatch` alarm)
- FPGA watchdog on the motor step line
- FHIR export of feeding data
- LLM-drafted weekly summary (needs internet, so keep a rule-based fallback)
- Symptom logging and tolerance flags

**Out of scope**

- Real patients, real clinical data, clinical guidance
- User accounts with real authentication (we use fixed demo users and say so)
- Native mobile apps, cloud hosting

## 4. Team roles

The detailed 4-person split, with personal checklists, sync points, and hand-offs, is in `TEAM.md`.

Adjust to who you have. One person can hold two roles.

| Role | Owns | Subagent to use |
|---|---|---|
| Firmware | `firmware/`, wiring, bench testing | `firmware-engineer` |
| Hub | `hub/`, the hub laptop (Docker), the broker | `hub-engineer` |
| Web | `web/`, accessibility checks | `web-engineer` |
| Sim, data, and pitch | `sim/`, demo script, slides | `sim-engineer` |

Everyone: run `safety-reviewer` on changes that touch prescriptions, limits, or the state machine.

## 5. Phases

Each phase ends with an acceptance check you can show to someone. Do not start the next phase until the check passes. Phases 3 and 4 can run in parallel with different people once phase 2 is done.

### Phase 0: Scaffold (this commit)

- [x] Repo structure, CLAUDE.md, rules, agents
- [x] Protocol schemas with validated examples
- [x] Stubs that build and a passing test suite
- [ ] Everyone clones, runs `make setup` and `make test`
- [ ] Hub laptop set up with Docker (`make docker-up`); the Pi broke
- [ ] Decide: do we have a motor or pump head? If not, set `DELIVERY_SIMULATED 1` and plan an LED or display stand-in
- [ ] Fill in the time budget in section 8

**Check:** `make test` passes on every laptop, and `make docker-up` works on the hub laptop.

### Phase 1: Walking skeleton (data flows one way, pump to screen)

- [x] `sim/pump_sim.py`: connects to the broker, publishes `availability` and a `status` every 2 seconds, runs a feed from a hard-coded prescription
- [x] `hub`: MQTT bridge subscribes to status, event, availability; validates against schemas; stores in SQLite
- [x] `hub`: `GET /api/pumps/{id}/status` (latest) and a server-sent events stream
- [x] `web/family`: one bare page showing live state and delivered volume
- [x] Hub serves `web/` as static files

**Check:** start broker, hub, sim; open the family page on a phone on the same network; watch delivered volume rise.

### Phase 2: Remote programming loop (the core)

- [x] `hub`: tables for prescriptions and audit; lifecycle proposed, confirmed, sent, active, rejected, superseded
- [x] `hub`: `POST /api/pumps/{id}/prescriptions` (clinician proposes), `POST .../{version}/confirm` and `.../decline` (caregiver)
- [x] `hub`: single publish gate that refuses anything unconfirmed (S2); retained, QoS 1
- [x] `sim`: validate in order (shape, confirmation, version, limits); reject with reason; queue if not idle; apply when idle; report version in status
- [x] `hub`: set `active` or `rejected` only from pump events and status (S5)
- [x] `web/clinician`: propose form and a status chip (Pending, Sent, Active on pump, Rejected with reason)
- [x] `web/family`: "Change to review" screen with old versus new and Confirm or Decline
- [x] Tests for unhappy paths: unconfirmed, out of range, stale version, pump offline
- [x] Run `safety-reviewer`

**Check:** propose 90 mL/hr in the portal, confirm on the phone, see the chip go Pending, Sent, Active on pump. Then propose 500 mL/hr and see Rejected: rate out of range.

### Phase 3: Real hardware

- [x] Firmware: wifi and MQTT with Last Will, non-blocking reconnect
- [x] Firmware: state machine with a single `transitionTo()`
- [x] Firmware: prescription validate, queue, apply, persist to NVS; same reasons as the sim
- [x] Firmware: actuator interface with a stepper implementation or an LED stand-in; delivered volume from steps or from time and rate
- [x] Firmware: fault buttons (occlusion, bag empty, pause)
- [ ] Optional: OLED showing rate, state, and "updated remotely, version N"
- [ ] Bench: calibrate `STEPS_PER_ML` with a measuring cup if using a real pump head (n/a while DELIVERY_SIMULATED=1)
- [x] Bench: pull wifi mid-feed and confirm the feed continues (S6) (Person A, real ESP32: 30 s outage, feed continued, settings unchanged; firmware/phase3/)
- [x] Run `safety-reviewer`

**Check:** repeat the phase 2 check with the ESP32 in place of the simulator, with no changes to the hub or web apps.

### Phase 4: Feedback and reporting

- [x] Hub: map alarms to plain-language cause and steps (content in the strings file)
- [x] Family app: alert screen with picture, steps, and vibration; daily progress toward goal
- [x] Sim: scripted scenarios with a time-speed factor; fault injection from the keyboard
- [x] Sim: `generate_history.py`, 30 days for three fictional patients (on target, drifting under target, repeated night occlusions)
- [x] Hub: daily totals, delivered versus prescribed, exception rules (under target for 3 days, more than N alarms per night, pump offline)
- [x] Clinician portal: patient list with exceptions first; patient detail with a delivered versus prescribed chart and alarm timeline
- [x] Clinician portal: weekly summary (rule-based text)
- [x] "Simulated data" label wherever generated history is shown (S8)

**Check:** press the occlusion button; within a few seconds the family app shows what happened and what to do, and the portal flags the patient. The dashboard shows the three fictional patients sorted by who needs attention.

Rehearsed on the simulator, 2026-10-03 (`--scenario occlusion`): the SSE `alert` reached the hub stream and the dashboard proxy 49 ms after the pump's `alarm_raised`; the portal `alarm_active` flag appeared after 1.2 s and cleared 1.2 s after `alarm_cleared` (status every 2 s, so always under 3 s); the dashboard lists the three patients. Still to do by a person: the same on a phone with the ESP32.

### Phase 5: Accessibility and personalization

- [x] Strings file with English plus one more language; language switch (Spanish; needs a native-speaker check)
- [x] Night mode; `prefers-reduced-motion` respected
- [x] Spoken status with speech synthesis; optional voice confirm with a button fallback (voice confirm hardened 2026-10-03: exact yes/no only, version pinned)
- [ ] Contrast, focus order, labels, and screen reader pass on every family screen
- [x] Feed profiles (for example overnight continuous, daytime bolus) that pre-fill a proposal
- [ ] Caregiver roles (parent, school nurse) recorded in the audit trail; alert preferences per caregiver

**Check:** complete the confirm flow using only a screen reader, and again in the second language in night mode.

### Phase 6: Demo hardening

- [ ] Write and rehearse `docs/DEMO.md` at least three times, timed
- [ ] Run the whole demo with the internet off
- [ ] Fallback 1: simulator in place of the ESP32. Fallback 2: a screen recording
- [ ] Fixed IP for the hub laptop; phone and laptop pre-joined to the demo network
- [x] Reset script that returns the system to the starting state (`make reset-demo`, `make docker-reset`)
- [ ] Slides: problem, what exists today, our loop, safety design, cost argument, limits of the prototype, next steps
- [ ] Freeze code one hour before judging

**Check:** two clean run-throughs in a row, one on hardware and one on the fallback.

### Open review findings (owner, severity)

Collected from the safety reviews so nothing is lost between chat threads. Tick when fixed.

- [x] (fixed by D, with `web/_mock/test_rx_merge.py`) C, medium (S5 display): `web/shared/data.js` `rank()` ties active, rejected and superseded with `>=`, so an older REST copy can show two "Active on pump" chips. Rank superseded above active and use `>`.
- [ ] C, medium: audit view shows raw codes (`applied_by_pump`, `superseded_by_N`, `alarm_raised`, ...) and alert ids in the Version column (`web/clinician/audit.js`).
- [ ] C, medium (web.md 18 px): family texts at 14 to 16 px: status and alarm lines, last-update time, Now/New tags, hints, sim label, footer.
- [ ] C, low: a repeated identical alarm may not be re-announced to screen readers (`web/family/alert.js`).
- [ ] C, low: the prototype footer is filled by JavaScript only; put the text in the HTML.
- [ ] C, low: first rail link always `aria-current="page"`; one alarm can cue twice when its key gains `raised_at`.
- [x] React dashboard reviewed 2026-10-03: pass with notes. D fixed raw error keys (`errorKey`) and `.`/`..` proxy segments. Open for C:
- [ ] C, medium (dashboard): family text below 18 px (review rows 14/12 px, state line, hints, buttons 16 px, chips and sim label 12 px, footer 12 px, nav 11 px).
- [ ] C, medium (dashboard): alert card has no picture, start time, or "cleared" message and announcement; port from `web/family/alert.js`.
- [ ] C, low (dashboard): ~30 strings inline in `lib/locale.tsx` and units hard-coded; move to `strings.en.js`/`strings.es.js`. Review names `clin-01` instead of `proposed_by`; no "changed" markers; no live announcement of a new proposal; no `refreshLists` after a 409.
- [ ] C, low (dashboard): offline time without a label; Sent chip ignores `rx_sent_offline`; profiles without a Simulated label; stale chart data with no notice; summary control 45 px; focus ring clipped by `overflow-hidden`.
- [ ] B, low: a status that arrives after `alarm_cleared` can reopen the alert and count twice for `night_alarms`.
- [ ] A, medium: network task stack raised to 10 KB (26ec146); still read the bench's stack high-water marks for both tasks with a 2 KB prescription before the demo (S6 if it overflows).
- [x] A: duplicate JSON keys rejected (firmware and sim, shared cases); no `prescription_queued` while idle on a failed persist (now in PROTOCOL.md; sim matches); bench replay is non-retained.
- [ ] A, low: rate-limit the NVS retry while idle and log the first failure; bench tools must never target the demo hub database; settle escaped-NUL keys and nesting deeper than 10 with a shared case (firmware drops, sim may reject).
- [ ] C, blocking for the redesign (held off main 2026-10-03, user decision): "dashboard redesign shell" (5541c6d) needs: no fabricated heart rate / oxygen (remove, or off by default with a large on-screen label), the family view at `/` scoped to the caregiver's own pump (no roster, no ward map), no hospital-ward framing on the family side, text at least 18 px on the family view, and no locked scrolling on phones. Then the lead re-reviews and re-merges.
- [ ] D: test the Docker stack (`compose.yaml`) end to end, including phones over the LAN.

## 6. Risks

| Risk | What we do about it |
|---|---|
| Hardware not ready or fails on stage | Simulator is wire-identical; switching is one command |
| Venue wifi unreliable | Everything runs on the hub laptop with no internet; bring our own travel router or use a hotspot with mobile data off |
| No motor or pump head | LED or display stand-in with modelled delivery, labelled as simulated |
| Speech recognition needs internet in some browsers | Spoken output only is the baseline; voice input is optional and always has a button |
| Firmware and simulator drift apart | Shared schemas, a limits parity test, `safety-reviewer` |
| Judges ask "is this safe?" | `SAFETY.md`: invariants, the confirm step, hard limits, the rejected-change demo, and an honest list of gaps |
| Judges ask "doesn't this exist?" | Know the current pumps: history and remote troubleshooting exist; our contribution is the closed loop, the family side, and interpretation |
| Scope creep | Must, should, stretch list above; stretch only after phase 5 |

## 7. Open questions

- Do we have a motor, a pump head, or an OLED?
- How long is the demo slot, and is there a Q and A?
- Is there a clinician or a family we can ask about real pain points before the pitch?
- Which second language?

## 8. Time budget

Fill in once the deadline is known. A rough split of working time:

| Phase | Share |
|---|---|
| 1 Walking skeleton | 10% |
| 2 Remote programming loop | 25% |
| 3 Hardware | 20% (parallel with 4) |
| 4 Feedback and reporting | 20% (parallel with 3) |
| 5 Accessibility and personalization | 10% |
| 6 Demo hardening | 15% |
