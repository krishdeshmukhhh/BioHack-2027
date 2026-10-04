# Runbook: hub laptop (Windows) with the ESP32

Exact commands to run the prototype demo on the Windows hub laptop with the real ESP32 on USB. Prototype only: never connect to a person, all data is fictional, rates are demo values. The demo script itself (who says what) is in `DEMO.md`.

All commands are **PowerShell**, run from the repo root (`C:\Users\Krish\Coding\Hackathons\BioHack\BioHack-2027`). Hub laptop IP on the current network: `192.168.1.93` (change it below if the network changes).

## 0. One-time setup (already done on this laptop)

Needs internet. Skip on later runs.

```powershell
uv pip install --python .venv\Scripts\python.exe platformio
$env:PLATFORMIO_CORE_DIR = "$PWD\firmware\.pio\core"
.venv\Scripts\pio run -d firmware -e esp32dev        # downloads the ESP32 toolchain (~1.6 GB) once
docker compose up -d --build broker hub dashboard    # builds the images once
```

Also needed: `firmware\include\secrets.h` (copy from `secrets.example.h`, or from a teammate's machine). The broker address in it must be the hub laptop IP.

After this, nothing needs the internet. The toolchain is cached in `firmware\.pio\core` (gitignored) and the Docker images are cached. **Every new PowerShell window must set `PLATFORMIO_CORE_DIR` before running `pio`**, or PlatformIO looks in `%USERPROFILE%\.platformio`, finds nothing and downloads it all again.

## 1. Start the stack

```powershell
git branch --show-current                            # must print: main
docker compose up -d broker hub dashboard
docker ps                                            # broker, hub, dashboard: all Up
```

Use `--build` only after pulling new code, and do it while online. A stray `smartpump-sim-run-...` container must not be running (`docker stop <name>`): only one `pump-001` on the broker.

## 2. Reset to the demo start (v7 at 60 mL/hr, idle)

Do this before every rehearsal and before the real demo. Every confirmed change moves the pump's version up (S3), so the ESP32's memory has to be erased as well as the hub's database. Close any serial monitor first (the erase and upload need COM3).

```powershell
$env:PLATFORMIO_CORE_DIR = "$PWD\firmware\.pio\core"
& "C:\Program Files\Git\bin\bash.exe" scripts/reset_demo_docker.sh
.venv\Scripts\python -c "import json; from sim.pump_sim import DEMO_SEED; print(json.dumps(dict(DEMO_SEED, pump_id='pump-001')))" | docker exec -i smartpump-broker-1 mosquitto_pub -t pump/pump-001/prescription -q 1 -r -s
.venv\Scripts\pio run -d firmware -e esp32dev -t erase  --upload-port COM3
.venv\Scripts\pio run -d firmware -e esp32dev -t upload --upload-port COM3
```

- The reset script ends with `Reset done.` It archives the database (never deletes it, S7) and regenerates the 30-day history so it ends today.
- The seed publish is rehearsal setup only. It skips the caregiver confirm (S2), so it is never part of the demo.
- Erase and upload both end with `SUCCESS`. Always `esp32dev`, never `esp32dev_offline`.

## 3. Serial monitor: the pump's control panel

```powershell
$env:PLATFORMIO_CORE_DIR = "$PWD\firmware\.pio\core"
.venv\Scripts\pio device monitor -d firmware -e esp32dev --port COM3 --dtr 0 --rts 0 --echo
```

Check: the status lines (every 2 s) show `"state":"idle"`, `"rate_ml_hr":60`, `"prescription_version":7`.

Type the pump commands in this window, each followed by Enter:

| Command | What it does |
|---|---|
| `status` | Print the status now |
| `start` | Start a feed (priming, then running) |
| `pause` / `resume` | Pause and resume the feed |
| `stop` | End the feed, back to idle |
| `occlusion` | Inject a blocked-tube alarm |
| `bag_empty` | Inject a bag-empty alarm |
| `clear` | Clear the alarm (then `resume`) |

Keep this window open for the whole session and don't press Ctrl+C mid-feed: reopening the port can reset the ESP32.

## 4. Open the screens

| Device | URL | Then |
|---|---|---|
| Laptop browser | `http://192.168.1.93:3000/clinician` | Check: 3 patients, "Simulated data", Aster without "night alarms" |
| Android phone, Chrome, same Wi-Fi | `http://192.168.1.93:3000/` | Open the patient, **Care** tab, tap **Enable alerts**. Stay on this tab |
| Fallback (static UI) | `http://192.168.1.93:8000/` and `/clinician/` | Use if a dashboard screen fails |

Android, not iPhone: iPhones don't vibrate from the web. Re-tap Enable alerts after any reload or tab change.

## 5. Demo checks

| # | Do | Expected |
|---|---|---|
| 1 | Laptop: propose 90 mL/hr. Phone: Confirm | Chip goes Pending, Sent, **Active on pump**; the monitor shows version 8 |
| 2 | Propose 500, Confirm | **Rejected: rate out of range**; the monitor still shows version 8 |
| 3 | Monitor: `start`, wait for `running`. Start a stopwatch, then `occlusion` | Phone: alert with steps, vibrates. Laptop: **Alarm now**. Target ≤ 3 s for both |
| 4 | Monitor: `clear`, then `resume` | Alert gone on both screens, feed running again |
| 5 | While running, in a **second** PowerShell window: `docker stop smartpump-broker-1; Start-Sleep 30; docker start smartpump-broker-1` | Monitor keeps showing `running` with `delivered_ml` rising (S6); screens show offline, then recover |
| 6 | Monitor: `stop` | `"state":"idle"` |

Then reset again (section 2) before the next run.

## 6. Watching and stopping

```powershell
docker exec smartpump-broker-1 mosquitto_sub -t 'pump/#' -v               # all pump messages
docker exec smartpump-broker-1 mosquitto_sub -t 'pump/+/availability' -v  # exactly one pump-001, online
docker compose logs -f hub                                                # hub log
docker compose stop                                                       # end of day
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `no configuration file provided: not found` | The repo is on another branch (for example `lane/fw`). `git checkout main` |
| `execvpe(/bin/bash) failed` | Plain `bash` in PowerShell is WSL. Use `& "C:\Program Files\Git\bin\bash.exe" ...` |
| `No module named pip` | The venv was made by uv. Use `uv pip install --python .venv\Scripts\python.exe ...` |
| `pio` starts downloading packages | `PLATFORMIO_CORE_DIR` isn't set in this window. Set it (section 3) |
| Upload or monitor: `could not open port 'COM3'` | Another monitor has the port. Close it. Check the port with `[System.IO.Ports.SerialPort]::GetPortNames()` |
| No COM port, "Unknown USB Device" in Device Manager | Cable or port. Use a rear USB port and a data cable; it should show `USB-SERIAL CH340 (COM3)` |
| Pump flaps online and offline | Two `pump-001`s: a sim container is running. `docker ps`, stop it |
| A new prescription is ignored | The pump has a higher version than the hub (the hub was reset without the ESP32 erase). Do all of section 2 |
| Aster shows "night alarms" | Earlier test alarms in the 22:00 to 06:00 UTC window. Reset (section 2) |
| Phone can't load the page | Same Wi-Fi as the laptop? Laptop IP still `192.168.1.93` (`ipconfig`)? |
