# Person B (Hub): where we are and what's next

Updated 2026-10-03 (evening, after the Pi was replaced by Docker). Prototype demo only, not a medical device.

## Where we are

| Stage | Team status | Hub (Person B) status |
|---|---|---|
| Sync 1: skeleton | Passed | Done |
| Sync 2: loop on sim | Passed | Done: lifecycle, publish gate, "active" only from the pump, audit, safety review |
| Sync 3: loop on hardware | `lane/fw` merged; bench checks still open (Person A) | Nothing for the hub to change. The ESP32 should just work as `pump-001` |
| Sync 4: feature freeze | Not yet | Hub part done (ticked in `docs/TEAM.md`) |
| Phase 6: demo hardening | Started | **We are here.** The Pi broke; the hub now runs in Docker on the hub laptop (`compose.yaml`). Not yet run end to end |

`lane/hub` is merged into `main`. On Windows all 360 tests pass and lint is clean (the UTF-8 test fix is in `main`).

Done in this session:
- Fixed the Windows-only failure: `shared/protocol/test_examples.py` and `sim/test_protocol_cases.py` now read files as UTF-8.
- `topics.md` and `PROTOCOL.md` now say the demo reset's zero-byte retained message is dropped silently by the pump (safety review follow-up).
- `scripts/reset_demo_docker.sh` refuses to run while a `make docker-sim` simulator is still up. `docker compose stop` does not stop `docker compose run` containers, so a forgotten sim would have kept the old v8.
- The Pi steps below are gone. `scripts/setup_pi.sh` and `hub/deploy/install_services.sh` are kept only for reference.

## Next steps, in order

### 1. Install on the hub laptop (needs internet once)
- [x] Docker Desktop (WSL 2 backend). Start it once and accept the firewall prompt, or allow inbound TCP 8000 and 1883.
- [x] Optional: `winget install ezwinports.make` so the `make docker-*` targets work. Without make, use the commands in the table below.
- [x] `docker compose up -d --build broker hub`. This build is the step that needs internet; after it the demo runs offline.
- [x] Open `http://localhost:8000/clinician/` and `http://localhost:8000/family/`. `docker compose logs -f broker hub` should show the hub connected to `broker:1883` and history loaded.

### 2. First run-through on Docker with the sim
- [x] `docker compose --profile sim run --rm sim` (interactive: `s` start feed, `o` occlusion, `q` quit).
- [x] Phase 2 check: propose 90, confirm on the phone. The chip goes Pending, Sent, Active on pump. Propose 500 and confirm it: Rejected, rate out of range.
- [x] Reset check: quit the sim (`q`), run `bash scripts/reset_demo_docker.sh` (Git Bash), then start the sim again. The pump comes back at v7, 60 mL/hr, idle, and does **not** pick up the old v8.
- [ ] Look at the portal right after the reset, when the hub has no record of v7. Report anything odd to Person C.
- [x] Restart Docker Desktop (or the laptop) and check that broker and hub come back by themselves (`restart: unless-stopped`).

### 3. Network for the phone and the ESP32
- [ ] Give the hub laptop a fixed IP on the demo router or hotspot. Find it with `ipconfig` (Wi-Fi adapter).
- [ ] Bookmark `http://<ip>:8000/family/` on the demo phone.
- [ ] Person A sets that IP as the broker host for the ESP32. Only one pump may use `pump-001`: never run the sim while the ESP32 is on.

### 4. Support the rest of the team
- [ ] Sync 3: watch `docker compose exec broker mosquitto_sub -t 'pump/#' -v` while A brings the ESP32 online.
- [ ] Sync 4: occlusion check against Docker: phone alert in 3 seconds or less, and the portal flags the patient.
- [ ] Fix any API issues Person C reports.
- [ ] To Person A: add an empty-payload case (`"payload": ""`, outcome `dropped`) to `shared/protocol/cases/prescription_cases.json` and bump the `55` count in `firmware/test/test_controller/test_main.cpp`. This was left out because PlatformIO was not available to run the firmware side.

### 5. Demo day (you run the hub laptop and are the backup operator)
- [ ] Before you walk up: Docker Desktop running, run the reset, check the pump shows online at v7.
- [ ] Keep a terminal open with `docker compose logs -f hub`.
- [ ] If the ESP32 fails: switch it off, then start the sim (same `PUMP_ID`).

## Quick reference (from the repo root)

| Task | make | Without make |
|---|---|---|
| Start broker + hub | `make docker-up` | `docker compose up -d --build broker hub` |
| Simulated pump | `make docker-sim` | `docker compose --profile sim run --rm sim` |
| Logs | `make docker-logs` | `docker compose logs -f broker hub` |
| Demo reset | `make docker-reset` | `bash scripts/reset_demo_docker.sh` |
| Stop | `make docker-down` | `docker compose down` |
| Watch MQTT | | `docker compose exec broker mosquitto_sub -t 'pump/#' -v` |
| Update code | | `git pull`, then `docker compose up -d --build hub` |
