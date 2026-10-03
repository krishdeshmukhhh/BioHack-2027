# Run the demo hub on a Windows laptop instead of the Pi. Prototype demo only.
# Run from the repo root in PowerShell:
#
#   powershell -ExecutionPolicy Bypass -File hub/deploy/laptop.ps1 start   # broker + hub, each in its own window
#   powershell -ExecutionPolicy Bypass -File hub/deploy/laptop.ps1 reset   # same as `make reset-demo`
#   powershell -ExecutionPolicy Bypass -File hub/deploy/laptop.ps1 urls    # addresses for the phone and the ESP32
#
# Needs Mosquitto (winget install EclipseFoundation.Mosquitto) with its Windows service
# disabled, and inbound TCP 1883 and 8000 allowed in Windows Firewall.
param([Parameter(Mandatory = $true)][ValidateSet("start", "reset", "urls")][string]$Action)
$ErrorActionPreference = "Stop"

$Root = (Get-Location).Path
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$MosquittoDir = "C:\Program Files\mosquitto"
$PumpId = if ($env:PUMP_ID) { $env:PUMP_ID } else { "pump-001" }
$Db = if ($env:HUB_DB_PATH) { $env:HUB_DB_PATH } else { "hub\data\hub.sqlite3" }

if (-not (Test-Path (Join-Path $Root "hub\app\main.py"))) { throw "run from the repo root" }
if (-not (Test-Path $Py)) { throw "no .venv: create it and pip install -r requirements.txt" }

function Show-Urls {
    $ips = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.InterfaceAlias -like "Wi-Fi*" }
    foreach ($ip in $ips) {
        $a = $ip.IPAddress
        Write-Host "Laptop on $($ip.InterfaceAlias): $a"
        Write-Host "  Family app (phone):  http://${a}:8000/family/"
        Write-Host "  Clinician portal:    http://${a}:8000/clinician/"
        Write-Host "  Broker for ESP32/sim: MQTT_HOST=$a  port 1883"
    }
    Write-Host "The phone, the ESP32 and this laptop must be on the same hotspot."
}

function Test-Listening([int]$Port) {
    [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

switch ($Action) {
    "start" {
        if (Test-Listening 1883) { Write-Host "= broker already listening on 1883" }
        else {
            New-Item -ItemType Directory -Force ".mosquitto" | Out-Null
            Start-Process powershell -WorkingDirectory $Root -ArgumentList "-NoExit", "-Command",
                "`$host.UI.RawUI.WindowTitle='broker'; & '$MosquittoDir\mosquitto.exe' -c scripts/mosquitto.conf -v"
            Write-Host "+ broker started (window 'broker')"
        }
        if (Test-Listening 8000) { Write-Host "= hub already listening on 8000" }
        else {
            Start-Process powershell -WorkingDirectory $Root -ArgumentList "-NoExit", "-Command",
                "`$host.UI.RawUI.WindowTitle='hub'; `$env:PUMP_ID='$PumpId'; & '$Py' -m uvicorn hub.app.main:app --host 0.0.0.0 --port 8000"
            Write-Host "+ hub started (window 'hub')"
        }
        Show-Urls
        Write-Host "Simulated pump (fallback): .venv\Scripts\python -m sim.pump_sim --pump-id $PumpId --demo-seed"
    }
    "reset" {
        # Same steps as scripts/reset_demo.sh (make reset-demo).
        if (Test-Listening 8000) { throw "the hub is running. Close its window first; it holds the database open." }
        $sims = Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -match "sim\.pump_sim" }
        if ($sims) { throw "a simulator is running. Quit it first (q + Enter), so it publishes offline." }
        if (-not (Test-Listening 1883)) { throw "the broker is not running. Start it with: laptop.ps1 start" }

        # 1. Archive the hub database instead of deleting it: the audit log is append-only (S7).
        if (Test-Path $Db) {
            $archive = Join-Path (Split-Path $Db) "archive"
            $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
            New-Item -ItemType Directory -Force $archive | Out-Null
            foreach ($f in @($Db, "$Db-wal", "$Db-shm")) {
                if (Test-Path $f) { Move-Item $f (Join-Path $archive "$(Split-Path $f -Leaf).$stamp") }
            }
            Write-Host "+ hub database archived to $archive ($stamp)"
        } else { Write-Host "= no hub database at $Db" }

        # 2. Remove the retained prescription. An empty retained message deletes it; it is not a prescription.
        & "$MosquittoDir\mosquitto_pub.exe" -h localhost -p 1883 -t "pump/$PumpId/prescription" -r -n
        if ($LASTEXITCODE -ne 0) { throw "could not clear the retained prescription" }
        Write-Host "+ retained prescription cleared on pump/$PumpId/prescription"

        # 3. History that ends today.
        & $Py -m sim.generate_history
        Write-Host ""
        Write-Host "Reset done. Now: laptop.ps1 start, then the pump (sim: --demo-seed; ESP32: Person A resets NVS for v7)."
    }
    "urls" { Show-Urls }
}
