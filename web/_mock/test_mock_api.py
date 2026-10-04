"""The mock must match docs/API.md and keep the same safety rules as the hub.

Runs a real mock server on a free port, with real simulated pumps behind it.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).parent))
from mock_api import make_server  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
STATUS_SCHEMA = json.loads((ROOT / "shared" / "protocol" / "status.schema.json").read_text())
HUB_ADDED = {"online", "received_at"}


@pytest.fixture(scope="module")
def base():
    server, hub = make_server(0, speed=600.0, host="127.0.0.1")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    wait_until(lambda: get(url, "/api/pumps/pump-001/status")[1]["received_at"])
    yield url
    hub.stop()
    server.shutdown()


def call(base: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def get(base: str, path: str):
    return call(base, "GET", path)


def post(base: str, path: str, body: dict):
    return call(base, "POST", path, body)


def wait_until(fn, timeout: float = 8.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = fn()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError("timed out")


def rx_state(base: str, pump: str, version: int) -> dict:
    _, rows = get(base, f"/api/pumps/{pump}/prescriptions")
    return next(r for r in rows if r["version"] == version)


def wait_for_state(base: str, pump: str, version: int, state: str) -> dict:
    return wait_until(lambda: (r := rx_state(base, pump, version))["state"] == state and r)


def propose(base: str, pump: str, rate: float, volume: float = 500) -> dict:
    status, rx = post(base, f"/api/pumps/{pump}/prescriptions", {
        "mode": "continuous", "rate_ml_hr": rate, "volume_ml": volume,
        "proposed_by": "clin-01",
    })
    assert status == 200, rx
    assert rx["state"] == "proposed"
    return rx


def test_status_is_pump_status_plus_hub_fields(base):
    status, s = get(base, "/api/pumps/pump-001/status")
    assert status == 200
    assert s["online"] is True and s["simulated"] is True
    pump_part = {k: v for k, v in s.items() if k not in HUB_ADDED}
    pump_part["uptime_ms"] = 0  # the hub drops uptime; the schema requires it
    Draft202012Validator(STATUS_SCHEMA).validate(pump_part)


@pytest.mark.parametrize("page_path", ["/", "/family/"])
def test_family_entry_loads_its_styles_and_script(base, page_path):
    class Assets(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "link" and attrs.get("rel") == "stylesheet":
                self.urls.append(attrs["href"])
            elif tag == "script" and "src" in attrs:
                self.urls.append(attrs["src"])

    with urllib.request.urlopen(base + page_path, timeout=5) as response:
        parser = Assets()
        parser.feed(response.read().decode("utf-8"))
    assert len(parser.urls) == 3
    for url in parser.urls:
        absolute = urllib.parse.urljoin(base + page_path, url)
        with urllib.request.urlopen(absolute, timeout=5) as response:
            assert response.status == 200
            assert "json" not in response.headers["Content-Type"]


def test_unknown_pump_is_404(base):
    status, body = get(base, "/api/pumps/nope/status")
    assert status == 404 and body["error"] == "unknown_pump"


def test_confirm_goes_sent_then_active_only_from_the_pump(base):
    rx = propose(base, "pump-001", 90)
    status, body = post(base, f"/api/pumps/pump-001/prescriptions/{rx['version']}/confirm",
                        {"confirmed_by": "care-01"})
    assert status == 200
    assert body["state"] == "sent"  # never active on send (S5)
    assert body["confirmed_role"] == "parent"
    done = wait_for_state(base, "pump-001", rx["version"], "active")
    assert done["resolved_at"]
    # The applied event can arrive before the next 2 s status; the status follows.
    wait_until(lambda: get(base, "/api/pumps/pump-001/status")[1]["prescription_version"]
               == rx["version"])


def test_out_of_range_is_rejected_by_the_pump_not_the_mock(base):
    rx = propose(base, "pump-002", 500)  # accepted at propose: no limit check (FR-2)
    post(base, f"/api/pumps/pump-002/prescriptions/{rx['version']}/confirm",
         {"confirmed_by": "care-02"})
    done = wait_for_state(base, "pump-002", rx["version"], "rejected")
    assert done["reject_reason"] == "rate_out_of_range"


def test_decline_and_double_answer(base):
    rx = propose(base, "pump-003", 80)
    path = f"/api/pumps/pump-003/prescriptions/{rx['version']}"
    status, body = post(base, path + "/decline", {"declined_by": "care-01"})
    assert status == 200 and body["state"] == "rejected" and body["reject_reason"] == "declined"
    status, body = post(base, path + "/confirm", {"confirmed_by": "care-01"})
    assert status == 409 and body["error"] == "not_proposed"


def test_propose_checks_shape_only(base):
    for bad in ({"mode": "fast"}, {"rate_ml_hr": 0}, {"volume_ml": -1}, {"note": "x" * 201},
                {"proposed_by": "care-01"}):
        body = {"mode": "continuous", "rate_ml_hr": 50, "volume_ml": 400,
                "proposed_by": "clin-01", **bad}
        status, err = post(base, "/api/pumps/pump-003/prescriptions", body)
        assert status == 422 and err["error"] == "invalid_input", bad


def test_audit_is_newest_first_and_records_roles(base):
    _, rows = get(base, "/api/pumps/pump-001/audit")
    assert rows == sorted(rows, key=lambda r: -r["id"])
    assert any(r["action"] == "confirmed" and r["actor_role"] == "parent" for r in rows)


def test_patients_and_daily(base):
    _, rows = get(base, "/api/patients")
    assert len(rows) == 3 and all(r["simulated"] for r in rows)
    flagged = [bool(r["exceptions"]) for r in rows]
    assert flagged == sorted(flagged, reverse=True)  # exceptions first
    codes = {c for r in rows for c in r["exceptions"]}
    assert codes <= {"offline", "under_target", "night_alarms", "alarm_active"}
    _, daily = get(base, f"/api/patients/{rows[0]['id']}/daily?days=7")
    assert len(daily) == 7 and all(d["simulated"] for d in daily)


def test_stream_starts_with_snapshot(base):
    req = urllib.request.Request(base + "/api/pumps/pump-001/stream")
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.headers["Content-Type"].startswith("text/event-stream")
        events = []
        while len(events) < 2:
            line = res.readline().decode().strip()
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
    assert events == ["status", "availability"]


def test_pages_are_served(base):
    for path in ("/family/", "/", "/_mock/"):
        with urllib.request.urlopen(base + path, timeout=5) as res:
            assert res.headers["Content-Type"].startswith("text/html")
    with urllib.request.urlopen(base + "/shared/data.js", timeout=5) as res:
        assert "javascript" in res.headers["Content-Type"]
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(base + "/_mock/mock_api.py", timeout=5)


def test_summary_and_profiles(base):
    status, summary = get(base, "/api/patients/pat-02/summary")
    assert status == 200 and summary["days"] == 7 and summary["simulated"] is True
    assert summary["trend"] in ("improving", "steady", "declining")
    assert summary["days_under_target"] >= 3  # pat-02 drifts under target
    status, profiles = get(base, "/api/patients/pat-01/profiles")
    assert status == 200 and len(profiles) == 2 and all(p["simulated"] for p in profiles)
    assert get(base, "/api/patients/nobody/summary")[0] == 404


def test_confirm_below_a_sent_version_is_stale(base):
    older = propose(base, "pump-003", 60)
    newer = propose(base, "pump-003", 70)
    post(base, f"/api/pumps/pump-003/prescriptions/{newer['version']}/confirm",
         {"confirmed_by": "care-01"})
    status, err = post(base, f"/api/pumps/pump-003/prescriptions/{older['version']}/confirm",
                       {"confirmed_by": "care-01"})
    assert status == 409 and err["error"] == "stale_version"
