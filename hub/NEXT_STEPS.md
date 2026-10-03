# Person B (Hub): where we are and what's next

Status as of 2026-10-03. Prototype demo only, not a medical device.

## Where we are

| Stage | Team status | Hub (Person B) status |
|---|---|---|
| Sync 1: skeleton | Passed | Done |
| Sync 2: loop on sim | Passed (PLAN phase 2 ticked) | Done: lifecycle, publish gate, "active" only from the pump, audit, safety review |
| Sync 3: loop on hardware | **Waiting on Person A** (firmware has no MQTT yet) | Nothing for the hub to change. The ESP32 should just work as `pump-001` |
| Sync 4: feature freeze | Not yet | Hub part done: alerts, patients and exceptions, daily totals, weekly summary, audit, profiles, history loading |
| Phase 6: demo hardening | Started | **We are here.** Reset command and boot services written, not yet tried on the Pi |

All hub tests pass (256) and lint is clean. The latest work is commit `c6a5a2d` on `lane/hub`, which has **not been pushed**.

## Next steps, in order

### 1. Hand the work back (today, 5 minutes)
- [ ] Push: `git push origin lane/hub` (from the `BioHack-2027-hub` worktree).
- [ ] Tell Person D it's ready to merge and pass on two things from the safety review:
  - Add a note to `shared/protocol/topics.md` and `docs/PROTOCOL.md`: an empty message on `pump/{id}/prescription` is a demo-reset clear, and the pump drops it.
  - Add an empty-message test case to `sim/test_pump_sim.py`.
- [ ] Ask D to tick B's boxes in `docs/TEAM.md` and the hub lines in `docs/PLAN.md` phase 4 (D owns `docs/`).
- [ ] Tell Person A: when the ESP32 gets MQTT, an empty prescription message must be silently dropped (no crash, no rejection).

### 2. Set up the Pi headless (needs internet once)
- [ ] Flash the SD card with Raspberry Pi Imager: hostname `smartpump`, username and password, SSH on, demo wifi name and password.
- [ ] `ssh <user>@smartpump.local`, clone the repo, check out `main` once D has merged.
- [ ] Run `scripts/setup_pi.sh`, then `hub/deploy/install_services.sh smartpump`.
- [ ] Reboot. Check `http://smartpump.local:8000/clinician/` loads from the laptop.
- [ ] Give the Pi a fixed IP on the router. Bookmark `http://<ip>:8000/family/` on the demo phone, since some Android phones can't open `.local` addresses.
- [ ] Run `make history` on the Pi so the 30-day data ends today.

### 3. First real run-through on the Pi with the sim
- [ ] Start the sim from a laptop with `MQTT_HOST=<pi ip> python -m sim.pump_sim --demo-seed`.
- [ ] Run the phase 2 check: propose 90, confirm on the phone, chip goes Pending, Sent, Active on pump. Then propose 500 and confirm it: Rejected, rate out of range.
- [ ] Try the reset:
  - `sudo systemctl stop smart-pump-hub`
  - `.venv/bin/python -m hub.reset`
  - `sudo systemctl start smart-pump-hub`
  - Restart the sim with `--demo-seed`.
  - Check the pump comes back at v7, 60 mL/hr, idle, and does **not** pick up the old v8.
- [ ] Check what the portal shows for v7 right after a reset, when the hub has no record of v7 yet. Report anything odd to Person C.
- [ ] Unplug the Pi's power and plug it back in. Check that everything comes back by itself.

### 4. Support the rest of the team
- [ ] Sync 3: be on the broker with `mosquitto_sub -t 'pump/#' -v` while A brings the ESP32 online. Make sure only one pump is using `pump-001`.
- [ ] Sync 4: run the occlusion check (phone alert in 3 seconds or less, portal flags the patient) against the real hub on the Pi.
- [ ] Fix any API issues Person C reports.

### 5. Demo day (you are the Pi operator and backup)
- [ ] Before you walk up:
  - Set the Pi's clock if it's offline (`sudo date -s "..."`).
  - Run the reset.
  - Check the pump shows online at v7.
- [ ] Keep a laptop SSH session open with `journalctl -u smart-pump-hub -f`.
- [ ] Fallback if the ESP32 fails: start the sim with the same `PUMP_ID` (stop the ESP32 first).
- [ ] Shut down with `sudo shutdown now`, never by pulling the power.

## Quick reference

| Task | Command |
|---|---|
| Hub logs on the Pi | `journalctl -u smart-pump-hub -f` |
| Restart the hub | `sudo systemctl restart smart-pump-hub` |
| Demo reset | stop the hub, then `.venv/bin/python -m hub.reset`, then start the hub |
| Watch MQTT | `mosquitto_sub -t 'pump/#' -v` |
| Hub tests | `.venv/Scripts/python -m pytest hub/tests` (Windows) |
