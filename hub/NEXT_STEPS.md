# Person B (Hub): where we are and what's next

Updated 2026-10-03 (evening). Prototype demo only, not a medical device.

## Where we are

| Stage | Team status | Hub (Person B) status |
|---|---|---|
| Sync 1: skeleton | Passed | Done |
| Sync 2: loop on sim | Passed (PLAN phase 2 ticked) | Done: lifecycle, publish gate, "active" only from the pump, audit, safety review |
| Sync 3: loop on hardware | **Waiting on Person A** (firmware has no MQTT yet) | Nothing for the hub to change. The ESP32 should just work as `pump-001` |
| Sync 4: feature freeze | Not yet | Hub part done: alerts, patients and exceptions, daily totals, weekly summary, audit, profiles, history loading |
| Phase 6: demo hardening | Started | **We are here.** Boot services written; Pi not set up yet |

`lane/hub` is pushed and up to date with `origin/main`. Hub tests pass.

## Done since the last update
- [x] Pushed `lane/hub` (reset command, Pi boot services, this file).
- [x] Merged `origin/main` into `lane/hub`. Person D had added `make reset-demo` (`scripts/reset_demo.sh`), which does what our `hub.reset` did and also regenerates history to end today. We removed `hub.reset`, so `make reset-demo` is the only reset command.

## Next steps, in order

### 1. Hand-off messages (send now)
- [ ] **To Person D (lead):**
  - Please merge `lane/hub`. It adds `hub/deploy/install_services.sh` (systemd services for the broker and hub) and removes the duplicate `hub.reset` in favour of `make reset-demo`.
  - The safety review asked for a note in `topics.md`/`PROTOCOL.md`: a zero-byte message on `pump/{id}/prescription` is the demo-reset clear, and the pump drops it silently. Consider adding it as a case in `prescription_cases.json`, so the sim and the firmware both test it.
  - Please tick B's boxes in `docs/TEAM.md`. Everything through "Before Sync 4" is built.
- [ ] **To Person A (firmware):**
  - `make reset-demo` sends an empty retained message on `pump/pump-001/prescription`. The ESP32 must drop it silently (no crash, no `rejected` event).
  - The shared test cases are in `shared/protocol/cases/prescription_cases.json`.

### 2. Set up the Pi headless (needs internet once)
- [ ] Flash the SD card with Raspberry Pi Imager:
  - Raspberry Pi OS Lite, 64-bit.
  - In the settings (gear icon): hostname `smartpump`, a username and password, SSH on, and the demo wifi name and password.
- [ ] Boot it, then from the laptop: `ssh <user>@smartpump.local`.
- [ ] On the Pi:
  ```bash
  sudo apt-get install -y git
  git clone https://github.com/krishdeshmukhhh/BioHack-2027.git && cd BioHack-2027
  git checkout main          # after D merges lane/hub; until then: git checkout lane/hub
  scripts/setup_pi.sh
  hub/deploy/install_services.sh smartpump
  make history
  sudo reboot
  ```
- [ ] After the reboot, open `http://smartpump.local:8000/clinician/` on the laptop.
- [ ] Give the Pi a fixed IP on the router. Bookmark `http://<ip>:8000/family/` on the demo phone, since some Android phones can't open `.local` addresses.

### 3. First real run-through on the Pi with the sim
- [ ] On the laptop: `MQTT_HOST=smartpump.local python -m sim.pump_sim --demo-seed` (on Windows PowerShell: `$env:MQTT_HOST="smartpump.local"; .venv/Scripts/python -m sim.pump_sim --demo-seed`).
- [ ] Phase 2 check:
  - Propose 90, confirm on the phone. The chip should go Pending, Sent, Active on pump.
  - Propose 500 and confirm it. It should show Rejected, rate out of range.
- [ ] Reset check:
  - Quit the sim (`q`).
  - On the Pi: `sudo systemctl stop smart-pump-hub && make reset-demo && sudo systemctl start smart-pump-hub`.
  - Restart the sim with `--demo-seed`.
  - The pump should come back at v7, 60 mL/hr, idle, and **not** pick up the old v8.
  - Note: `reset_demo.sh` checks for a running sim only on the Pi itself. A sim on the laptop has to be quit by hand.
- [ ] Look at the portal right after the reset, when the hub has no record of v7. Report anything odd to Person C.
- [ ] Unplug the Pi's power, plug it back in, and check that everything comes back by itself.

### 4. Support the rest of the team
- [ ] Sync 3: watch `mosquitto_sub -h smartpump.local -t 'pump/#' -v` while A brings the ESP32 online. Make sure only one pump is using `pump-001`.
- [ ] Sync 4: run the occlusion check against the Pi: phone alert in 3 seconds or less, and the portal flags the patient.
- [ ] Fix any API issues Person C reports.

### 5. Demo day (you are the Pi operator and backup)
- [ ] Before you walk up:
  - If the Pi is offline, set its clock: `sudo date -s "..."`.
  - Run the reset (see step 3).
  - Check the pump shows online at v7.
- [ ] Keep a laptop SSH session open with `journalctl -u smart-pump-hub -f`.
- [ ] If the ESP32 fails: switch it off, then start the sim with the same `PUMP_ID`.
- [ ] Shut down with `sudo shutdown now`, never by pulling the power.

## Quick reference

| Task | Command (on the Pi) |
|---|---|
| Hub logs | `journalctl -u smart-pump-hub -f` |
| Restart the hub | `sudo systemctl restart smart-pump-hub` |
| Demo reset | `sudo systemctl stop smart-pump-hub && make reset-demo && sudo systemctl start smart-pump-hub` |
| Watch MQTT | `mosquitto_sub -t 'pump/#' -v` |
| Update code | `git pull && sudo systemctl restart smart-pump-hub` |
