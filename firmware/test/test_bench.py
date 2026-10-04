"""Tests for the serial bench helper's safety gates and freshness checks."""

import importlib.util
import json
from collections import deque
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "tools" / "bench.py"
SPEC = importlib.util.spec_from_file_location("firmware_bench", MODULE_PATH)
bench = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)


def status(**updates):
    value = {
        "pump_id": "pump-001",
        "uptime_ms": 2000,
        "state": "idle",
        "rate_ml_hr": 60,
        "delivered_ml": 0,
        "target_ml": 5,
        "alarm": None,
        "prescription_version": 7,
        "pending_version": None,
        "simulated": True,
    }
    value.update(updates)
    return value


def event(to_state, uptime_ms):
    return {
        "pump_id": "pump-001",
        "uptime_ms": uptime_ms,
        "type": "state_changed",
        "from_state": "idle",
        "to_state": to_state,
        "simulated": True,
    }


def encoded(value):
    return (json.dumps(value) + "\n").encode()


class FakeClock:
    now = 0

    def __call__(self):
        return self.now


class FakeSerial:
    def __init__(self, clock, lines=(), on_write=None):
        self.clock = clock
        self.lines = deque(lines)
        self.writes = []
        self.on_write = on_write

    def read(self, _):
        self.clock.now += 0.1
        return self.lines.popleft() if self.lines else b""

    def write(self, data):
        self.writes.append(data)
        if self.on_write:
            self.lines.extend(self.on_write(data))

    def flush(self):
        pass

    def reset_input_buffer(self):
        self.lines.clear()


def controller(lines=(), on_write=None):
    clock = FakeClock()
    serial = FakeSerial(clock, lines, on_write)
    report = {"checks": {name: {"result": "not_run"} for name in bench.CHECKS}}
    helper = bench.Bench(serial, report, clock=clock, timeout=1)
    return helper, serial, report


def test_parser_ignores_boot_noise_and_requires_exact_mode_marker():
    assert bench.parse_line(b"ets Jun 8 2016 00:22:57\r\n") is None
    assert bench.parse_line("Mode: offline bench; local demo enabled") is None
    assert bench.parse_line(bench.OFFLINE_MARKER) == ("mode", "offline")
    assert bench.parse_line("[]") is None
    assert bench.parse_line('{"state":"running"}') is None
    assert bench.parse_line(encoded(status())) == ("status", status())
    assert bench.parse_line(encoded({"topic": "pump/status", "payload": status()})) == (
        "status",
        status(),
    )


@pytest.mark.parametrize("marker", [bench.HUB_MARKER, "unsupported build marker"])
def test_hub_or_missing_mode_marker_sends_no_commands(marker):
    helper, serial, _ = controller([(marker + "\n").encode(), encoded(status())])
    with pytest.raises(bench.BenchError):
        helper.run()
    assert serial.writes == []


def test_probe_of_hub_is_read_only():
    helper, serial, report = controller(
        [
            (bench.HUB_MARKER + "\n").encode(),
            encoded(status(state="running")),
        ]
    )
    helper.identify(probe=True)
    assert serial.writes == []
    assert report["device_mode"] == "hub"
    assert report["checks"]["mode_gate"]["result"] == "pass"
    assert not helper.authorized


@pytest.mark.parametrize(
    "update",
    [{"simulated": False}, {"state": "running"}, {"pending_version": 8}, {"uptime_ms": True}],
)
def test_control_refuses_unsafe_initial_status_without_commands(update):
    helper, serial, _ = controller(
        [
            (bench.OFFLINE_MARKER + "\n").encode(),
            encoded(status(**update)),
        ]
    )
    with pytest.raises(bench.BenchError):
        helper.run()
    helper.cleanup()
    assert serial.writes == []


def test_start_uses_transition_events_without_requiring_priming_status():
    # Priming lasts one second, shorter than the periodic status interval.
    # Stale pre-command telemetry must not satisfy the running check.
    def response(command):
        assert command == b"start\n"
        return [
            encoded(event("priming", 2100)),
            encoded(event("running", 3100)),
            encoded(status(state="running", uptime_ms=4000, delivered_ml=0.015)),
        ]

    helper, serial, _ = controller([encoded(status(state="running", uptime_ms=9000))], response)
    helper.mode = "offline"
    helper.authorized = True
    helper.last_status = status()
    fresh = helper.transition("start", "priming", status_target="running")
    assert fresh["uptime_ms"] == 4000
    assert serial.writes == [b"start\n"]


def test_pause_freeze_detects_advancing_volume_and_does_not_clear_alarm():
    first = status(state="paused", uptime_ms=4000, delivered_ml=1)
    helper, serial, report = controller(
        [
            encoded(status(state="paused", uptime_ms=8000, delivered_ml=1.01)),
        ]
    )
    with pytest.raises(bench.BenchError, match="advanced while paused"):
        helper.freeze(first, "paused")
    helper.mode = "offline"
    helper.authorized = True
    helper.last_status = status(state="alarm", alarm="occlusion")
    report["checks"]["demo_applied_idle"] = {"result": "pass"}
    helper.cleanup()
    assert serial.writes == []
    assert "alarm left intact" in report["cleanup"]


def test_partial_serial_lines_survive_read_timeouts():
    message = encoded(status())
    helper, _, _ = controller([message[:15], b"", message[15:]])
    assert helper.wait("status") == status()
