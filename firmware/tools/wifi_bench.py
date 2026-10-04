#!/usr/bin/env python3
"""Bounded device-only WiFi outage check for the ESP32 network bench profile.

Requires the compile-gated network bench startup marker, a hub-confirmed idle
prescription, and simulated delivery. Never changes Mac WiFi or stops a broker.
Opening serial does not intentionally reset the board; press reset while this
helper listens to expose the startup markers.
Use only the scratch/test hub database prepared for network_bench.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from . import network_bench as network
except ImportError:
    import network_bench as network

bench = network.bench
PROFILE_MARKER = "Network bench controls enabled; simulated=true"
OFF_MARKER = "Bench WiFi disconnected"
ON_MARKER = "Bench WiFi reconnect enabled"
CHECKS = (
    "mode_gate",
    "initial_idle",
    "confirmed_prescription",
    "hub_live_status",
    "start_progression",
    "device_wifi_disconnected",
    "delivery_during_wifi_loss",
    "hub_offline",
    "mqtt_last_will_offline",
    "network_restored",
    "stop_returns_idle",
)


class WifiBench(network.NetworkBench):
    def __init__(self, *args, outage_seconds=30, **kwargs):
        super().__init__(*args, **kwargs)
        self.profile_seen = False
        self.disabled_by_helper = False
        self.outage_seconds = outage_seconds

    def read(self, deadline):
        while self.clock() < deadline:
            if b"\n" in self.buffer:
                raw, _, rest = self.buffer.partition(b"\n")
                self.buffer = bytearray(rest)
                line = raw.decode("utf-8", errors="replace").strip()
                if line == PROFILE_MARKER:
                    self.profile_seen = True
                    self.report["network_bench_profile"] = True
                    return "profile", line
                if line in {OFF_MARKER, ON_MARKER}:
                    return "diagnostic", line
                parsed = bench.parse_line(line)
                if not parsed:
                    continue
                kind, value = parsed
                if kind == "mode":
                    self.mode = value
                    self.report["device_mode"] = value
                elif kind == "status":
                    bench.validate_status(value)
                    self.last_status = value
                    self.report["last_status"] = value
                    self.report["simulated"] = True
                return parsed
            block = self.port.read(256)
            if block:
                self.buffer.extend(block)
                if len(self.buffer) > 8192:
                    self.buffer.clear()
        raise bench.BenchError("Timed out waiting for fresh network bench serial evidence")

    def identify(self, probe=False):
        self.check("mode_gate")
        self.wait("mode")
        if self.mode != "hub":
            raise bench.BenchError("WiFi-loss check refuses offline firmware")
        if not self.profile_seen:
            self.wait("profile")
        initial = self.wait("status")
        network.require_hub(self.mode, initial)
        if initial["pump_id"] != self.pump_id:
            raise bench.BenchError("USB pump identity does not match the requested hub pump")
        self.authorized = True
        self.passed("Hub and compile-gated network bench markers plus simulated USB status")
        return initial

    def send(self, command):
        self.remaining()
        if not self.authorized or not self.profile_seen:
            raise bench.BenchError("Network bench controls were not positively identified")
        network.require_hub(self.mode, self.last_status)
        if command not in {"start", "stop", "wifi_off", "wifi_on"}:
            raise bench.BenchError("Unsupported WiFi bench command")
        self.discard_serial_backlog()
        if command == "start":
            self.started_feed = True
        elif command == "wifi_off":
            # A write/flush may fail after the device received the command. Retain
            # cleanup ownership before writing, including lost acknowledgements.
            self.disabled_by_helper = True
        self.port.write((command + "\n").encode("ascii"))
        self.port.flush()

    @staticmethod
    def stable_feed(current, baseline, *, advance_from=None):
        keys = (
            "pump_id",
            "prescription_version",
            "rate_ml_hr",
            "target_ml",
            "pending_version",
            "last_rejected_version",
            "last_reject_reason",
        )
        if (
            current["state"] != "running"
            or current["alarm"] is not None
            or any(current.get(key) != baseline.get(key) for key in keys)
        ):
            raise bench.BenchError("Feed state, prescription, rate or rejection fields changed")
        if advance_from is not None and current["delivered_ml"] <= advance_from["delivered_ml"]:
            raise bench.BenchError("Digital volume did not advance during device WiFi loss")

    def live_hub(self, initial):
        self.check("hub_live_status")
        baseline = self.api_request("GET", "/status").get("received_at")
        started = self.clock()
        self.observer.start(min(self.timeout, self.remaining()))

        def observed():
            for _, raw in reversed(self.observer.matching("status", started)):
                value = json.loads(raw)
                if (
                    value.get("pump_id") == self.pump_id
                    and value.get("simulated") is True
                    and value.get("uptime_ms", -1) >= initial["uptime_ms"]
                    and value.get("prescription_version") == initial["prescription_version"]
                ):
                    return value
            return None

        sample = self.until(observed, lambda s: s is not None)
        self.until(
            lambda: self.api_request("GET", "/status"),
            lambda s: network.hub_matches_fresh_sample(s, baseline, sample),
        )
        self.passed("Fresh MQTT status and advancing hub received_at agree with USB pump")

    def run(self):
        initial = self.identify()
        self.check("initial_idle")
        if (
            initial["state"] != "idle"
            or initial["alarm"] is not None
            or initial["pending_version"] is not None
        ):
            raise bench.BenchError("Existing feed/alarm/pending update refused without changes")
        if initial["prescription_version"] <= 0 or initial["rate_ml_hr"] <= 0:
            raise bench.BenchError("An accepted existing prescription is required")
        if initial["target_ml"] / initial["rate_ml_hr"] * 3600 < self.outage_seconds + 60:
            raise bench.BenchError("Existing target is too short for the bounded outage check")
        self.passed("Idle accepted prescription; no alarm/pending update; adequate digital target")

        self.live_hub(initial)
        self.check("confirmed_prescription")
        prescription = self.prescription(initial["prescription_version"])
        if (
            not prescription
            or prescription["state"] != "active"
            or not prescription.get("confirmed_by")
            or not prescription.get("confirmed_at")
            or prescription["rate_ml_hr"] != initial["rate_ml_hr"]
            or prescription["volume_ml"] != initial["target_ml"]
        ):
            raise bench.BenchError("Existing device settings lack matching active hub confirmation")
        self.report["tested_version"] = initial["prescription_version"]
        self.passed(
            "Existing active hub prescription matches device and has caregiver confirmation"
        )

        self.check("start_progression")
        running = self.transition("start", "priming", status_target="running")
        baseline = self.progression(running)
        self.passed("Helper-started digital feed is running and advancing")

        self.check("device_wifi_disconnected")
        hub_before = self.api_request("GET", "/status").get("received_at")
        disconnected_at = self.clock()
        self.send("wifi_off")
        self.wait("diagnostic", lambda line: line == OFF_MARKER)
        first = self.fresh_status()
        self.stable_feed(first, baseline)
        self.passed("Network worker positively acknowledged actual device WiFi disconnection")

        self.check("delivery_during_wifi_loss")
        previous = first
        hub_offline = False
        while previous["uptime_ms"] - first["uptime_ms"] < self.outage_seconds * 1000:
            previous_uptime = previous["uptime_ms"]
            current = self.wait("status", lambda s, floor=previous_uptime: s["uptime_ms"] > floor)
            self.stable_feed(current, baseline, advance_from=previous)
            hub_offline |= self.api_request("GET", "/status").get("online") is False
            previous = current
        self.report["outage_window"] = {
            "device_elapsed_ms": previous["uptime_ms"] - first["uptime_ms"],
            "start_delivered_ml": first["delivered_ml"],
            "end_delivered_ml": previous["delivered_ml"],
            "rate_ml_hr": baseline["rate_ml_hr"],
            "prescription_version": baseline["prescription_version"],
        }
        self.passed(
            "Digital volume advanced throughout >=30 device seconds without changing settings"
        )

        self.check("hub_offline")
        if not hub_offline:
            raise bench.BenchError("Hub did not show offline during the actual device WiFi outage")
        self.passed("Hub marked pump offline during device-only WiFi loss")

        self.check("mqtt_last_will_offline")
        self.until(
            lambda: self.observer.matching("availability", disconnected_at),
            lambda messages: any(raw == b"offline" for _, raw in messages),
        )
        self.report["offline_availability"] = "Observed via broker during device WiFi loss"
        self.passed("Broker delivered retained offline after ungraceful device connection loss")

        self.check("network_restored")
        enabled_at = self.clock()
        self.send("wifi_on")
        self.wait("diagnostic", lambda line: line == ON_MARKER)
        resumed = self.fresh_status()
        self.stable_feed(resumed, baseline, advance_from=previous)

        def observed_restored():
            for _, raw in reversed(self.observer.matching("status", enabled_at)):
                value = json.loads(raw)
                if value.get("uptime_ms", -1) >= resumed["uptime_ms"]:
                    self.stable_feed(value, baseline)
                    return value
            return None

        restored_mqtt = self.until(observed_restored, lambda s: s is not None)
        self.until(
            lambda: self.api_request("GET", "/status"),
            lambda s: network.hub_matches_fresh_sample(s, hub_before, restored_mqtt),
        )
        self.until(
            lambda: self.observer.matching("availability", enabled_at),
            lambda messages: any(raw == b"online" for _, raw in messages),
        )
        self.disabled_by_helper = False
        latest = self.fresh_status()
        self.stable_feed(latest, baseline, advance_from=resumed)
        self.report["restored_status"] = latest
        self.passed(
            "Device rejoined; fresh MQTT/hub online; same running feed and rejection fields"
        )

        self.check("stop_returns_idle")
        stopped = self.transition("stop", "idle")
        if stopped["alarm"] is not None:
            raise bench.BenchError("Stop did not leave alarm-free idle")
        self.passed("Helper-started digital feed stopped safely to idle")

    def cleanup(self):
        self.deadline = max(self.deadline, self.clock() + 20)
        if self.disabled_by_helper:
            try:
                self.send("wifi_on")
                self.wait("diagnostic", lambda line: line == ON_MARKER, timeout=5)
                self.report["network_cleanup"] = "Reconnect enabled; online recovery not verified"
                self.disabled_by_helper = False
            except Exception:
                self.report["network_cleanup"] = "Could not confirm reconnect; inspect device"
        if self.started_feed and self.authorized and self.mode == "hub":
            try:
                # A start may have succeeded before its transition acknowledgement
                # failed; obtain current state before deciding whether stop is allowed.
                self.discard_serial_backlog()
                self.wait("status", timeout=5)
            except Exception:
                self.report["feed_cleanup_observation"] = (
                    "Fresh state unavailable; using last observed state"
                )
        super().cleanup()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--hub", default="http://127.0.0.1:8000")
    parser.add_argument("--scratch-hub", action="store_true", required=True,
                        help="Confirm --hub uses a scratch/test database, not the real demo DB")
    parser.add_argument("--broker", default="127.0.0.1")
    parser.add_argument("--broker-port", type=int, default=1883)
    parser.add_argument("--pump-id", default="pump-001")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--total-timeout", type=float, default=180)
    parser.add_argument("--outage-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    if not 10 <= args.timeout <= 30 or not 90 <= args.total_timeout <= 300:
        parser.error("--timeout must be 10–30 and --total-timeout 90–300 seconds")
    if not 30 <= args.outage_seconds <= 60:
        parser.error("--outage-seconds must be 30–60")
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "prototype": True,
        "simulated": None,
        "device_mode": "unknown",
        "network_bench_profile": False,
        "port": args.port,
        "mechanism": "Compile-gated device-only WiFi.disconnect",
        "checks": {name: {"result": "not_run"} for name in CHECKS},
    }
    port = observer = helper = None
    result = 1
    print("Listening for hub + network bench markers; press ESP32 reset now.", flush=True)
    try:
        api = network.HttpApi(args.hub)
        port = bench.open_serial(args.port)
        observer = network.MqttObserver(args.broker, args.broker_port, args.pump_id)
        helper = WifiBench(
            port,
            report,
            api,
            observer,
            pump_id=args.pump_id,
            timeout=args.timeout,
            total_timeout=args.total_timeout,
            outage_seconds=args.outage_seconds,
        )
        helper.run()
        result = 0
    except KeyboardInterrupt:
        report["error"] = "Interrupted by operator"
    except bench.BenchError as exc:
        report["error"] = str(exc)
    except Exception as exc:
        report["error"] = f"WiFi helper failed: {type(exc).__name__}; inspect setup"
    finally:
        if result and helper and helper.current_check:
            report["checks"][helper.current_check] = {"result": "fail", "detail": report["error"]}
        if result and helper:
            helper.cleanup()
        if observer:
            observer.close()
        if port:
            port.close()
        report["result"] = "pass" if result == 0 else "fail"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['result'].upper()}: evidence written to {args.output}")
    if result:
        print(report["error"], file=sys.stderr)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
