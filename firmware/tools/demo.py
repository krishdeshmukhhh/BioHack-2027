"""Offline digital run of the actual ESP32 controller core. No broker required."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BINARY = ROOT / "firmware/.pio/build/native/program"


def demo_commands() -> list[dict]:
    rx = json.loads((ROOT / "shared/protocol/examples/prescription.json").read_text())
    rx.update(version=7, rate_ml_hr=60, volume_ml=500)
    queued = dict(rx, version=8, rate_ml_hr=90, note="D" * 200)
    rejected = dict(rx, version=9, rate_ml_hr=500)
    return [
        {"command": "prescription", "payload": rx},
        {"command": "start"},
        {"command": "tick", "elapsed_ms": 1000},
        {"command": "tick", "elapsed_ms": 60000},
        {"command": "prescription", "payload": queued},
        {"command": "prescription", "payload": rejected},
        {"command": "occlusion"},
        {"command": "tick", "elapsed_ms": 10000},
        {"command": "clear"},
        {"command": "resume"},
        {"command": "tick", "elapsed_ms": 60000},
        {"command": "stop"},
    ]


def run_demo() -> list[dict]:
    if not BINARY.is_file():
        raise SystemExit("Build first: .venv/bin/pio run -d firmware -e native")
    result = subprocess.run(
        [str(BINARY)],
        input="".join(json.dumps(command) + "\n" for command in demo_commands()),
        text=True,
        capture_output=True,
        check=True,
    )
    if result.stderr:
        raise RuntimeError(result.stderr)
    return [json.loads(line) for line in result.stdout.splitlines()]


def main() -> None:
    messages = run_demo()
    print("Prototype: ESP32 controller core with simulated delivery (offline desktop demo).")
    for message in messages:
        payload = message["payload"]
        if isinstance(payload, str):
            print(f"Availability: {payload}")
        elif "type" in payload:
            detail = payload.get("reason", payload.get("alarm", ""))
            version = f" v{payload['version']}" if "version" in payload else ""
            print(f"Event: {payload['type']}{version} {detail}".rstrip())
        else:
            print(
                f"State: {payload['state']:8} | delivered {payload['delivered_ml']:.3f} mL"
                f" | active v{payload['prescription_version']}"
                f" | pending {payload['pending_version']} | simulated=true"
            )


if __name__ == "__main__":
    main()
