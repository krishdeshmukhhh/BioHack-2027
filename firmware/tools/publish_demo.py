"""Publish an explicitly confirmed demo fixture to bench ESP32 firmware.

The hub remains the production-path publish gate; this is a local test tool.
"""

import argparse
import json
from datetime import UTC, datetime

import paho.mqtt.client as mqtt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker", required=True)
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--pump-id", default="pump-001")
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--rate", type=float, required=True, help="Demo mL/hr")
    parser.add_argument("--volume", type=float, default=500, help="Demo mL")
    parser.add_argument("--confirmed-by", required=True, choices=["care-01", "care-02"])
    parser.add_argument("--note", default="Digitally simulated ESP32 bench test")
    args = parser.parse_args()
    if args.version < 1 or len(args.note) > 200:
        parser.error("Version must be positive and note must be at most 200 characters")
    at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    payload = {
        "pump_id": args.pump_id,
        "version": args.version,
        "mode": "continuous",
        "rate_ml_hr": args.rate,
        "volume_ml": args.volume,
        "proposed_by": "clin-01",
        "proposed_at": at,
        "confirmed_by": args.confirmed_by,
        "confirmed_at": at,
        "note": args.note,
    }
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(args.broker, args.port, keepalive=15)
    client.loop_start()
    try:
        result = client.publish(f"pump/{args.pump_id}/prescription", encoded, qos=1, retain=True)
        result.wait_for_publish(timeout=10)
        if not result.is_published():
            raise SystemExit("Broker did not acknowledge the prescription within 10 seconds")
        print(
            f"Sent confirmed demo v{args.version}; "
            "wait for pump telemetry to verify applied/rejected."
        )
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
