#!/usr/bin/env python3
"""Exercise a configured ESP32 digital pump through the real hub and broker.

Join the agreed private demo network before running. This helper never changes
WiFi, stops the broker, or intentionally resets the device when opening serial.
Press ESP32 reset after it begins listening to expose the hub startup marker.
Use only a scratch/test hub database: bench users clin-01/care-01 are intentional.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

try:
    from . import bench
except ImportError:
    import bench

CHECKS = (
    "mode_gate",
    "initial_idle",
    "hub_live_status",
    "proposal_confirmation_gate",
    "confirmed_long_note_applies",
    "retained_replay_ignored",
    "device_limit_rejection",
    "start_progression",
    "busy_prescription_queued",
    "pause_alarm_clear_resume",
    "queued_applies_on_stop",
    "idle_reboot_restores_nvs",
    "reboot_availability",
)


def require_hub(mode, status):
    if mode != "hub":
        raise bench.BenchError("Connected checks require the hub build; offline mode refused")
    bench.validate_status(status)


def offline_then_online(messages):
    offline_at = None
    for at, raw in sorted(messages, key=lambda item: item[0]):
        if raw == b"offline":
            offline_at = at
        elif raw == b"online" and offline_at is not None and at > offline_at:
            return True
    return False


def hub_matches_fresh_sample(status, baseline_received_at, mqtt_status):
    received = status.get("received_at")
    if not isinstance(received, str):
        return False
    try:
        timestamp = datetime.fromisoformat(received.replace("Z", "+00:00"))
        baseline = (
            datetime.fromisoformat(baseline_received_at.replace("Z", "+00:00"))
            if baseline_received_at
            else None
        )
        if timestamp.tzinfo is None or (baseline is not None and timestamp <= baseline):
            return False
    except (TypeError, ValueError):
        return False
    fields = (
        "pump_id",
        "prescription_version",
        "pending_version",
        "rate_ml_hr",
        "target_ml",
        "state",
        "alarm",
        "simulated",
    )
    return status.get("online") is True and all(
        status.get(field) == mqtt_status.get(field) for field in fields
    )


class HttpApi:
    def __init__(self, base_url, *, timeout=3):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise bench.BenchError("--hub must be an HTTP(S) base URL")
        if parsed.username or parsed.password:
            raise bench.BenchError("Do not put credentials in the hub URL")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise bench.BenchError(f"Hub HTTP {exc.code} for {method} {path}") from None
        except (OSError, ValueError):
            raise bench.BenchError(f"Hub unavailable or invalid JSON for {method} {path}") from None


class MqttObserver:
    """Bounded MQTT message buffer; only replays an exact hub-issued payload."""

    def __init__(self, host, port, pump_id):
        import paho.mqtt.client as mqtt

        self.host, self.port = host, port
        self.prefix = f"pump/{pump_id}/"
        self.messages = deque(maxlen=1024)
        self.lock = threading.Lock()
        self.ready = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._connect
        self.client.on_subscribe = lambda *args: self.ready.set()
        self.client.on_message = self._message

    def _connect(self, client, userdata, flags, reason, properties):
        if reason == 0:
            client.subscribe(
                [
                    (self.prefix + topic, 1)
                    for topic in ("status", "event", "availability", "prescription")
                ]
            )

    def _message(self, client, userdata, message):
        with self.lock:
            self.messages.append((time.monotonic(), message.topic, bytes(message.payload)))

    def start(self, timeout):
        self.client.connect_async(self.host, self.port, keepalive=10)
        self.client.loop_start()
        if not self.ready.wait(timeout):
            raise bench.BenchError("MQTT observer did not connect and subscribe before deadline")

    def matching(self, topic, since=0):
        with self.lock:
            return [
                (at, raw)
                for at, name, raw in self.messages
                if name == self.prefix + topic and at >= since
            ]

    def replay(self, payload, timeout):
        result = self.client.publish(self.prefix + "prescription", payload, qos=1, retain=False)
        result.wait_for_publish(timeout=timeout)
        if not result.is_published():
            raise bench.BenchError("Broker did not acknowledge exact confirmed prescription replay")

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()


class NetworkBench(bench.Bench):
    def __init__(
        self,
        port,
        report,
        api,
        observer,
        *,
        pump_id="pump-001",
        timeout=15,
        total_timeout=180,
        clock=time.monotonic,
        sleep=time.sleep,
    ):
        super().__init__(port, report, timeout=timeout, clock=clock)
        self.api, self.observer = api, observer
        self.pump_id = pump_id
        self.path = "/api/pumps/" + urllib.parse.quote(pump_id, safe="")
        self.deadline = clock() + total_timeout
        self.sleep = sleep
        self.started_feed = False

    def remaining(self):
        left = self.deadline - self.clock()
        if left <= 0:
            raise bench.BenchError("Connected bench exceeded its total deadline")
        return left

    def wait(self, kind, predicate=lambda _: True, *, timeout=None):
        limit = min(self.timeout if timeout is None else timeout, self.remaining())
        return super().wait(kind, predicate, timeout=limit)

    def api_request(self, method, suffix, payload=None):
        self.api.timeout = min(3, self.remaining())
        return self.api.request(method, self.path + suffix, payload)

    def discard_serial_backlog(self):
        self.port.reset_input_buffer()
        self.buffer.clear()

    def fresh_status(self):
        previous_uptime = self.last_status["uptime_ms"]
        self.discard_serial_backlog()
        return self.wait("status", lambda s: s["uptime_ms"] > previous_uptime)

    def until(self, callback, predicate):
        deadline = self.clock() + min(self.timeout, self.remaining())
        while self.clock() < deadline:
            value = callback()
            if predicate(value):
                return value
            self.sleep(min(0.2, max(0, deadline - self.clock())))
        raise bench.BenchError(
            "Hub/broker evidence did not reach the expected state before deadline"
        )

    def identify(self, probe=False):
        self.check("mode_gate")
        self.wait("mode")
        initial = self.wait("status")
        require_hub(self.mode, initial)
        if initial["pump_id"] != self.pump_id:
            raise bench.BenchError("Serial pump identity differs from requested hub pump")
        self.authorized = True
        self.passed("Hub marker and simulated=true serial status observed")
        return initial

    def send(self, command):
        self.remaining()
        if not self.authorized:
            raise bench.BenchError("Hub mode gate has not authorized serial controls")
        require_hub(self.mode, self.last_status)
        if command not in {"start", "pause", "resume", "stop", "occlusion", "clear", "reboot"}:
            raise bench.BenchError("Unsupported network bench command")
        self.port.reset_input_buffer()
        self.buffer.clear()
        self.port.write((command + "\n").encode("ascii"))
        self.port.flush()
        if command == "start":
            self.started_feed = True

    def prescription(self, version):
        items = self.api_request("GET", "/prescriptions")
        return next((item for item in items if item["version"] == version), None)

    def propose(self, rate, note=""):
        result = self.api_request(
            "POST",
            "/prescriptions",
            {
                "mode": "continuous",
                "rate_ml_hr": rate,
                "volume_ml": 5,
                "note": note,
                "proposed_by": "clin-01",
            },
        )
        if result["state"] != "proposed" or result["confirmed_by"]:
            raise bench.BenchError("New hub proposal did not await caregiver confirmation")
        if result["version"] <= self.last_status["prescription_version"]:
            raise bench.BenchError("Hub issued a version no newer than the real device")
        return result

    def confirm(self, proposal):
        version = proposal["version"]
        result = self.api_request(
            "POST", f"/prescriptions/{version}/confirm", {"confirmed_by": "care-01"}
        )
        if result["state"] not in {"confirmed", "sent", "active"}:
            raise bench.BenchError("Caregiver confirmation did not enter a published lifecycle")
        if result["confirmed_by"] != "care-01" or not result["confirmed_at"]:
            raise bench.BenchError("Confirmation evidence missing from hub response")
        return result

    def mqtt_prescription(self, version):
        def payload():
            for _, raw in reversed(self.observer.matching("prescription")):
                try:
                    value = json.loads(raw)
                except ValueError:
                    continue
                if value.get("version") == version:
                    return raw, value
            return None

        return self.until(payload, lambda value: value is not None)

    def run(self):
        initial = self.identify()
        self.check("initial_idle")
        if (
            initial["state"] != "idle"
            or initial["alarm"] is not None
            or initial["pending_version"] is not None
        ):
            raise bench.BenchError("Initial pump must be idle without alarm or pending update")
        self.passed("Existing idle pump left untouched before integration setup")

        self.check("hub_live_status")
        hub_baseline = self.api_request("GET", "/status").get("received_at")
        observer_started = self.clock()
        self.observer.start(min(self.timeout, self.remaining()))

        def observed_status():
            for _, raw in reversed(self.observer.matching("status", observer_started)):
                value = json.loads(raw)
                if (
                    value.get("pump_id") == self.pump_id
                    and value.get("simulated") is True
                    and value.get("uptime_ms", -1) >= initial["uptime_ms"]
                    and value.get("prescription_version") == initial["prescription_version"]
                ):
                    return value
            return None

        mqtt_status = self.until(observed_status, lambda value: value is not None)
        hub_status = self.until(
            lambda: self.api_request("GET", "/status"),
            lambda s: hub_matches_fresh_sample(s, hub_baseline, mqtt_status),
        )
        self.report["hub_status_before"] = hub_status
        self.report["mqtt_status_before"] = mqtt_status
        self.passed("Real hub reports fresh online simulated status matching the USB device")

        self.check("proposal_confirmation_gate")
        note = "Fictional ESP32 bench prescription; ".ljust(200, "x")
        assert len(note) == 200
        valid = self.propose(90, note)
        proposal_baseline = self.fresh_status()
        unchanged = self.wait(
            "status", lambda s: s["uptime_ms"] >= proposal_baseline["uptime_ms"] + 4000
        )
        if (
            unchanged["prescription_version"] != initial["prescription_version"]
            or unchanged["pending_version"] is not None
            or self.prescription(valid["version"])["state"] != "proposed"
        ):
            raise bench.BenchError("Unconfirmed proposal changed the pump or became active")
        self.passed("90 mL/hr proposal stayed proposed and did not change pump before confirmation")

        self.check("confirmed_long_note_applies")
        self.confirm(valid)
        applied = self.wait("status", lambda s: s["prescription_version"] == valid["version"])
        if applied["state"] != "idle" or applied["rate_ml_hr"] != 90 or applied["target_ml"] != 5:
            raise bench.BenchError(
                "Confirmed prescription did not apply with exact values while idle"
            )
        self.until(lambda: self.prescription(valid["version"]), lambda p: p["state"] == "active")
        raw, wire = self.mqtt_prescription(valid["version"])
        expected_keys = {
            "pump_id",
            "version",
            "mode",
            "rate_ml_hr",
            "volume_ml",
            "note",
            "proposed_by",
            "proposed_at",
            "confirmed_by",
            "confirmed_at",
        }
        if set(wire) != expected_keys or wire["note"] != note:
            raise bench.BenchError("Wire prescription did not contain the exact 200-character note")
        self.report["valid_version"] = valid["version"]
        self.passed(
            "Confirmed 90 mL/hr, 5 mL and 200-character note traversed MQTT; pump applied idle"
        )

        self.check("retained_replay_ignored")
        replay_baseline = self.fresh_status()
        rejection_before = (
            replay_baseline.get("last_rejected_version"),
            replay_baseline.get("last_reject_reason"),
        )
        self.discard_serial_backlog()
        replay_at = self.clock()
        self.observer.replay(raw, min(self.timeout, self.remaining()))
        replayed = self.wait(
            "status", lambda s: s["uptime_ms"] >= replay_baseline["uptime_ms"] + 4000
        )
        rejection_after = (
            replayed.get("last_rejected_version"),
            replayed.get("last_reject_reason"),
        )
        if (
            replayed["prescription_version"] != valid["version"]
            or replayed["pending_version"] is not None
            or rejection_after != rejection_before
        ):
            raise bench.BenchError("Exact retained replay changed prescription or rejection fields")
        for _, payload in self.observer.matching("event", replay_at):
            event = json.loads(payload)
            if (
                event.get("type", "").startswith("prescription_")
                and event.get("version") == valid["version"]
            ):
                raise bench.BenchError(
                    "Duplicate accepted prescription emitted a prescription event"
                )
        self.passed(
            "Exact caregiver-confirmed MQTT payload replayed non-retained; pump ignored duplicate"
        )

        self.check("device_limit_rejection")
        invalid = self.propose(500, "Fictional out-of-range bench case")
        self.confirm(invalid)
        rejected = self.wait(
            "status",
            lambda s: (
                s.get("last_rejected_version") == invalid["version"]
                and s.get("last_reject_reason") == "rate_out_of_range"
            ),
        )
        repeated = self.wait("status", lambda s: s["uptime_ms"] >= rejected["uptime_ms"] + 2000)
        if (
            repeated.get("last_rejected_version") != invalid["version"]
            or repeated.get("last_reject_reason") != "rate_out_of_range"
            or repeated["prescription_version"] != valid["version"]
            or repeated["rate_ml_hr"] != 90
        ):
            raise bench.BenchError("Device rejection was not repeated or changed accepted settings")
        self.until(
            lambda: self.prescription(invalid["version"]),
            lambda p: p["state"] == "rejected" and p["reject_reason"] == "rate_out_of_range",
        )
        self.report["rejected_version"] = invalid["version"]
        self.passed(
            "Hub sent caregiver-confirmed 500; ESP32 rejected and repeated reason in status"
        )

        self.check("start_progression")
        running = self.transition("start", "priming", status_target="running")
        self.progression(running)
        self.passed("Real ESP32 advanced digital delivery at accepted 90 mL/hr")

        self.check("busy_prescription_queued")
        queued = self.propose(75, "Fictional queued bench update")
        self.confirm(queued)
        pending = self.wait("status", lambda s: s["pending_version"] == queued["version"])
        later = self.progression(pending)
        if (
            later["prescription_version"] != valid["version"]
            or later["rate_ml_hr"] != 90
            or later["pending_version"] != queued["version"]
            or self.prescription(queued["version"])["state"] == "active"
        ):
            raise bench.BenchError("Queued update changed the active feed before returning idle")
        self.report["queued_version"] = queued["version"]
        self.passed("New confirmed 75 mL/hr version remained pending during running at 90 mL/hr")

        self.check("pause_alarm_clear_resume")
        paused = self.transition("pause", "paused")
        self.freeze(paused, "paused")
        alarm = self.transition("occlusion", "alarm", alarm_event="alarm_raised")
        self.freeze(alarm, "alarm", alarm="occlusion")
        clear = self.transition("clear", "paused", alarm_event="alarm_cleared")
        self.freeze(clear, "paused")
        resumed = self.transition("resume", "running")
        self.progression(resumed)
        self.passed(
            "Pause froze; occlusion stopped; clear remained paused; separate resume advanced"
        )

        self.check("queued_applies_on_stop")
        stopped = self.transition("stop", "idle")
        if (
            stopped["prescription_version"] != queued["version"]
            or stopped["rate_ml_hr"] != 75
            or stopped["pending_version"] is not None
        ):
            raise bench.BenchError("Queued prescription did not apply on returning idle")
        self.until(lambda: self.prescription(queued["version"]), lambda p: p["state"] == "active")
        self.passed("Stop returned idle and applied queued version; hub now reports it active")

        self.check("idle_reboot_restores_nvs")
        before_reboot = self.clock()
        expected = {
            key: stopped[key] for key in ("prescription_version", "rate_ml_hr", "target_ml")
        }
        self.send("reboot")
        self.mode = None
        self.wait("mode")
        restored = self.wait("status")
        require_hub(self.mode, restored)
        if (
            restored["uptime_ms"] >= stopped["uptime_ms"]
            or restored["state"] != "idle"
            or restored["alarm"] is not None
            or any(restored[k] != v for k, v in expected.items())
        ):
            raise bench.BenchError(
                "Fresh reboot did not restore exact NVS prescription safely idle"
            )
        self.passed("Fresh boot and lower uptime; same queued version/rate/target restored idle")

        self.check("reboot_availability")

        def availability():
            return self.observer.matching("availability", before_reboot)

        self.until(availability, offline_then_online)
        self.passed("Broker observed offline followed by online across controlled idle restart")

    def cleanup(self):
        if (
            self.started_feed
            and self.authorized
            and self.mode == "hub"
            and self.last_status
            and self.last_status["state"] in {"priming", "running", "paused"}
        ):
            try:
                # Permit only a brief stop after the test's overall deadline.
                self.deadline = max(self.deadline, self.clock() + 5)
                self.transition("stop", "idle")
                self.report["cleanup"] = "Stopped helper-started feed to idle; pending may apply"
            except Exception:
                self.report["cleanup"] = "Stop not confirmed; inspect device manually"
        elif self.last_status and self.last_status["state"] == "alarm":
            self.report["cleanup"] = "Active alarm preserved; no automatic clear"


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
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--total-timeout", type=float, default=180)
    args = parser.parse_args(argv)
    if not 5 <= args.timeout <= 30 or not 60 <= args.total_timeout <= 300:
        parser.error("--timeout must be 5–30 and --total-timeout 60–300 seconds")
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "prototype": True,
        "simulated": None,
        "device_mode": "unknown",
        "port": args.port,
        "checks": {name: {"result": "not_run"} for name in CHECKS},
        "wifi_loss": {"result": "not_run", "detail": "No WiFi or broker shutdown performed"},
    }
    helper = port = observer = None
    result = 1
    print(
        "WARNING: use only a scratch/test hub database; bench users are clin-01/care-01.\n"
        "Listening for hub mode. Press ESP32 reset; WiFi must already be configured/joined.",
        flush=True,
    )
    try:
        api = HttpApi(args.hub)
        port = bench.open_serial(args.port)
        observer = MqttObserver(args.broker, args.broker_port, args.pump_id)
        helper = NetworkBench(
            port,
            report,
            api,
            observer,
            pump_id=args.pump_id,
            timeout=args.timeout,
            total_timeout=args.total_timeout,
        )
        helper.run()
        result = 0
    except KeyboardInterrupt:
        report["error"] = "Interrupted by operator"
    except bench.BenchError as exc:
        report["error"] = str(exc)
    except Exception as exc:
        report["error"] = f"Connected helper failed: {type(exc).__name__}; inspect setup"
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
