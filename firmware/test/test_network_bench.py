"""Connected bench tests use fake serial, hub HTTP and MQTT callbacks only."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from firmware.test.test_bench import FakeClock, encoded, status
from firmware.tools import network_bench as network


class FakePump:
    def __init__(self, clock, mode="hub", **initial):
        self.clock = clock
        self.value = status(**initial)
        self.lines = [
            (network.bench.HUB_MARKER if mode == "hub" else network.bench.OFFLINE_MARKER).encode()
            + b"\n"
        ]
        self.writes = []
        self.api = None
        self.observer = None
        self.received_at = "2026-10-03T12:00:00+00:00"

    def fresh_received_at(self):
        base = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
        self.received_at = (base + timedelta(seconds=self.clock.now)).isoformat()

    def read(self, _):
        self.clock.now += 0.1
        if self.lines:
            return self.lines.pop(0)
        self.value["uptime_ms"] += 2000
        self.fresh_received_at()
        if self.value["state"] == "running":
            self.value["delivered_ml"] += self.value["rate_ml_hr"] / 1800
        return encoded(self.value)

    def reset_input_buffer(self):
        self.lines.clear()

    def flush(self):
        pass

    def transition(self, state):
        previous = self.value["state"]
        self.value["state"] = state
        self.lines.append(
            encoded(
                {
                    "pump_id": "pump-001",
                    "uptime_ms": self.value["uptime_ms"],
                    "simulated": True,
                    "type": "state_changed",
                    "from_state": previous,
                    "to_state": state,
                }
            )
        )

    def write(self, raw):
        self.writes.append(raw)
        command = raw.decode().strip()
        if command == "start":
            self.transition("priming")
            self.transition("running")
        elif command in {"pause", "clear"}:
            if command == "clear":
                self.lines.append(
                    encoded(
                        {
                            "pump_id": "pump-001",
                            "uptime_ms": self.value["uptime_ms"],
                            "simulated": True,
                            "type": "alarm_cleared",
                            "alarm": "occlusion",
                        }
                    )
                )
                self.value["alarm"] = None
                self.value["rate_ml_hr"] = 90
            self.transition("paused")
        elif command == "occlusion":
            self.value["alarm"] = "occlusion"
            self.value["rate_ml_hr"] = 0
            self.lines.append(
                encoded(
                    {
                        "pump_id": "pump-001",
                        "uptime_ms": self.value["uptime_ms"],
                        "simulated": True,
                        "type": "alarm_raised",
                        "alarm": "occlusion",
                    }
                )
            )
            self.transition("alarm")
        elif command == "resume":
            self.transition("running")
        elif command == "stop":
            self.transition("idle")
            if self.value["pending_version"]:
                prescription = self.api.items[self.value["pending_version"]]
                self.api.apply(prescription)
        elif command == "reboot":
            self.value["uptime_ms"] = 0
            self.lines.append(network.bench.HUB_MARKER.encode() + b"\n")
            self.observer.messages.extend(
                [
                    (self.clock(), "availability", b"offline"),
                    (self.clock() + 0.01, "availability", b"online"),
                ]
            )
        else:
            raise AssertionError(f"Unexpected command {command}")


class FakeApi:
    def __init__(self, pump):
        self.pump = pump
        pump.api = self
        self.items = {}
        self.calls = []
        self.timeout = 3

    def apply(self, item):
        self.pump.value.update(
            prescription_version=item["version"],
            rate_ml_hr=item["rate_ml_hr"],
            target_ml=item["volume_ml"],
            pending_version=None,
        )
        item["state"] = "active"

    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if path.endswith("/status"):
            value = {**self.pump.value, "online": True, "received_at": self.pump.received_at}
            del value["uptime_ms"]  # The real hub intentionally strips device uptime from HTTP.
            return value
        if method == "GET":
            return list(self.items.values())
        if path.endswith("/confirm"):
            version = int(path.split("/")[-2])
            item = self.items[version]
            item.update(
                confirmed_by=payload["confirmed_by"],
                confirmed_at="2026-10-03T12:01:00Z",
                state="sent",
            )
            wire = {
                k: item[k]
                for k in (
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
                )
            }
            self.pump.observer.messages.append((self.pump.clock(), "prescription", encoded(wire)))
            if item["rate_ml_hr"] == 500:
                self.pump.value.update(
                    last_rejected_version=version, last_reject_reason="rate_out_of_range"
                )
                item.update(state="rejected", reject_reason="rate_out_of_range")
            elif self.pump.value["state"] == "idle":
                self.apply(item)
            else:
                self.pump.value["pending_version"] = version
            # Hub returns sent before asynchronous telemetry changes the lifecycle.
            return {**item, "state": "sent"}
        version = max([self.pump.value["prescription_version"], *self.items]) + 1
        item = {
            **payload,
            "pump_id": "pump-001",
            "version": version,
            "state": "proposed",
            "confirmed_by": None,
            "proposed_at": "2026-10-03T12:00:00Z",
        }
        self.items[version] = item
        return item.copy()


class FakeObserver:
    def __init__(self, pump):
        self.pump = pump
        pump.observer = self
        self.messages = []
        self.started = False
        self.replays = []

    def start(self, timeout):
        self.started = True
        self.pump.clock.now += 0.1
        self.pump.fresh_received_at()
        self.messages.append((self.pump.clock(), "status", encoded(self.pump.value)))

    def matching(self, topic, since=0):
        return [(at, raw) for at, name, raw in self.messages if name == topic and at >= since]

    def replay(self, raw, timeout):
        assert raw == next(raw for _, name, raw in self.messages if name == "prescription")
        self.replays.append(raw)


def helper(mode="hub", **initial):
    clock = FakeClock()
    pump = FakePump(clock, mode, **initial)
    api = FakeApi(pump)
    observer = FakeObserver(pump)
    report = {"checks": {name: {"result": "not_run"} for name in network.CHECKS}}
    tester = network.NetworkBench(
        pump,
        report,
        api,
        observer,
        clock=clock,
        sleep=lambda seconds: setattr(clock, "now", clock.now + seconds),
    )
    return tester, pump, api, observer, report


@pytest.mark.parametrize(
    "mode,initial",
    [
        ("offline", {}),
        ("hub", {"simulated": False}),
        ("hub", {"state": "running"}),
        ("hub", {"alarm": "occlusion", "state": "alarm"}),
        ("hub", {"pending_version": 8}),
        ("hub", {"pump_id": "different-pump"}),
    ],
)
def test_network_gate_refuses_before_any_write_or_http(mode, initial):
    tester, pump, api, observer, _ = helper(mode, **initial)
    with pytest.raises(network.bench.BenchError):
        tester.run()
    tester.cleanup()
    assert pump.writes == []
    assert api.calls == []
    assert not observer.started


def test_connected_workflow_uses_hub_confirmation_and_exact_replay():
    tester, pump, api, observer, report = helper()
    tester.run()
    assert all(check["result"] == "pass" for check in report["checks"].values())
    proposals = [
        payload
        for method, path, payload in api.calls
        if method == "POST" and not path.endswith("/confirm")
    ]
    assert [payload["rate_ml_hr"] for payload in proposals] == [90, 500, 75]
    assert len(proposals[0]["note"]) == 200
    assert json.loads(observer.replays[0])["confirmed_by"] == "care-01"
    assert b"demo\n" not in pump.writes
    assert pump.value["state"] == "idle"
    assert pump.value["rate_ml_hr"] == 75
    assert report["queued_version"] > report["rejected_version"] > report["valid_version"]


def test_total_deadline_blocks_commands():
    tester, pump, _, _, _ = helper()
    tester.mode = "hub"
    tester.last_status = status()
    tester.authorized = True
    tester.deadline = -1
    with pytest.raises(network.bench.BenchError, match="total deadline"):
        tester.send("start")
    assert pump.writes == []


def test_alarm_cleanup_never_clears_or_stops():
    tester, pump, _, _, report = helper()
    tester.started_feed = True
    tester.authorized = True
    tester.mode = "hub"
    tester.last_status = status(state="alarm", alarm="occlusion")
    tester.cleanup()
    assert pump.writes == []
    assert "preserved" in report["cleanup"]


def test_api_rejects_url_credentials_without_network_calls():
    with pytest.raises(network.bench.BenchError, match="credentials"):
        network.HttpApi("http://example:secret@localhost:8000")


def test_availability_requires_later_online_after_offline():
    assert not network.offline_then_online([(1, b"online"), (2, b"offline")])
    assert not network.offline_then_online([(1, b"offline"), (1, b"online")])
    assert network.offline_then_online([(1, b"online"), (2, b"offline"), (3, b"online")])


def test_fresh_serial_status_discards_old_backlog():
    tester, pump, _, _, _ = helper()
    tester.last_status = status(uptime_ms=1000)
    pump.lines = [encoded(status(uptime_ms=99000))]
    assert tester.fresh_status()["uptime_ms"] == 4000


def test_stale_hub_snapshot_cannot_satisfy_fresh_mqtt_gate():
    mqtt_status = status()
    http_status = {k: v for k, v in mqtt_status.items() if k != "uptime_ms"}
    http_status.update(online=True, received_at="2026-10-03T12:00:00Z")
    baseline = http_status["received_at"]
    assert not network.hub_matches_fresh_sample(http_status, baseline, mqtt_status)
    http_status["received_at"] = "2026-10-03T12:00:02Z"
    assert network.hub_matches_fresh_sample(http_status, baseline, mqtt_status)
    http_status["prescription_version"] = 999
    assert not network.hub_matches_fresh_sample(http_status, baseline, mqtt_status)


@pytest.mark.parametrize(
    "event_type", ["prescription_applied", "prescription_queued", "prescription_rejected"]
)
def test_duplicate_replay_must_be_silent_for_all_prescription_events(event_type):
    tester, pump, _, observer, _ = helper()

    def broken_replay(raw, timeout):
        version = json.loads(raw)["version"]
        observer.messages.append(
            (
                pump.clock(),
                "event",
                encoded(
                    {
                        "pump_id": "pump-001",
                        "uptime_ms": pump.value["uptime_ms"],
                        "simulated": True,
                        "type": event_type,
                        "version": version,
                    }
                ),
            )
        )

    observer.replay = broken_replay
    with pytest.raises(network.bench.BenchError, match="emitted a prescription event"):
        tester.run()
    assert tester.current_check == "retained_replay_ignored"
