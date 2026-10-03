"""PumpCore tests: no broker, fake publisher, fake clock.

Every payload the core publishes is validated against the shared schemas.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from sim import pump_sim
from sim.pump_sim import PumpCore

PROTOCOL = Path(__file__).parent.parent / "shared" / "protocol"


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((PROTOCOL / f"{name}.schema.json").read_text())
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


STATUS = _validator("status")
EVENT = _validator("event")


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    def __call__(self, topic: str, payload: str) -> None:
        msg = json.loads(payload)
        kind = topic.rsplit("/", 1)[-1]
        validator = {"status": STATUS, "event": EVENT}[kind]
        errors = [e.message for e in validator.iter_errors(msg)]
        assert not errors, (topic, msg, errors)
        assert msg["simulated"] is True
        self.messages.append((topic, msg))

    def events(self, type_: str | None = None) -> list[dict]:
        return [
            m for t, m in self.messages
            if t.endswith("/event") and (type_ is None or m["type"] == type_)
        ]

    def statuses(self) -> list[dict]:
        return [m for t, m in self.messages if t.endswith("/status")]

    def clear(self) -> None:
        self.messages.clear()


def rx(version: int = 1, **overrides) -> str:
    msg = json.loads((PROTOCOL / "examples" / "prescription.json").read_text())
    msg["version"] = version
    msg.update(overrides)
    for k, v in list(msg.items()):
        if v is _DELETE:
            del msg[k]
    return json.dumps(msg)


_DELETE = object()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def pub() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def core(clock, pub) -> PumpCore:
    return PumpCore("pump-001", publish=pub, clock=clock)


def advance(core: PumpCore, clock: FakeClock, seconds: float, step: float = 0.5) -> None:
    end = clock.t + seconds
    while clock.t < end:
        clock.t = min(end, clock.t + step)
        core.tick()


def run_to_running(core, clock):
    assert core.start()
    advance(core, clock, pump_sim.PRIME_S + 0.5)
    assert core.state == "running"


# ---- happy path --------------------------------------------------------

def test_apply_in_idle(core, pub):
    assert core.handle_prescription(rx(1)) == "applied"
    (ev,) = pub.events()
    assert ev["type"] == "prescription_applied" and ev["version"] == 1
    st = core.status()
    assert st["prescription_version"] == 1
    assert st["target_ml"] == 500 and st["rate_ml_hr"] == 90
    assert st["last_rejected_version"] is None and st["last_reject_reason"] is None


def test_status_every_two_seconds_and_schema(core, clock, pub):
    core.tick()
    advance(core, clock, 10, step=0.1)
    sts = pub.statuses()
    assert 5 <= len(sts) <= 6
    assert all(s["simulated"] is True for s in sts)
    assert "last_rejected_version" in sts[0] and sts[0]["last_rejected_version"] is None


def test_status_period_not_scaled_by_speed(clock, pub):
    core = PumpCore("pump-001", publish=pub, clock=clock, speed=60)
    core.tick()
    advance(core, clock, 10, step=0.1)
    assert 5 <= len(pub.statuses()) <= 6


# ---- rejections, each reason ------------------------------------------

@pytest.mark.parametrize(
    "payload, reason",
    [
        (rx(3, mode="drip"), "malformed"),
        (rx(3, rate_ml_hr="90"), "malformed"),
        (rx(3, rate_ml_hr=True), "malformed"),
        (rx(3, volume_ml=_DELETE), "malformed"),
        (rx(3, pump_id=7), "malformed"),
        (rx(3, pump_id="pump-002"), "wrong_pump"),
        (rx(3, confirmed_by=_DELETE), "not_confirmed"),
        (rx(3, confirmed_by=""), "not_confirmed"),
        (rx(3, confirmed_at=_DELETE), "not_confirmed"),
        (rx(3, confirmed_at=""), "not_confirmed"),
        (rx(3, confirmed_by=None), "not_confirmed"),
        (rx(3, rate_ml_hr=pump_sim.LIMIT_RATE_MIN_ML_HR - 0.5), "rate_out_of_range"),
        (rx(3, rate_ml_hr=500), "rate_out_of_range"),
        (rx(3, rate_ml_hr=pump_sim.LIMIT_RATE_MAX_ML_HR + 0.01), "rate_out_of_range"),
        (rx(3, volume_ml=0.5), "volume_out_of_range"),
        (rx(3, volume_ml=pump_sim.LIMIT_VOLUME_MAX_ML + 1), "volume_out_of_range"),
    ],
)
def test_rejection_reasons(core, pub, payload, reason):
    core.handle_prescription(rx(2))
    pub.clear()
    before = core.status()
    assert core.handle_prescription(payload) == reason
    (ev,) = pub.events()
    assert ev == {**ev, "type": "prescription_rejected", "version": 3, "reason": reason}
    after = core.status()
    # nothing changes, and never clamped (S1)
    assert after["prescription_version"] == 2 and after["rate_ml_hr"] == before["rate_ml_hr"]
    assert after["target_ml"] == before["target_ml"]
    assert after["last_rejected_version"] == 3 and after["last_reject_reason"] == reason


def test_limits_inclusive(core):
    assert core.handle_prescription(
        rx(1, rate_ml_hr=pump_sim.LIMIT_RATE_MAX_ML_HR, volume_ml=pump_sim.LIMIT_VOLUME_MAX_ML)
    ) == "applied"
    assert core.handle_prescription(
        rx(2, rate_ml_hr=pump_sim.LIMIT_RATE_MIN_ML_HR, volume_ml=pump_sim.LIMIT_VOLUME_MIN_ML)
    ) == "applied"


def test_stale_version(core, pub):
    core.handle_prescription(rx(5))
    pub.clear()
    assert core.handle_prescription(rx(4)) == "stale_version"
    assert pub.events()[0]["reason"] == "stale_version"
    assert core.status()["last_rejected_version"] == 4


def test_stale_below_pending(core, clock, pub):
    core.handle_prescription(rx(5))
    run_to_running(core, clock)
    assert core.handle_prescription(rx(8)) == "queued"
    pub.clear()
    assert core.handle_prescription(rx(7)) == "stale_version"
    assert core.status()["pending_version"] == 8


def test_order_first_failure_wins(core):
    # wrong pump AND unconfirmed AND out of range -> wrong_pump
    payload = rx(4, pump_id="pump-009", confirmed_by="", rate_ml_hr=999)
    assert core.handle_prescription(payload) == "wrong_pump"
    # unconfirmed AND out of range -> not_confirmed
    assert core.handle_prescription(rx(4, confirmed_by="", rate_ml_hr=999)) == "not_confirmed"
    # rate and volume out -> rate first
    assert core.handle_prescription(rx(4, rate_ml_hr=999, volume_ml=0)) == "rate_out_of_range"


def test_malformed_beats_wrong_pump(core):
    assert core.handle_prescription(rx(4, pump_id="other", mode="x")) == "malformed"


def test_unconfirmed_stale_is_not_confirmed(core):
    core.handle_prescription(rx(5))
    assert core.handle_prescription(rx(3, confirmed_by=_DELETE)) == "not_confirmed"


@pytest.mark.parametrize(
    "payload",
    [b"not json", b"[1,2]", b'{"version": "3"}', b'{"version": 0}', b'{"version": true}',
     b'{"version": NaN}', b"\xff\xfe"],
)
def test_malformed_without_readable_version_is_dropped(core, pub, payload):
    assert core.handle_prescription(payload) == "dropped"
    assert pub.events() == []
    assert core.status()["last_rejected_version"] is None


def test_nan_rate_is_malformed_not_applied(core, pub):
    payload = rx(3).replace('"rate_ml_hr": 90', '"rate_ml_hr": NaN')
    # NaN makes the whole payload unparseable, so there is no readable version.
    assert core.handle_prescription(payload) == "dropped"
    assert core.status()["prescription_version"] == 0


def test_reject_fields_persist_until_next_rejection(core, clock, pub):
    core.handle_prescription(rx(1))
    core.handle_prescription(rx(2, rate_ml_hr=500))
    assert core.handle_prescription(rx(3)) == "applied"
    advance(core, clock, 6)
    st = pub.statuses()[-1]
    assert st["last_rejected_version"] == 2 and st["last_reject_reason"] == "rate_out_of_range"
    core.handle_prescription(rx(4, volume_ml=5000))
    st = core.status()
    assert st["last_rejected_version"] == 4 and st["last_reject_reason"] == "volume_out_of_range"


# ---- replays -----------------------------------------------------------

def test_replay_of_current_is_silent(core, pub):
    core.handle_prescription(rx(1))
    pub.clear()
    assert core.handle_prescription(rx(1)) == "ignored"
    assert pub.events() == []
    assert core.status()["last_rejected_version"] is None


def test_replay_of_current_does_not_touch_reject_fields(core, pub):
    core.handle_prescription(rx(1))
    core.handle_prescription(rx(2, rate_ml_hr=500))
    pub.clear()
    assert core.handle_prescription(rx(1)) == "ignored"
    assert pub.events() == []
    st = core.status()
    assert st["last_rejected_version"] == 2 and st["last_reject_reason"] == "rate_out_of_range"


def test_replay_of_pending_is_silent(core, clock, pub):
    core.handle_prescription(rx(1))
    run_to_running(core, clock)
    assert core.handle_prescription(rx(2)) == "queued"
    pub.clear()
    assert core.handle_prescription(rx(2)) == "ignored"
    assert pub.events() == []
    assert core.status()["pending_version"] == 2


def test_retained_replay_after_reconnect(core, pub):
    """After a reconnect the broker re-delivers the retained prescription: harmless."""
    core.handle_prescription(rx(7))
    pub.clear()
    for _ in range(3):
        assert core.handle_prescription(rx(7)) == "ignored"
    assert pub.events() == []
    assert core.status()["prescription_version"] == 7


# ---- queueing (S4) -----------------------------------------------------

@pytest.mark.parametrize("busy", ["priming", "running", "paused", "alarm", "complete"])
def test_apply_only_in_idle(core, clock, pub, busy):
    core.handle_prescription(rx(1, volume_ml=10, rate_ml_hr=150))
    core.start()
    if busy != "priming":
        advance(core, clock, pump_sim.PRIME_S + 0.5)
    if busy == "paused":
        core.toggle_pause()
    elif busy == "alarm":
        core.raise_alarm("occlusion")
    elif busy == "complete":
        advance(core, clock, 241)
    assert core.state == busy
    pub.clear()
    assert core.handle_prescription(rx(2, rate_ml_hr=60)) == "queued"
    (ev,) = pub.events()
    assert ev["type"] == "prescription_queued" and ev["version"] == 2
    st = core.status()
    assert st["prescription_version"] == 1 and st["pending_version"] == 2
    assert st["rate_ml_hr"] in (0, 150)


def test_queue_then_apply_on_return_to_idle(core, clock, pub):
    core.handle_prescription(rx(1, rate_ml_hr=120, volume_ml=4))
    run_to_running(core, clock)
    assert core.handle_prescription(rx(2, rate_ml_hr=60, volume_ml=300)) == "queued"
    # 4 mL at 120 mL/hr is 120 s, then hold in complete, then idle
    advance(core, clock, 130 + pump_sim.COMPLETE_HOLD_S + 1)
    assert core.state == "idle"
    st = core.status()
    assert st["prescription_version"] == 2 and st["pending_version"] is None
    assert st["rate_ml_hr"] == 60 and st["target_ml"] == 300
    types = [e["type"] for e in pub.events()]
    i_idle = next(
        i for i, e in enumerate(pub.events())
        if e["type"] == "state_changed" and e["to_state"] == "idle"
    )
    assert types[i_idle + 1] == "prescription_applied"
    assert pub.events()[i_idle + 1]["version"] == 2


def test_newer_pending_replaces_older(core, clock):
    core.handle_prescription(rx(1))
    run_to_running(core, clock)
    assert core.handle_prescription(rx(2)) == "queued"
    assert core.handle_prescription(rx(3)) == "queued"
    assert core.status()["pending_version"] == 3


def test_rejected_while_running_does_not_queue(core, clock):
    core.handle_prescription(rx(1))
    run_to_running(core, clock)
    assert core.handle_prescription(rx(2, rate_ml_hr=500)) == "rate_out_of_range"
    assert core.status()["pending_version"] is None


# ---- state machine -----------------------------------------------------

def test_state_changed_events(core, clock, pub):
    core.handle_prescription(rx(1))
    pub.clear()
    run_to_running(core, clock)
    sc = [(e["from_state"], e["to_state"]) for e in pub.events("state_changed")]
    assert sc == [("idle", "priming"), ("priming", "running")]


def test_illegal_transition_raises(core):
    with pytest.raises(ValueError):
        core.transition_to("running")


def test_start_needs_prescription(core, pub):
    assert core.start() is False
    assert core.state == "idle"
    assert pub.events() == []


def test_pause_resume(core, clock, pub):
    core.handle_prescription(rx(1))
    run_to_running(core, clock)
    assert core.toggle_pause() and core.state == "paused"
    d = core.delivered_ml
    advance(core, clock, 60)
    assert core.delivered_ml == d  # no delivery while paused
    assert core.toggle_pause() and core.state == "running"


# ---- alarms ------------------------------------------------------------

@pytest.mark.parametrize("alarm", ["occlusion", "bag_empty"])
def test_alarm_raise_and_clear_goes_to_paused(core, clock, pub, alarm):
    core.handle_prescription(rx(1))
    run_to_running(core, clock)
    pub.clear()
    assert core.raise_alarm(alarm)
    evs = pub.events()
    assert evs[0] == {**evs[0], "type": "alarm_raised", "alarm": alarm}
    assert (evs[1]["from_state"], evs[1]["to_state"]) == ("running", "alarm")
    st = core.status()
    assert st["state"] == "alarm" and st["alarm"] == alarm and st["rate_ml_hr"] == 0
    d = core.delivered_ml
    advance(core, clock, 60)
    assert core.delivered_ml == d  # actuator stopped

    pub.clear()
    assert core.clear_alarm()
    evs = pub.events()
    assert evs[0] == {**evs[0], "type": "alarm_cleared", "alarm": alarm}
    assert (evs[1]["from_state"], evs[1]["to_state"]) == ("alarm", "paused")
    assert core.state == "paused" and core.status()["alarm"] is None


def test_alarm_from_paused(core, clock):
    core.handle_prescription(rx(1))
    run_to_running(core, clock)
    core.toggle_pause()
    assert core.raise_alarm("bag_empty") and core.state == "alarm"


def test_alarm_ignored_when_idle(core, pub):
    assert core.raise_alarm("occlusion") is False
    assert core.clear_alarm() is False
    assert pub.events() == []


def test_pause_ignored_in_alarm(core, clock):
    core.handle_prescription(rx(1))
    run_to_running(core, clock)
    core.raise_alarm("occlusion")
    assert core.toggle_pause() is False and core.state == "alarm"


# ---- delivery ----------------------------------------------------------

def test_delivery_and_completion(core, clock, pub):
    core.handle_prescription(rx(1, rate_ml_hr=60, volume_ml=2))
    run_to_running(core, clock)
    advance(core, clock, 60)
    assert core.delivered_ml == pytest.approx(1.0, abs=0.02)
    advance(core, clock, 61)
    assert core.state == "complete"
    assert core.delivered_ml == 2
    st = pub.statuses()[-1]
    assert st["delivered_ml"] <= st["target_ml"]
    advance(core, clock, pump_sim.COMPLETE_HOLD_S + 1)
    assert core.state == "idle"


def test_speed_scales_delivery(clock, pub):
    core = PumpCore("pump-001", publish=pub, clock=clock, speed=60)
    core.handle_prescription(rx(1, rate_ml_hr=60, volume_ml=500))
    core.start()
    advance(core, clock, 1)  # 60 sim seconds covers priming
    assert core.state == "running"
    d0 = core.delivered_ml
    advance(core, clock, 10)  # 600 sim seconds at 60 mL/hr = 10 mL
    assert core.delivered_ml - d0 == pytest.approx(10.0, abs=0.01)


def test_start_resets_delivered(core, clock):
    core.handle_prescription(rx(1, rate_ml_hr=150, volume_ml=1))
    run_to_running(core, clock)
    advance(core, clock, 60 + pump_sim.COMPLETE_HOLD_S)
    assert core.state == "idle" and core.delivered_ml == 1
    core.start()
    assert core.delivered_ml == 0


# ---- S6 ----------------------------------------------------------------

def test_publish_failure_does_not_change_delivery(clock):
    """Two identical pumps, one with every publish lost: delivery must be identical."""
    online_pub = FakePublisher()
    online = PumpCore("pump-001", publish=online_pub, clock=clock)
    offline = PumpCore("pump-001", publish=lambda topic, payload: None, clock=clock)
    for c in (online, offline):
        c.handle_prescription(rx(1))
        c.start()
    for _ in range(200):
        clock.t += 0.5
        online.tick()
        offline.tick()
    assert online.state == offline.state == "running"
    assert online.delivered_ml == offline.delivered_ml > 0


def test_state_file_round_trip(tmp_path, clock, pub):
    path = tmp_path / "state.json"
    a = PumpCore("pump-001", publish=pub, clock=clock, state_file=path)
    a.handle_prescription(rx(4))
    b = PumpCore("pump-001", publish=pub, clock=clock, state_file=path)
    assert b.status()["prescription_version"] == 4
    assert b.handle_prescription(rx(4)) == "ignored"
    assert b.handle_prescription(rx(3)) == "stale_version"


def test_state_file_garbage_ignored(tmp_path, clock, pub):
    path = tmp_path / "state.json"
    path.write_text("{oops")
    assert PumpCore("pump-001", publish=pub, clock=clock, state_file=path).version == 0


# ---- safety review follow-ups ---------------------------------------------


def test_huge_integer_rate_is_malformed_not_an_error(core, pub):
    payload = rx(2).replace('"rate_ml_hr": 90', '"rate_ml_hr": 1' + "0" * 400)
    assert '"rate_ml_hr": 1000' in payload
    assert core.handle_prescription(payload) == "malformed"
    assert core.status()["last_reject_reason"] == "malformed"
    assert core.version == 0


@pytest.mark.parametrize("version", [2**31, 10**20])
def test_version_above_int32_is_dropped(core, version):
    # Outside 1..2147483647 is not a readable version (PROTOCOL.md check 1).
    assert core.handle_prescription(rx(version)) == "dropped"
    assert core.status()["last_rejected_version"] is None
    assert core.handle_prescription(rx(2**31 - 1)) == "applied"


@pytest.mark.parametrize(
    "bad",
    [
        {"rate_ml_hr": 500},
        {"volume_ml": 5000},
        {"confirmed_by": ""},
        {"confirmed_at": None},
        {"pump_id": "pump-999"},
    ],
)
def test_state_file_with_invalid_prescription_is_discarded(tmp_path, clock, pub, bad):
    path = tmp_path / "state.json"
    saved = json.loads(rx(4))
    saved.update(bad)
    path.write_text(json.dumps({"prescription": saved}))
    assert PumpCore("pump-001", publish=pub, clock=clock, state_file=path).version == 0


def test_demo_seed_starts_feed_and_is_superseded_normally(core, clock, pub):
    assert core.seed_demo_prescription()
    assert core.version == 7 and not pub.messages  # loaded like NVS: no events
    run_to_running(core, clock)
    assert core.status()["rate_ml_hr"] == 60
    assert core.handle_prescription(rx(7)) == "ignored"
    assert core.handle_prescription(rx(8)) == "queued"


def test_demo_seed_never_overrides_a_loaded_prescription(core):
    core.handle_prescription(rx(9))
    assert not core.seed_demo_prescription()
    assert core.version == 9
