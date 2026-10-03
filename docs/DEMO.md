# Demo script

Target: about three minutes of live demo. Rehearse it timed. Adjust once the slot length is known. The talk and slides around it are in `PITCH.md`.

## Setup before you walk up

- Hub laptop on the demo network with `make docker-up` running (Docker path not yet tested end to end; fallback: B's `hub/deploy/laptop.ps1`) (broker and hub in Docker), pump online (or `make docker-sim`). Without Docker: `make broker` and `make hub`
- Laptop on the clinician portal, phone on the family app, both on the demo network
- System reset to the starting state: version 7 active at 60 mL/hr, pump idle. With the hub and simulator stopped and the broker up, run `make reset-demo`, then `make hub` and `python -m sim.pump_sim --demo-seed`. In Docker: `make docker-reset`, then start the pump
- Rehearse steps 6 to 8 hands-free with `python -m sim.pump_sim --demo-seed --scenario occlusion --speed 60`. On stage, use the keys (`s`, `o`, `c`, `p`) so the presenter controls the timing
- Fallbacks ready: simulator, screen recording
- Exactly one pump per `PUMP_ID` on the broker. A leftover `make sim` with the same id as the ESP32 makes both flap online and offline every second. Check with `mosquitto_sub -t 'pump/+/availability' -v`.
- Ubuntu's own Mosquitto service disabled (`sudo systemctl disable --now mosquitto`), or `make broker` cannot bind port 1883

## Script

| Step | Who | Action | What the audience sees |
|---|---|---|---|
| 1 | Presenter | One sentence on the problem | Slide |
| 2 | Clinician | Opens the dashboard | Three fictional patients, the one who needs attention at the top, "Simulated data" label |
| 3 | Clinician | Proposes 90 mL/hr | Status chip: Pending |
| 4 | Caregiver | Phone shows the change, old versus new; confirms (by voice if available, else the button) | Chip: Sent, then Active on pump. Pump display or motor changes |
| 5 | Clinician | Proposes an out-of-range rate | After the caregiver confirms, the chip shows Rejected: rate out of range. Pump unchanged |
| 6 | Caregiver | Starts a feed | Progress rises on the phone |
| 7 | Presenter | Presses the occlusion button (or pinches the line) | Phone vibrates and shows what happened and what to do, with a picture. Portal flags the patient |
| 8 | Caregiver | Clears it, feed resumes | Alert clears on both screens |
| 9 | Caregiver | Switches language and night mode | Same screen, second language, dim theme |
| 10 | Presenter | Audit trail and the honest list of gaps | Slide or portal screen |

## Lines worth saying

- "The portal says active only when the pump itself reports the new version."
- "The pump refused that change on its own. The limit is in the device, not the app."
- "Everything you saw is running on one laptop with no internet."
- "This is a prototype with simulated data. Here is what a real product would still need."

## If something breaks

- Pump offline: say so, switch to the simulator (`make sim`), carry on. The offline indicator is itself a feature.
- Phone will not connect: use the family app in a second browser window on the laptop.
- Everything down: play the recording and talk over it.
