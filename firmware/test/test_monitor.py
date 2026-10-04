"""Check display filtering preserves serial control and handles actual framing."""

import json

import pytest

# The filter runs inside PlatformIO; skip where it is not installed in this venv.
pytest.importorskip("platformio")
from platformio.device.monitor.filters.base import load_monitor_filter  # noqa: E402
from serial.tools import miniterm  # noqa: E402

from firmware.monitor.filter_pump_view import PumpView  # noqa: E402
from firmware.test.test_bench import status  # noqa: E402


def monitor():
    view = PumpView({"environment": "esp32dev"})
    view.color = False
    return view


def test_fragmented_status_formats_progress_only_after_full_line():
    view = monitor()
    raw = json.dumps(status(state="running", delivered_ml=25, target_ml=100, rate_ml_hr=90))
    assert view.rx(raw[:30]) == ""
    text = view.rx(raw[30:] + "\r\n")
    assert "SIMULATED DELIVERY | pump-001" in text
    assert "RUNNING  |  Rate 90.0 mL/hr" in text
    assert "[======>-----------------]  25.0%" in text
    assert "25.00 / 100.00 mL" in text
    assert '"delivered_ml"' not in text


def test_alarm_pending_and_historical_rejection_remain_prominent():
    value = status(state="alarm", alarm="occlusion", rate_ml_hr=0, pending_version=8)
    value.update(last_rejected_version=9, last_reject_reason="rate_out_of_range")
    text = monitor().rx(json.dumps(value) + "\n")
    assert "ALARM: OCCLUSION -- delivery stopped" in text
    assert "PENDING: v8" in text
    assert "LAST REJECTION: v9 -- rate_out_of_range" in text


def test_events_and_diagnostics_in_a_single_chunk_are_not_lost():
    event = {"pump_id": "pump-001", "uptime_ms": 10, "simulated": True,
             "type": "alarm_cleared", "alarm": "occlusion"}
    text = monitor().rx(json.dumps(event) + "\nCommand unavailable in current state.\n")
    assert "[SIMULATED] ALARM CLEARED: OCCLUSION -- paused; use resume to continue" in text
    assert "Command unavailable in current state.\n" in text


@pytest.mark.parametrize("line", [
    "boot message", '{"unknown":true}', "{bad json}",
    json.dumps(status(simulated=False)), json.dumps(status(rate_ml_hr="invalid")),
    json.dumps(status(alarm={"invalid": True})),
    json.dumps({"pump_id": "pump-001", "uptime_ms": 10, "simulated": True,
                "type": "state_changed", "from_state": None, "to_state": "running"}),
])
def test_unknown_and_invalid_messages_pass_through(line):
    assert monitor().rx(line + "\n") == line + "\n"


def test_colors_can_be_enabled_without_changing_command_transmission():
    view = monitor()
    view.color = True
    text = view.rx(json.dumps(status(state="running")) + "\n")
    assert "\033[1;32mRUNNING\033[0m" in text
    for command in ("start\n", "occlusion\n", "clear\n", "resume\n", "stop\n"):
        assert view.tx(command) == command


def test_zero_target_and_excess_volume_render_bounded_bars():
    text = monitor().rx(json.dumps(status(target_ml=0)) + "\n")
    assert "[------------------------]   0.0%" in text
    text = monitor().rx(json.dumps(status(delivered_ml=110, target_ml=100)) + "\n")
    assert "[========================] 100.0%" in text


def test_platformio_discovers_filter_from_project_monitor_directory():
    assert load_monitor_filter("firmware/monitor/filter_pump_view.py",
                               options={"environment": "esp32dev"})
    view = miniterm.TRANSFORMATIONS["pump_view"]()
    assert view.NAME == "pump_view"
    assert "SIMULATED DELIVERY" in view.rx(json.dumps(status()) + "\n")
