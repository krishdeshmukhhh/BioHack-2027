"""Device-only WiFi outage tests with no hardware, HTTP or MQTT connections."""

import pytest

from firmware.test.test_bench import FakeClock, encoded, status
from firmware.test.test_network_bench import FakeApi, FakeObserver, FakePump
from firmware.tools import wifi_bench as wifi


class WifiPump(FakePump):
    def __init__(self, clock, *, profile=True, mode="hub", **initial):
        super().__init__(clock, mode, **initial)
        if profile:
            self.lines.append(wifi.PROFILE_MARKER.encode() + b"\n")
        self.wifi_enabled = True
        self.break_during_outage = None

    def read(self, count):
        if not self.wifi_enabled and self.break_during_outage:
            self.value.update(self.break_during_outage)
        return super().read(count)

    def write(self, raw):
        if raw not in {b"wifi_off\n", b"wifi_on\n"}:
            return super().write(raw)
        self.writes.append(raw)
        self.wifi_enabled = raw == b"wifi_on\n"
        marker = wifi.ON_MARKER if self.wifi_enabled else wifi.OFF_MARKER
        self.lines.append(marker.encode() + b"\n")
        self.observer.messages.append(
            (self.clock(), "availability", b"online" if self.wifi_enabled else b"offline")
        )


class WifiApi(FakeApi):
    def request(self, method, path, payload=None):
        result = super().request(method, path, payload)
        if path.endswith("/status") and not self.pump.wifi_enabled:
            result["online"] = False
        return result


class WifiObserver(FakeObserver):
    def matching(self, topic, since=0):
        if topic == "status" and self.pump.wifi_enabled:
            self.messages.append((self.pump.clock(), "status", encoded(self.pump.value)))
        return super().matching(topic, since)


def helper(**options):
    clock = FakeClock()
    pump = WifiPump(clock, **options)
    api = WifiApi(pump)
    observer = WifiObserver(pump)
    api.items[7] = {
        "pump_id": "pump-001",
        "version": 7,
        "state": "active",
        "rate_ml_hr": 60,
        "volume_ml": 5,
        "confirmed_by": "care-01",
        "confirmed_at": "2026-10-03T12:00:00Z",
    }
    report = {"checks": {name: {"result": "not_run"} for name in wifi.CHECKS}}
    test = wifi.WifiBench(
        pump,
        report,
        api,
        observer,
        clock=clock,
        sleep=lambda seconds: setattr(clock, "now", clock.now + seconds),
    )
    return test, pump, api, observer, report


@pytest.mark.parametrize(
    "options",
    [
        {"profile": False},
        {"mode": "offline"},
        {"simulated": False},
        {"state": "running"},
        {"state": "alarm", "alarm": "occlusion"},
        {"pending_version": 8},
    ],
)
def test_refuses_legacy_profile_or_active_state_before_writes(options):
    test, pump, _, _, _ = helper(**options)
    with pytest.raises(wifi.bench.BenchError):
        test.run()
    test.cleanup()
    assert pump.writes == []


def test_full_wifi_outage_preserves_settings_and_reports_real_windows():
    test, pump, api, _, report = helper()
    test.run()
    assert all(check["result"] == "pass" for check in report["checks"].values())
    assert report["outage_window"]["device_elapsed_ms"] >= 30000
    assert (
        report["outage_window"]["end_delivered_ml"] > report["outage_window"]["start_delivered_ml"]
    )
    assert pump.value["state"] == "idle"
    assert pump.wifi_enabled
    assert pump.writes == [b"start\n", b"wifi_off\n", b"wifi_on\n", b"stop\n"]
    assert all(method == "GET" for method, _, _ in api.calls)


@pytest.mark.parametrize(
    "change",
    [
        {"prescription_version": 8},
        {"rate_ml_hr": 75},
        {"last_rejected_version": 7, "last_reject_reason": "stale_version"},
    ],
)
def test_changed_feed_fails_and_restores_network_without_false_pass(change):
    test, pump, _, _, report = helper()
    pump.break_during_outage = change
    with pytest.raises(wifi.bench.BenchError, match="changed"):
        test.run()
    assert report["checks"]["delivery_during_wifi_loss"]["result"] == "not_run"
    test.cleanup()
    assert pump.wifi_enabled
    assert b"wifi_on\n" in pump.writes
    assert "not verified" in report["network_cleanup"]


def test_alarm_failure_restores_network_and_preserves_alarm():
    test, pump, _, _, report = helper()
    pump.break_during_outage = {"state": "alarm", "alarm": "occlusion", "rate_ml_hr": 0}
    with pytest.raises(wifi.bench.BenchError):
        test.run()
    test.cleanup()
    assert pump.wifi_enabled
    assert b"clear\n" not in pump.writes
    assert b"stop\n" not in pump.writes
    assert pump.value["state"] == "alarm"
    assert "preserved" in report["cleanup"]


def test_initial_unconfirmed_settings_do_not_start_feed():
    test, pump, api, _, _ = helper()
    api.items[7]["confirmed_by"] = None
    with pytest.raises(wifi.bench.BenchError, match="confirmation"):
        test.run()
    assert pump.writes == []


def test_frozen_volume_during_wifi_loss_is_detected():
    baseline = status(state="running", delivered_ml=1)
    with pytest.raises(wifi.bench.BenchError, match="did not advance"):
        wifi.WifiBench.stable_feed(baseline, baseline, advance_from=baseline)


def test_successful_wifi_off_write_with_flush_failure_still_restores_network():
    test, pump, _, _, report = helper()
    test.mode = "hub"
    test.profile_seen = True
    test.authorized = True
    test.last_status = status()

    def fail_first_flush():
        pump.flush = lambda: None
        raise OSError("USB flush failed after command delivery")

    pump.flush = fail_first_flush
    with pytest.raises(OSError):
        test.send("wifi_off")
    assert not pump.wifi_enabled
    assert test.disabled_by_helper
    test.cleanup()
    assert pump.wifi_enabled
    assert pump.writes == [b"wifi_off\n", b"wifi_on\n"]
    assert "not verified" in report["network_cleanup"]


def test_start_flush_failure_retains_feed_ownership_for_safe_stop():
    test, pump, _, _, _ = helper()
    test.mode = "hub"
    test.profile_seen = True
    test.authorized = True
    test.last_status = status()

    def fail_first_flush():
        pump.flush = lambda: None
        raise OSError("USB flush failed after start")

    pump.flush = fail_first_flush
    with pytest.raises(OSError):
        test.send("start")
    test.cleanup()
    assert pump.writes == [b"start\n", b"stop\n"]
    assert pump.value["state"] == "idle"
