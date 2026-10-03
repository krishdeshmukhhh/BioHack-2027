# Safety design

This is a hackathon prototype. It is not a medical device, has not been tested as one, and must never be connected to a person. All patient data in this project is fictional.

Remote programming of a pump is the riskiest thing we do, so the design is built around a short list of invariants. They are numbered so code, reviews, and the pitch can refer to them.

## Invariants

**S1. Hard limits live in the pump.**
Rate and volume limits are compile-time constants in `firmware/include/limits.h`. A prescription outside them is rejected and reported. It is never clamped to the nearest allowed value, because a silently changed dose is worse than a refused one. Limits cannot be changed over the network.

**S2. Nothing reaches the pump without a caregiver's confirmation.**
The hub publishes a prescription only after a caregiver confirms it. The pump independently rejects any prescription without confirmation fields.

**S3. Versions only go up.**
Each prescription has a version one higher than the last. The pump ignores anything not newer than what it has, which also makes retained and repeated messages harmless.

**S4. No change mid-feed.**
A prescription is applied only when the pump is idle. Otherwise it is queued and applied when the feed ends.

**S5. "Active" means the pump said so.**
The portal shows a prescription as active only after pump telemetry reports that version. Sending is not the same as applying.

**S6. Connectivity loss never affects a feed.**
If wifi or the broker drops, the pump continues the last accepted prescription. The hub shows the pump as offline with the time of the last update.

**S7. The audit log is append-only.**
Who proposed, who confirmed, when it was sent, when the pump applied or rejected it. Rows are never changed or deleted.

**S8. Simulated data is labelled.**
In the data (`"simulated": true`) and on every screen that shows it.

## Defence in depth

| Layer | What it stops |
|---|---|
| Portal form validation | Typos |
| Hub validation and confirmation gate | Unconfirmed or malformed prescriptions |
| Caregiver review of old versus new | Changes that look wrong to the person at the bedside |
| Pump limit check | Anything out of range, whatever the hub does |
| FPGA watchdog (stretch) | A motor running too fast because of a firmware bug |

## Known gaps (say these out loud in the pitch)

- No real authentication. Demo users are fixed. A real system needs clinician and caregiver identity, and roles.
- The MQTT broker accepts anonymous connections on a private network. A real system needs TLS and per-device credentials.
- Limits are one global set of demo values. A real system needs per-patient limits set by a clinician through a controlled process.
- Delivery is measured from motor steps or modelled from time. There is no independent flow measurement unless the level sensor stretch goal is done.
- No regulatory work has been done. A real product would need design controls, risk management, electrical safety, software lifecycle, usability, and cybersecurity documentation.
- Values in this repo are demo values, not clinical guidance.
