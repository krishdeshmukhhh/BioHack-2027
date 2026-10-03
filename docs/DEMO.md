# Demo script

Target: about three minutes of live demo. Rehearse it timed. Adjust once the slot length is known.

## Setup before you walk up

- Pi on, `make broker` and `make hub` running, pump (or `make sim`) online
- Laptop on the clinician portal, phone on the family app, both on the demo network
- System reset to the starting state: version 7 active at 60 mL/hr, pump idle
- Fallbacks ready: simulator, screen recording

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
- "Everything you saw is running on a Raspberry Pi with no internet."
- "This is a prototype with simulated data. Here is what a real product would still need."

## If something breaks

- Pump offline: say so, switch to the simulator (`make sim`), carry on. The offline indicator is itself a feature.
- Phone will not connect: use the family app in a second browser window on the laptop.
- Everything down: play the recording and talk over it.
