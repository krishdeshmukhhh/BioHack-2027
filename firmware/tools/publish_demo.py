"""Publish a demo fixture to bench ESP32 firmware, with no hub running.

Bench only. The hub is the publish gate (S2) and the source of every version the
portal shows (S5); a version published here bypasses both. So this tool needs
--bench-only, publishes NOT retained, and uses the identity "bench-test" (never a
hub user id). Run `make reset-demo` before the hub is used again.
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
    parser.add_argument(
        "--bench-only", action="store_true",
        help="required: confirms no hub is using this pump id",
    )
    parser.add_argument("--note", default="Digitally simulated ESP32 bench test")
    args = parser.parse_args()
    if not args.bench_only:
        parser.error("bench tool: pass --bench-only to confirm no hub is using this pump id")
    if args.version < 1 or len(args.note) > 200:
        parser.error("Version must be positive and note must be at most 200 characters")
    at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    payload = {
        "pump_id": args.pump_id,
        "version": args.version,
        "mode": "continuous",
        "rate_ml_hr": args.rate,
        "volume_ml": args.volume,
        "proposed_by": "bench-test",
        "proposed_at": at,
        "confirmed_by": "bench-test",
        "confirmed_at": at,
        "note": args.note,
    }
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(args.broker, args.port, keepalive=15)
    client.loop_start()
    try:
        result = client.publish(f"pump/{args.pump_id}/prescription", encoded, qos=1, retain=False)
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
