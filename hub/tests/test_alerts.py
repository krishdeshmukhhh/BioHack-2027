"""Alerts from pump alarms (FR-14, FR-15), the audit endpoint, staleness, and static files."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from hub.app.main import create_app
from hub.tests.helpers import PUMP, example, send


def raised(alarm: str = "occlusion") -> dict:
    return example("event.alarm", type="alarm_raised", alarm=alarm)


def cleared(alarm: str = "occlusion") -> dict:
    return example("event.alarm", type="alarm_cleared", alarm=alarm)


def drain(queue) -> list[tuple[str, dict]]:
    seen = []
    while not queue.empty():
        seen.append(queue.get_nowait())
    return seen


def test_alarm_event_raises_then_clears(hub, client):
    queue = hub.live.subscribe(PUMP)
    send(hub, "event", raised())
    body = client.get(f"/api/pumps/{PUMP}/alerts").json()
    assert len(body) == 1
    assert body[0]["alarm"] == "occlusion" and body[0]["active"] is True
    assert body[0]["raised_at"].endswith("Z") and body[0]["cleared_at"] is None

    send(hub, "event", cleared())
    body = client.get(f"/api/pumps/{PUMP}/alerts").json()
    assert body[0]["active"] is False and body[0]["cleared_at"] is not None

    alerts = [d for e, d in drain(queue) if e == "alert"]
    assert [a["active"] for a in alerts] == [True, False]


def test_status_raises_alert_when_the_event_was_lost(hub, client):
    send(hub, "status", example("status.alarm"))
    body = client.get(f"/api/pumps/{PUMP}/alerts").json()
    assert [(a["alarm"], a["active"]) for a in body] == [("occlusion", True)]


def test_status_without_alarm_clears_open_alert(hub, client):
    send(hub, "event", raised())
    send(hub, "status", example("status.running"))
    body = client.get(f"/api/pumps/{PUMP}/alerts").json()
    assert body[0]["active"] is False


def test_repeated_alarm_status_does_not_duplicate(hub, client):
    send(hub, "event", raised())
    for _ in range(3):
        send(hub, "status", example("status.alarm"))
    assert len(client.get(f"/api/pumps/{PUMP}/alerts").json()) == 1


def test_active_alerts_listed_first(hub, client):
    send(hub, "event", raised("bag_empty"))
    send(hub, "event", cleared("bag_empty"))
    send(hub, "event", raised("occlusion"))
    body = client.get(f"/api/pumps/{PUMP}/alerts").json()
    assert [(a["alarm"], a["active"]) for a in body] == [
        ("occlusion", True), ("bag_empty", False),
    ]  # fmt: skip


def test_alerts_unknown_pump_is_404(client):
    assert client.get("/api/pumps/pump-nope/alerts").status_code == 404


def test_alarms_are_audited(hub, client):
    send(hub, "event", raised())
    send(hub, "event", cleared())
    rows = client.get(f"/api/pumps/{PUMP}/audit").json()
    assert [r["action"] for r in rows] == ["alarm_cleared", "alarm_raised"]
    assert all(r["entity"] == "alarm" and r["actor"] == PUMP for r in rows)


def test_audit_is_newest_first_and_per_pump(hub, client):
    body = {"mode": "continuous", "rate_ml_hr": 90, "volume_ml": 500, "proposed_by": "clin-01"}
    v = client.post(f"/api/pumps/{PUMP}/prescriptions", json=body).json()["version"]
    client.post(f"/api/pumps/{PUMP}/prescriptions/{v}/confirm", json={"confirmed_by": "care-02"})
    client.post("/api/pumps/pump-002/prescriptions", json=body)
    rows = client.get(f"/api/pumps/{PUMP}/audit").json()
    assert [r["action"] for r in rows] == ["sent", "confirmed", "proposed"]
    assert rows[1]["actor"] == "care-02" and rows[1]["actor_role"] == "school_nurse"
    assert set(rows[0]) == {"id", "at", "actor", "actor_role", "entity", "entity_id",
                            "action", "old_value", "new_value"}  # fmt: skip
    assert client.get("/api/pumps/pump-nope/audit").status_code == 404


def test_pump_goes_offline_when_status_is_stale(hub):
    send(hub, "status", example("status.running"))
    queue = hub.live.subscribe(PUMP)
    hub.check_stale(datetime.now(UTC) + timedelta(seconds=5))
    assert hub.is_online(PUMP)
    hub.check_stale(datetime.now(UTC) + timedelta(seconds=11))
    assert not hub.is_online(PUMP)
    assert drain(queue) == [("availability", hub.availability_of(PUMP))]
    send(hub, "status", example("status.running"))
    assert hub.is_online(PUMP)


def test_web_apps_and_shared_files_are_served(hub, tmp_path):
    for folder in ("shared", "family", "clinician"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "index.html").write_text(folder)
    (tmp_path / "shared" / "tokens.css").write_text("css")
    client = TestClient(create_app(hub=hub, web_dir=tmp_path))
    expected = {"/shared/tokens.css": "css", "/family/": "family", "/clinician/": "clinician",
                "/": "family"}  # fmt: skip
    for path, text in expected.items():
        assert client.get(path).text == text, path
    assert client.get("/health").json() == {"status": "ok"}  # API routes still win


def test_duplicate_qos1_events_do_not_double_count(hub, client):
    # topics.md: events are QoS 1 (at least once), so the same event can arrive twice.
    for _ in range(2):
        send(hub, "event", raised())
    for _ in range(2):
        send(hub, "event", cleared())
    body = client.get(f"/api/pumps/{PUMP}/alerts").json()
    assert [(a["alarm"], a["active"]) for a in body] == [("occlusion", False)]
    assert [r["action"] for r in client.get(f"/api/pumps/{PUMP}/audit").json()] == [
        "alarm_cleared", "alarm_raised",
    ]  # fmt: skip


def test_alert_carries_simulated(hub, client):
    send(hub, "event", raised())
    assert client.get(f"/api/pumps/{PUMP}/alerts").json()[0]["simulated"] is True


def test_snapshot_includes_active_alerts_only(hub):
    send(hub, "event", raised("bag_empty"))
    send(hub, "event", cleared("bag_empty"))
    send(hub, "event", raised("occlusion"))
    snap = [d for e, d in hub.snapshot(PUMP) if e == "alert"]
    assert [(a["alarm"], a["active"]) for a in snap] == [("occlusion", True)]


def test_late_duplicate_raise_after_clear_is_ignored(hub, client):
    # Review finding: raise, clear, then a redelivered raise must not reopen the alarm.
    send(hub, "event", raised())
    send(hub, "event", cleared())
    send(hub, "event", raised())
    body = client.get(f"/api/pumps/{PUMP}/alerts").json()
    assert [(a["alarm"], a["active"]) for a in body] == [("occlusion", False)]
    assert hub.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 2


def test_late_duplicate_clear_does_not_hide_a_new_alarm(hub, client):
    # Review finding: an old clear redelivered after a new raise must leave the new alarm open.
    send(hub, "event", raised())
    send(hub, "event", cleared())
    send(hub, "event", raised() | {"uptime_ms": 999000})
    send(hub, "status", example("status.alarm", uptime_ms=999500))
    send(hub, "event", cleared())  # the duplicate
    body = client.get(f"/api/pumps/{PUMP}/alerts").json()
    assert [(a["alarm"], a["active"]) for a in body] == [
        ("occlusion", True), ("occlusion", False),
    ]  # fmt: skip


def test_events_alone_do_not_keep_a_pump_online(hub, monkeypatch):
    # docs/API.md: offline after 10 s with no *status*; an event 8 s later does not count.
    start = datetime.now(UTC)
    send(hub, "status", example("status.running"))
    at = (start + timedelta(seconds=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    monkeypatch.setattr("hub.app.service.utc_now", lambda: at)
    send(hub, "event", example("event.state"))
    hub.check_stale(start + timedelta(seconds=12))
    assert not hub.is_online(PUMP)


def test_retained_online_without_status_goes_offline(hub):
    send(hub, "availability", "online")
    assert hub.is_online(PUMP)
    hub.check_stale(datetime.now(UTC) + timedelta(seconds=11))
    assert not hub.is_online(PUMP)
