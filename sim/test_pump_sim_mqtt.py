"""MqttLink tests with a fake paho client. No broker needed."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from sim import pump_sim
from sim.pump_sim import MqttLink, PumpCore, handle_key
from sim.test_pump_sim import FakeClock, FakePublisher, rx

ROOT = Path(__file__).parent.parent


class FakeInfo:
    def __init__(self) -> None:
        self.waited = False

    def wait_for_publish(self, timeout=None) -> None:
        self.waited = True


class FakeSocket:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.published: list[tuple[str, str, int, bool]] = []
        self.will = None
        self.sock = FakeSocket()
        self.loop_running = False

    def will_set(self, topic, payload, qos=0, retain=False):
        self.will = (topic, payload, qos, retain)

    def reconnect_delay_set(self, min_delay, max_delay):
        pass

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))
        self.calls.append(("publish", topic, payload))
        return FakeInfo()

    def subscribe(self, topic, qos=0):
        self.calls.append(("subscribe", topic, qos))

    def connect_async(self, host, port, keepalive=60):
        self.calls.append(("connect_async", host, port, keepalive))

    def loop_start(self):
        self.loop_running = True
        self.calls.append(("loop_start",))

    def loop_stop(self):
        self.loop_running = False
        self.calls.append(("loop_stop",))

    def disconnect(self):
        self.calls.append(("disconnect",))

    def socket(self):
        return self.sock


OK = SimpleNamespace(is_failure=False)


def make(pump_id="pump-001"):
    clock = FakeClock()
    client = FakeClient()
    box: list[MqttLink] = []
    validated = FakePublisher()

    def publish(topic, payload):
        validated(topic, payload)  # schema-checks everything sent
        box[0].publish(topic, payload)

    core = PumpCore(pump_id, publish=publish, clock=clock)
    link = MqttLink(core, "localhost", 1883, client=client)
    box.append(link)
    return core, link, client, clock


def connect(link, client):
    link.start()
    link.on_connect(client, None, {}, OK, None)


def msg(topic, payload):
    return SimpleNamespace(topic=topic, payload=payload.encode())


def test_last_will_is_retained_offline_qos1():
    _, _, client, _ = make()
    assert client.will == ("pump/pump-001/availability", "offline", 1, True)


def test_on_connect_online_then_subscribe():
    _, link, client, _ = make()
    connect(link, client)
    assert ("connect_async", "localhost", 1883, pump_sim.KEEPALIVE_S) in client.calls
    assert ("pump/pump-001/availability", "online", 1, True) in client.published
    assert ("subscribe", "pump/pump-001/prescription", 1) in client.calls


def test_failed_connect_does_not_subscribe():
    _, link, client, _ = make()
    link.on_connect(client, None, {}, SimpleNamespace(is_failure=True), None)
    assert not any(c[0] == "subscribe" for c in client.calls)
    assert link.connected is False


def test_pump_publish_qos_matches_topics_md():
    core, link, client, clock = make()
    connect(link, client)
    link.on_message(client, None, msg("pump/pump-001/prescription", rx(1)))
    core.tick()
    sent = [p for p in client.published if not p[0].endswith("/availability")]
    assert sent and all(r is False for _, _, _, r in sent)
    assert {q for t, _, q, _ in sent if t.endswith("/status")} == {0}
    assert {q for t, _, q, _ in sent if t.endswith("/event")} == {1}
    assert all(json.loads(p)["simulated"] is True for _, p, _, _ in sent)


def test_message_routed_to_core():
    core, link, client, _ = make()
    connect(link, client)
    link.on_message(client, None, msg("pump/pump-001/prescription", rx(3)))
    assert core.version == 3
    link.on_message(client, None, msg("pump/pump-001/other", rx(4)))
    assert core.version == 3


def test_retained_replay_on_reconnect_is_silent():
    core, link, client, _ = make()
    connect(link, client)
    link.on_message(client, None, msg("pump/pump-001/prescription", rx(5)))
    link.on_disconnect(client, None, {}, OK, None)
    client.published.clear()
    link.on_connect(client, None, {}, OK, None)  # re-subscribes, broker replays
    link.on_message(client, None, msg("pump/pump-001/prescription", rx(5)))
    events = [p for p in client.published if p[0].endswith("/event")]
    assert events == []
    assert core.version == 5


def test_drop_keeps_feed_running_and_suppresses_publishes():
    core, link, client, clock = make()
    connect(link, client)
    link.on_message(client, None, msg("pump/pump-001/prescription", rx(1)))
    core.start()
    for _ in range(20):
        clock.t += 0.5
        core.tick()
    assert core.state == "running"
    handle_key("d", core, link, threading.Event())
    assert link.dropped and client.sock.closed and not client.loop_running
    assert ("disconnect",) not in client.calls  # ungraceful, so the Will fires
    client.published.clear()
    d0 = core.delivered_ml
    for _ in range(40):
        clock.t += 0.5
        core.tick()
    assert client.published == []  # nothing gets out while "wifi" is down
    assert core.state == "running"
    assert core.delivered_ml - d0 == pytest.approx(90 * 20 / 3600, abs=1e-6)
    handle_key("d", core, link, threading.Event())
    assert not link.dropped and client.loop_running


def test_graceful_shutdown_publishes_offline_before_disconnect():
    _, link, client, _ = make()
    connect(link, client)
    link.shutdown()
    i_off = client.calls.index(("publish", "pump/pump-001/availability", "offline"))
    i_disc = client.calls.index(("disconnect",))
    assert i_off < i_disc
    assert ("pump/pump-001/availability", "offline", 1, True) in client.published
    assert not client.loop_running


def test_quit_key_sets_stop():
    core, link, _, _ = make()
    stop = threading.Event()
    handle_key("q", core, link, stop)
    assert stop.is_set()


def test_keys_drive_core():
    core, link, client, clock = make()
    connect(link, client)
    stop = threading.Event()
    core.handle_prescription(rx(1))
    handle_key("s", core, link, stop)
    assert core.state == "priming"
    clock.t += pump_sim.PRIME_S + 0.1
    core.tick()
    handle_key("p", core, link, stop)
    assert core.state == "paused"
    handle_key("o", core, link, stop)
    assert core.state == "alarm" and core.alarm == "occlusion"
    handle_key("c", core, link, stop)
    assert core.state == "paused"
    handle_key("p", core, link, stop)
    handle_key("b", core, link, stop)
    assert core.alarm == "bag_empty"


def test_cli_help_runs():
    out = subprocess.run(
        [sys.executable, "-m", "sim.pump_sim", "--help"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0
    assert "SIMULATED" in out.stdout and "--speed" in out.stdout


def test_handler_error_does_not_escape_on_message(monkeypatch):
    core, link, client, _ = make()
    connect(link, client)

    def boom(payload):
        raise RuntimeError("bug")

    monkeypatch.setattr(core, "handle_prescription", boom)
    # Must not raise: an exception here would stop paho's network thread.
    link.on_message(client, None, msg("pump/pump-001/prescription", rx(1)))
