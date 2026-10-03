#!/usr/bin/env python3
"""Bounded serial checks for the offline ESP32 digital-delivery prototype.

Opening the port does not deliberately reset the ESP32. Press its reset button
after this helper starts so it can observe the build's positive mode marker.
Probe mode only reads; control mode refuses hub builds and active feeds.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OFFLINE_MARKER = "Mode: offline bench; local demo enabled; simulated=true"
HUB_MARKER = "Mode: hub; local demo disabled; simulated=true"
CHECKS = (
    "mode_gate",
    "initial_idle",
    "demo_applied_idle",
    "start_progression",
    "pause_freezes_volume",
    "occlusion_stops_delivery",
    "clear_remains_paused",
    "resume_progression",
    "stop_returns_idle",
    "reboot_restores_prescription",
)
STATUS_KEYS = {
    "pump_id",
    "uptime_ms",
    "state",
    "rate_ml_hr",
    "delivered_ml",
    "target_ml",
    "alarm",
    "prescription_version",
    "pending_version",
    "simulated",
}


class BenchError(RuntimeError):
    pass


def parse_line(line: bytes | bytearray | str):
    """Ignore boot noise and recognize direct JSON or desktop-style envelopes."""
    if isinstance(line, (bytes, bytearray)):
        line = line.decode("utf-8", errors="replace")
    line = line.strip()
    if line == OFFLINE_MARKER:
        return "mode", "offline"
    if line == HUB_MARKER:
        return "mode", "hub"
    try:
        value = json.loads(line)
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    if isinstance(value.get("payload"), dict):
        value = value["payload"]
    if STATUS_KEYS <= value.keys():
        return "status", value
    if {"type", "uptime_ms", "simulated", "pump_id"} <= value.keys():
        return "event", value
    return None


def validate_status(value):
    if value["simulated"] is not True:
        raise BenchError("Device is not positively labelled simulated=true")
    if value["state"] not in {"idle", "priming", "running", "paused", "alarm", "complete"}:
        raise BenchError("Unrecognized controller state")
    for field in ("uptime_ms", "rate_ml_hr", "delivered_ml", "target_ml", "prescription_version"):
        number = value[field]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise BenchError(f"Invalid numeric telemetry: {field}")
        if not math.isfinite(number) or number < 0:
            raise BenchError(f"Invalid numeric telemetry: {field}")


def require_offline(mode, status):
    if mode != "offline":
        raise BenchError("Control requires the offline bench startup marker; hub mode refused")
    validate_status(status)


class Bench:
    def __init__(self, port, report, *, timeout=12.0, clock=time.monotonic):
        self.port = port
        self.report = report
        self.timeout = timeout
        self.clock = clock
        self.mode = None
        self.last_status = None
        self.authorized = False
        self.current_check = None
        self.buffer = bytearray()

    def read(self, deadline):
        while self.clock() < deadline:
            if b"\n" in self.buffer:
                line, _, rest = self.buffer.partition(b"\n")
                self.buffer = bytearray(rest)
                result = parse_line(line)
                if not result:
                    continue
                kind, value = result
                if kind == "mode":
                    self.mode = value
                    self.report["device_mode"] = value
                elif kind == "status":
                    validate_status(value)
                    self.last_status = value
                    self.report["last_status"] = value
                    self.report["simulated"] = True
                return result
            block = self.port.read(256)
            if block:
                self.buffer.extend(block)
                if len(self.buffer) > 8192:
                    self.buffer.clear()  # Ignore a corrupt or unterminated boot line.
        raise BenchError("Timed out waiting for fresh serial telemetry")

    def wait(self, kind, predicate=lambda _: True, *, timeout=None):
        deadline = self.clock() + (self.timeout if timeout is None else timeout)
        while self.clock() < deadline:
            actual_kind, value = self.read(deadline)
            if actual_kind == kind and predicate(value):
                return value
        raise BenchError(f"Timed out waiting for {kind}")

    def check(self, name):
        self.current_check = name

    def passed(self, detail):
        self.report["checks"][self.current_check] = {"result": "pass", "detail": detail}

    def identify(self, probe=False):
        self.check("mode_gate")
        self.wait("mode")
        status = self.wait("status")
        if probe:
            self.passed(f"Read-only probe observed {self.mode} build with simulated=true")
            return status
        require_offline(self.mode, status)
        self.authorized = True
        self.passed("Offline marker and simulated=true telemetry observed; control permitted")
        return status

    def send(self, command):
        if not self.authorized:
            raise BenchError("Serial control has not been authorized by the offline mode gate")
        require_offline(self.mode, self.last_status)
        # Discard already-received lines before each command. Subsequent checks
        # require an event and telemetry newer than the pre-command uptime.
        self.port.reset_input_buffer()
        self.buffer.clear()
        self.port.write((command + "\n").encode("ascii"))
        self.port.flush()

    def transition(self, command, target, *, alarm_event=None, status_target=None):
        before = self.last_status["uptime_ms"]
        self.send(command)
        if alarm_event:
            self.wait(
                "event",
                lambda e: (
                    e["type"] == alarm_event
                    and e["uptime_ms"] >= before
                    and e.get("alarm") == "occlusion"
                ),
            )
        event = self.wait(
            "event",
            lambda e: (
                e["type"] == "state_changed"
                and e.get("to_state") == target
                and e["uptime_ms"] >= before
            ),
        )
        if status_target and status_target != target:
            event = self.wait(
                "event",
                lambda e: (
                    e["type"] == "state_changed"
                    and e.get("to_state") == status_target
                    and e["uptime_ms"] >= event["uptime_ms"]
                ),
            )
        return self.wait(
            "status",
            lambda s: (
                s["uptime_ms"] > event["uptime_ms"] and s["state"] == (status_target or target)
            ),
        )

    def freeze(self, first, state, *, alarm=None):
        later = self.wait("status", lambda s: s["uptime_ms"] >= first["uptime_ms"] + 4000)
        if later["state"] != state or later["alarm"] != alarm:
            raise BenchError(f"Expected stable {state} state with alarm={alarm}")
        if abs(later["delivered_ml"] - first["delivered_ml"]) > 0.000001:
            raise BenchError(f"Delivered volume advanced while {state}")
        if state == "alarm" and (first["rate_ml_hr"] != 0 or later["rate_ml_hr"] != 0):
            raise BenchError("Alarm telemetry did not report rate zero")
        return later

    def progression(self, first):
        later = self.wait("status", lambda s: s["uptime_ms"] >= first["uptime_ms"] + 4000)
        if later["state"] != "running" or later["alarm"] is not None:
            raise BenchError("Controller did not remain running without an alarm")
        if later["delivered_ml"] <= first["delivered_ml"]:
            raise BenchError("Digital delivered volume did not advance")
        return later

    def run(self):
        initial = self.identify()
        self.check("initial_idle")
        if initial["state"] != "idle" or initial["alarm"] is not None:
            raise BenchError(
                "Initial controller must be idle without an alarm; feed left unchanged"
            )
        if initial["pending_version"] is not None:
            raise BenchError("Initial pending prescription exists; left unchanged")
        self.passed("Idle, no alarm, no pending prescription")

        self.check("demo_applied_idle")
        previous_version = initial["prescription_version"]
        self.send("demo")
        event = self.wait(
            "event",
            lambda e: (
                e["type"] == "prescription_applied"
                and e.get("version", 0) > previous_version
                and e["uptime_ms"] >= initial["uptime_ms"]
            ),
        )
        fixture = self.wait(
            "status",
            lambda s: (
                s["uptime_ms"] > event["uptime_ms"]
                and s["prescription_version"] == event["version"]
            ),
        )
        if fixture["state"] != "idle" or fixture["rate_ml_hr"] != 60 or fixture["target_ml"] != 5:
            raise BenchError("Local demo was not applied idle at the documented fixture values")
        version = fixture["prescription_version"]
        self.passed(f"Fictional demo v{version} applied idle at 60 mL/hr, 5 mL")

        self.check("start_progression")
        running = self.transition("start", "priming", status_target="running")
        self.progression(running)
        self.passed("Start reached running and digital delivered volume advanced")

        self.check("pause_freezes_volume")
        paused = self.transition("pause", "paused")
        self.freeze(paused, "paused")
        self.passed("Pause held delivered volume constant for at least 4 device seconds")

        self.check("occlusion_stops_delivery")
        alarm = self.transition("occlusion", "alarm", alarm_event="alarm_raised")
        self.freeze(alarm, "alarm", alarm="occlusion")
        self.passed("Occlusion alarm held rate zero and delivered volume constant")

        self.check("clear_remains_paused")
        cleared = self.transition("clear", "paused", alarm_event="alarm_cleared")
        self.freeze(cleared, "paused")
        self.passed("Clear removed alarm and remained paused without advancing volume")

        self.check("resume_progression")
        resumed = self.transition("resume", "running")
        self.progression(resumed)
        self.passed("Separate resume restored running and digital volume advanced")

        self.check("stop_returns_idle")
        stopped = self.transition("stop", "idle")
        if stopped["alarm"] is not None:
            raise BenchError("Stop left an alarm active")
        self.passed("Stop returned controller to idle")

        self.check("reboot_restores_prescription")
        expected = {k: stopped[k] for k in ("prescription_version", "rate_ml_hr", "target_ml")}
        uptime_before = stopped["uptime_ms"]
        if stopped["state"] != "idle":
            raise BenchError("Reboot refused because controller is not idle")
        self.send("reboot")
        self.mode = None
        self.wait("mode")  # Must see a new boot, never use pre-reboot serial backlog.
        restored = self.wait("status")
        require_offline(self.mode, restored)
        if restored["uptime_ms"] >= uptime_before:
            raise BenchError("Fresh post-boot uptime did not decrease")
        if restored["state"] != "idle" or restored["alarm"] is not None:
            raise BenchError("Reboot did not restore safely to idle")
        if any(restored[k] != v for k, v in expected.items()):
            raise BenchError("Reboot changed the prescription version, rate or target")
        self.passed("New boot; uptime decreased; NVS restored same version/rate/target idle")

    def cleanup(self):
        # Never clear alarms or modify a hub build; do not stop someone else's
        # pre-existing feed when the initial idle gate failed.
        began = self.report["checks"]["demo_applied_idle"]["result"] == "pass"
        if (
            began
            and self.authorized
            and self.mode == "offline"
            and self.last_status
            and self.last_status["state"] in {"priming", "running", "paused"}
        ):
            try:
                self.transition("stop", "idle")
                self.report["cleanup"] = "Stopped bench feed to idle"
            except Exception:
                self.report["cleanup"] = "Could not confirm stop; inspect device manually"
        elif self.last_status and self.last_status["state"] == "alarm":
            self.report["cleanup"] = "Active alarm left intact; no automatic clear or stop"


def open_serial(port_name):
    import serial

    port = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=1, exclusive=True)
    # Set these before open so pyserial does not deliberately pulse the reset lines.
    port.dtr = False
    port.rts = False
    port.port = port_name
    port.open()
    return port


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--output", required=True, type=Path, help="JSON evidence report path")
    parser.add_argument("--probe", action="store_true", help="Only listen; send no commands")
    parser.add_argument("--timeout", type=float, default=12, help="Per-step deadline: 4–60 seconds")
    args = parser.parse_args(argv)
    if not 4 <= args.timeout <= 60:
        parser.error("--timeout must be between 4 and 60 seconds")
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "port": args.port,
        "prototype": True,
        "simulated": None,
        "device_mode": "unknown",
        "probe_only": args.probe,
        "checks": {name: {"result": "not_run"} for name in CHECKS},
        "network_checks": {"result": "not_run", "detail": "No MQTT, hub or WiFi-loss checks"},
    }
    port = None
    bench = None
    result = 1
    print(
        "Listening without intentional reset. Press ESP32 reset now to show its startup marker.",
        flush=True,
    )
    try:
        port = open_serial(args.port)
        bench = Bench(port, report, timeout=args.timeout)
        if args.probe:
            bench.identify(probe=True)
        else:
            bench.run()
        result = 0
    except KeyboardInterrupt:
        report["error"] = "Interrupted by operator"
    except BenchError as exc:
        report["error"] = str(exc)
    except Exception as exc:
        # Serial failures may include arbitrary device output: record class only.
        report["error"] = f"Serial failure: {type(exc).__name__}; close monitors and check port"
    finally:
        if result and bench and bench.current_check:
            report["checks"][bench.current_check] = {"result": "fail", "detail": report["error"]}
        if result and bench:
            bench.cleanup()
        if port:
            port.close()
        report["result"] = "pass" if result == 0 else "fail"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{report['result'].upper()}: JSON report written to {args.output}")
    if result:
        print(report["error"], file=sys.stderr)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
