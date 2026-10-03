"""Scripted scenario tests: no broker, fake publisher (schema-checked), fake clock."""

from __future__ import annotations

import subprocess
import sys
import threading

import pytest

from sim.pump_sim import MqttLink, PumpCore, handle_key, parse_args, prepare_core
from sim.scenarios import (
    SCENARIOS,
    NoPrescriptionError,
    Scenario,
    ScenarioRunner,
    Step,
)
from sim.test_pump_sim import FakeClock, FakePublisher, rx
from sim.test_pump_sim_mqtt import OK, ROOT, FakeClient

TICK = 0.1  # real seconds per main-loop tick, as in main()


def seeded(speed: float, link: bool = False):
    clock = FakeClock()
    pub = FakePublisher()
    box: list[MqttLink] = []
    client = FakeClient() if link else None

    def publish(topic, payload):
        pub(topic, payload)  # schema-checks everything the core sends
        if box:
            box[0].publish(topic, payload)

    core = PumpCore("pump-001", publish=publish, clock=clock, speed=speed)
    assert core.seed_demo_prescription()
    mlink = None
    if link:
        mlink = MqttLink(core, "localhost", 1883, client=client)
        box.append(mlink)
        mlink.start()
        mlink.on_connect(client, None, {}, OK, None)
    return core, mlink, client, clock, pub


def drive(core, runner, clock, real_s, trace=None):
    end = clock.t + real_s
    while clock.t < end - 1e-9:
        clock.t += TICK
        core.tick()
        runner.tick()
        if trace is not None:
            trace.append(round(core.delivered_ml, 6))


def run_until_done(core, runner, clock, limit_s=600, trace=None):
    for _ in range(int(limit_s / TICK)):
        if runner.done:
            return
        drive(core, runner, clock, TICK, trace)
    raise AssertionError(f"scenario did not finish in {limit_s} real s")


def event_seq(pub) -> list[str]:
    out = []
    for e in pub.events():
        if e["type"] == "state_changed":
            out.append(f"{e['from_state']}->{e['to_state']}")
        elif e["type"] in ("alarm_raised", "alarm_cleared"):
            out.append(f"{e['type']}:{e['alarm']}")
        else:
            out.append(e["type"])
    return out


def fault_cycle(alarm: str) -> list[str]:
    return [
        f"alarm_raised:{alarm}", "running->alarm",
        f"alarm_cleared:{alarm}", "alarm->paused", "paused->running",
    ]


# ---- timing ------------------------------------------------------------

def test_sim_steps_scale_with_speed_and_real_steps_do_not():
    core, _, _, clock, _ = seeded(speed=60)
    scenario = Scenario("t", "timing", 60, (
        Step(3, "start", real=True),
        Step(600, "occlusion"),  # 600 sim s = 10 real s at x60
        Step(10, "clear", real=True),
        Step(3, "pause_resume", real=True),
    ))
    t0 = clock.t
    runner = ScenarioRunner(scenario, core, out=lambda _: None)
    fired_at: list[float] = []
    while not runner.done:
        n = len(runner.fired)
        drive(core, runner, clock, TICK)
        if len(runner.fired) > n:
            fired_at.append(clock.t - t0)
    assert fired_at == pytest.approx([3, 13, 23, 26], abs=TICK + 1e-6)
    assert [a for _, a, _ in runner.fired] == ["start", "occlusion", "clear", "pause_resume"]
    assert all(ok for *_, ok in runner.fired)
    # printed t is SIM seconds since the scenario started
    assert [t for t, *_ in runner.fired] == pytest.approx([180, 780, 1380, 1560], abs=60 * TICK)


def test_same_scenario_takes_less_real_time_at_higher_speed():
    real = {}
    for speed in (1, 10):
        core, _, _, clock, _ = seeded(speed=speed)
        runner = ScenarioRunner(SCENARIOS["occlusion"], core, out=lambda _: None)
        t0 = clock.t
        run_until_done(core, runner, clock, limit_s=1000)
        real[speed] = clock.t - t0
    # 600 sim s of feed before the occlusion shrinks to 60 s; 16 real s of lead-in
    # and human steps do not shrink.
    assert real[1] == pytest.approx(616, abs=0.5)
    assert real[10] == pytest.approx(76, abs=0.5)


def test_printed_lines():
    core, _, _, clock, _ = seeded(speed=60)
    lines: list[str] = []
    runner = ScenarioRunner(SCENARIOS["occlusion"], core, out=lines.append)
    run_until_done(core, runner, clock)
    fired = [ln for ln in lines if "t=" in ln]
    assert len(fired) == 4
    assert fired[1].startswith("[scenario] t=") and " occlusion " in fired[1]
    assert lines[-1].startswith("[scenario] occlusion done")


# ---- each scenario's event sequence -------------------------------------

@pytest.mark.parametrize("name,alarm", [("occlusion", "occlusion"), ("bag_empty", "bag_empty")])
def test_fault_scenarios_drive_expected_events(name, alarm):
    core, _, _, clock, pub = seeded(speed=60)
    runner = ScenarioRunner(SCENARIOS[name], core, out=lambda _: None)
    run_until_done(core, runner, clock)
    assert event_seq(pub) == ["idle->priming", "priming->running", *fault_cycle(alarm)]
    assert core.state == "running" and core.alarm is None
    assert core.delivered_ml > 0
    # the alarm reached telemetry (status is real-time; the alarm lasts 10 real s)
    assert any(s["alarm"] == alarm and s["state"] == "alarm" for s in pub.statuses())
    assert core.version == 7  # a scenario never changes the prescription


def test_overnight_two_occlusions_then_complete():
    core, _, _, clock, pub = seeded(speed=600)
    runner = ScenarioRunner(SCENARIOS["overnight"], core, out=lambda _: None)
    run_until_done(core, runner, clock, limit_s=300)
    assert event_seq(pub) == [
        "idle->priming", "priming->running",
        *fault_cycle("occlusion"), *fault_cycle("occlusion"),
        "running->complete",
    ]
    assert core.delivered_ml == pytest.approx(500)
    assert all(ok for *_, ok in runner.fired)
    drive(core, runner, clock, 1)  # 5 sim s hold, then idle on its own
    assert core.state == "idle"


def test_overnight_fits_a_rehearsal_at_suggested_speed():
    scenario = SCENARIOS["overnight"]
    core, _, _, clock, _ = seeded(speed=scenario.suggested_speed)
    runner = ScenarioRunner(scenario, core, out=lambda _: None)
    t0 = clock.t
    run_until_done(core, runner, clock, limit_s=300)
    assert clock.t - t0 < 120  # 500 mL at 60 mL/hr in under two real minutes


def test_wifi_drop_publishes_nothing_while_down_then_reconnects():
    core, link, client, clock, pub = seeded(speed=60, link=True)
    runner = ScenarioRunner(SCENARIOS["wifi_drop"], core, link, out=lambda _: None)
    while not link.dropped:
        drive(core, runner, clock, TICK)
    assert client.sock.closed and ("disconnect",) not in client.calls  # Will fires
    client.published.clear()
    d0 = core.delivered_ml
    drive(core, runner, clock, 29.5)
    assert client.published == []
    assert core.state == "running"  # S6
    assert core.delivered_ml - d0 == pytest.approx(60 * 29.5 * 60 / 3600, abs=0.2)
    run_until_done(core, runner, clock)
    assert not link.dropped and client.loop_running
    assert all(ok for *_, ok in runner.fired)
    link.on_connect(client, None, {}, OK, None)  # paho reconnects in its own thread
    drive(core, runner, clock, 2)
    st = [p for t, p, *_ in client.published if t.endswith("/status")]
    assert st, "status resumes after reconnect"
    assert ("pump/pump-001/availability", "online", 1, True) in client.published
    assert event_seq(pub) == ["idle->priming", "priming->running"]


def test_wifi_drop_delivery_identical_to_no_drop_run():
    traces = []
    for with_link in (True, False):
        core, link, _, clock, _ = seeded(speed=60, link=with_link)
        runner = ScenarioRunner(SCENARIOS["wifi_drop"], core, link, out=lambda _: None)
        trace: list[float] = []
        run_until_done(core, runner, clock, trace=trace)
        drive(core, runner, clock, 10, trace)
        traces.append((trace, core.state))
        if not with_link:  # no link: drop and restore are reported as ignored
            assert [ok for _, a, ok in runner.fired if "wifi" in a] == [False, False]
    assert traces[0] == traces[1]
    assert traces[0][0][-1] > 0


# ---- guard rails ---------------------------------------------------------

def test_refuses_without_prescription():
    core = PumpCore("pump-001", publish=FakePublisher(), clock=FakeClock())
    with pytest.raises(NoPrescriptionError, match="--demo-seed"):
        ScenarioRunner(SCENARIOS["occlusion"], core, out=lambda _: None)


def test_cli_refuses_scenario_without_prescription(tmp_path):
    out = subprocess.run(
        [sys.executable, "-m", "sim.pump_sim", "--scenario", "occlusion",
         "--state-file", str(tmp_path / "none.json")],
        cwd=ROOT, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
    )
    assert out.returncode == 2
    assert "needs a prescription" in out.stderr


def test_cli_lists_scenarios():
    out = subprocess.run(
        [sys.executable, "-m", "sim.pump_sim", "--list-scenarios"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0
    for name in ("occlusion", "bag_empty", "wifi_drop", "overnight"):
        assert name in out.stdout


def test_step_rejects_unknown_action():
    with pytest.raises(ValueError):
        Step(1, "set_rate")


def test_ignored_step_is_reported_not_forced():
    """--demo-feed already started the feed, so the scripted start is ignored."""
    core, _, _, clock, _ = seeded(speed=60)
    core.start()
    lines: list[str] = []
    runner = ScenarioRunner(SCENARIOS["occlusion"], core, out=lines.append)
    run_until_done(core, runner, clock)
    assert runner.fired[0][1:] == ("start", False)
    assert any("ignored, pump state is" in ln for ln in lines)
    assert core.state == "running"


def test_keyboard_stays_live_during_scenario():
    core, _, _, clock, pub = seeded(speed=60)
    runner = ScenarioRunner(SCENARIOS["occlusion"], core, out=lambda _: None)
    drive(core, runner, clock, 5)
    assert core.state == "running"
    handle_key("p", core, None, threading.Event())  # caregiver pauses by hand
    run_until_done(core, runner, clock)
    # occlusion from paused is allowed; clear goes to paused, the scripted
    # resume then runs again
    assert event_seq(pub)[2:] == [
        "running->paused", "alarm_raised:occlusion", "paused->alarm",
        "alarm_cleared:occlusion", "alarm->paused", "paused->running",
    ]


def test_prescription_still_validated_during_scenario():
    """A scenario adds no path around handle_prescription: mid-feed it queues (S4)."""
    core, _, _, clock, pub = seeded(speed=60)
    runner = ScenarioRunner(SCENARIOS["occlusion"], core, out=lambda _: None)
    drive(core, runner, clock, 5)
    assert core.handle_prescription(rx(8, pump_id="pump-001")) == "queued"
    assert core.handle_prescription(rx(9, rate_ml_hr=999)) == "rate_out_of_range"
    run_until_done(core, runner, clock)
    assert core.version == 7 and core.pending_version == 8


# ---- --demo-seed -----------------------------------------------------------

def test_demo_seed_leaves_pump_idle_with_v7(tmp_path):
    args = parse_args(["--demo-seed", "--pump-id", "pump-001",
                       "--state-file", str(tmp_path / "none.json")])
    pub, clock = FakePublisher(), FakeClock()
    core = prepare_core(args, pub, clock)
    assert core.state == "idle" and core.version == 7
    assert pub.messages == []  # loaded like NVS: no events
    core.tick()
    (st,) = pub.statuses()
    assert st["state"] == "idle" and st["prescription_version"] == 7
    assert st["rate_ml_hr"] == 60 and st["delivered_ml"] == 0


def test_demo_feed_still_starts_a_feed(tmp_path):
    args = parse_args(["--demo-feed", "--pump-id", "pump-001",
                       "--state-file", str(tmp_path / "none.json")])
    core = prepare_core(args, FakePublisher(), FakeClock())
    assert core.state == "priming" and core.version == 7


def test_demo_seed_does_not_override_state_file(tmp_path):
    path = tmp_path / "state.json"
    first = PumpCore("pump-001", publish=FakePublisher(), clock=FakeClock(), state_file=path)
    assert first.handle_prescription(rx(9)) == "applied"
    args = parse_args(["--demo-seed", "--pump-id", "pump-001", "--state-file", str(path)])
    assert prepare_core(args, FakePublisher(), FakeClock()).version == 9


def test_demo_seed_and_demo_feed_are_exclusive():
    with pytest.raises(SystemExit):
        parse_args(["--demo-seed", "--demo-feed"])
