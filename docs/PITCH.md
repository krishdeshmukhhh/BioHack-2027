# Pitch outline

Started at Sync 2, as `TEAM.md` asks. Owner: Person D (presenter). The live demo runs from `DEMO.md`; this page is the talk around it.

Rules for every slide (from `.claude/rules/safety.md`): say "prototype" and "demo", never imply clinical readiness, and give no clinical guidance. Every number on a slide has a source in `research/REFERENCES.md`. Claims marked ⚠ are unverified; check them or drop them before the final deck.

## Timing (draft, for a 5-minute slot; adjust when the slot is known)

| Part | Time | Slides |
|---|---|---|
| Problem and what exists | 0:45 | 1 to 3 |
| Our loop, in one picture | 0:30 | 4 |
| Live demo (`DEMO.md` steps 2 to 9) | 2:45 | none (screens) |
| Safety design, honest gaps, cost, next steps | 1:00 | 5 to 8 |

Rehearse with a timer (Sync 5). If the slot is 3 minutes, cut slides 3 and 7 and demo steps 6 to 9.

## Slides

### 1. Title

"Smart Pump: caregiver-confirmed remote programming for home tube feeding." Team names. A visible line: "Prototype. Simulated data. Not connected to a person."

### 2. The problem

- Families tube feeding at home program the pump by hand at the bedside; changes from the clinic travel by phone or paper (`PLAN.md` §1).
- Carers often lack training and written information: in one survey only 8% had read written guidance [R1].
- Support after discharge can be slow: some patients were not contacted for seven days or more [R2].
- ⚠ Poor understanding of pump alarms and disturbed sleep at night are reported [R1, search summary only].

Say: one sentence, then the 8% number. Do not read the bullets.

### 3. What exists today

- Kangaroo Connect is described as the first enteral pump with wireless connectivity, with feeding history, attainment reports, remote troubleshooting and remote software updates [R3, ⚠ search summary].
- The data flows one way, to clinicians and support staff.
- Our differentiator: **remote prescription changes that the caregiver confirms and the pump itself acknowledges.** We found no public evidence of this [R3].

⚠ **Before the final deck, someone reads the Kangaroo Connect operator manual (link in R3) and confirms this claim.** If it is wrong, reword to "we focus on…" rather than "nobody does…".

### 4. Our loop (one diagram)

Clinician proposes → caregiver confirms on the phone → hub publishes → **pump checks its own limits** → pump reports the new version → portal says "Active on pump".

Say: "The portal says active only when the pump itself reports the new version." Use the closed-loop diagram from `research/ARCHITECTURE-DIAGRAMS.md` §4, simplified to five boxes.

→ Live demo here (`DEMO.md`).

### 5. Safety by design (defence in depth)

Show S1 to S8 as plain sentences, grouped:

- **The pump decides:** hard limits compiled into the firmware; out-of-range is rejected and reported, never clamped (S1). Versions only go up (S3). Changes only apply when idle (S4). Losing wifi never stops a feed (S6).
- **People decide:** no prescription reaches the pump without a caregiver confirmation (S2).
- **The screen tells the truth:** "active" only from pump telemetry (S5); simulated data is labelled (S8); the audit log is append-only (S7).
- How we checked: an independent safety review ran before every merge and caught real bugs. Example: a path where the hub could re-send a replaced prescription. Fixed with a regression test.

Say: "The pump refused that change on its own. The limit is in the device, not the app." (Person A gives the 30-second version.)

### 6. Accessibility is a feature

One-handed night use: large targets, pictures with numbered steps for alarms, spoken status, vibration (Android), second language, night mode. Screenshots from Person C.

### 7. Cost

Bill of materials (fill in real prices from receipts; do not estimate on the slide):

| Part | Price |
|---|---|
| ESP32 dev board | ___ |
| Hub computer: any laptop for the demo; a small single-board computer in a real product | ___ |
| Stepper and driver, or LED stand-in | ___ |
| Buttons, optional OLED | ___ |
| Software and services | 0 (open source, no cloud, runs offline on the hub laptop) |

Say: the argument is "no cloud and no subscription", not "cheaper than a medical pump". We have not costed a certified device.

### 8. Honest gaps and next steps

From `SAFETY.md` "Known gaps", said out loud:

- No real authentication; demo users are fixed. Anonymous MQTT on a private network (would need TLS and per-device credentials).
- One global set of demo limits; a real system needs per-patient limits set through a controlled process.
- Delivery is measured from motor steps or modelled; no independent flow measurement.
- No regulatory work: a real product would need IEC 60601-2-24 [R18], ENFit connectors (ISO 80369-3) [R19], FDA cybersecurity expectations such as an SBOM and penetration testing [R5], design controls, risk management and usability studies.

Next steps: per-patient limits, real identity and roles, independent flow sensing (stretch: level sensor), and clinical partners to test the workflow with families.

Close: "Everything you saw is running on one laptop with no internet. It is a prototype with simulated data; here is what a real product would still need."

## Assets to collect

- [ ] Screenshots from C: family live page, "Change to review", alert screen, night mode, portal with chips (Sync 4)
- [ ] Photo of the physical prop from A, labelled "Prototype, not connected to a person"
- [ ] Real BOM prices (A)
- [ ] Kangaroo Connect manual check (anyone, before Sync 4)
- [ ] Screen recording of a clean demo run as the fallback (Sync 5)
