"""Patients and exceptions (FR-19), daily totals (FR-20), weekly facts (FR-21), profiles."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from hub.app import reports
from hub.tests.helpers import PUMP, example, send
from sim import generate_history

TODAY = datetime.now(UTC).date()


def day(patient: str, d: date, delivered: float, prescribed: float = 900.0) -> dict:
    return {"patient_id": patient, "pump_id": "x", "date": d.isoformat(),
            "delivered_ml": delivered, "prescribed_ml": prescribed, "alarm_count": 0,
            "simulated": True}  # fmt: skip


def alarm(patient: str, at: datetime, code: str = "occlusion") -> dict:
    return {"patient_id": patient, "pump_id": "x", "alarm": code,
            "raised_at": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "cleared_at": None,
            "simulated": True}  # fmt: skip


def history(daily: list[dict], alarms: list[dict] | None = None) -> dict:
    return {"simulated": True, "seed": 1, "generated_for_end_date": TODAY.isoformat(),
            "patients": [], "daily": daily, "alarms": alarms or []}  # fmt: skip


def last_night(hour: int) -> datetime:
    start, _ = reports.night_window(datetime.now(UTC))
    base = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    return base + timedelta(hours=(hour - 22) % 24)


def by_id(client) -> dict[str, dict]:
    return {p["id"]: p for p in client.get("/api/patients").json()}


def test_generated_history_loads_and_flags_the_right_patients(hub, client, tmp_path):
    path = tmp_path / "history.json"
    generate_history.write(generate_history.generate(end_date=TODAY), path)
    assert reports.load_history(hub.conn, path)
    send(hub, "status", example("status.running"))
    patients = by_id(client)
    assert patients["pat-01"]["exceptions"] == []
    assert "under_target" in patients["pat-02"]["exceptions"]
    assert patients["pat-01"]["online"] is True
    assert all(p["simulated"] is True for p in patients.values())


def test_missing_history_file_is_not_an_error(hub, tmp_path):
    assert reports.load_history(hub.conn, tmp_path / "nope.json") is False


def test_history_must_be_labelled_simulated(hub):
    with pytest.raises(ValueError):
        reports.load_history_data(hub.conn, {**history([]), "simulated": False})


def test_offline_until_a_status_arrives(client, hub):
    assert by_id(client)["pat-01"]["exceptions"] == ["offline"]
    send(hub, "status", example("status.running"))
    assert by_id(client)["pat-01"]["exceptions"] == []
    send(hub, "availability", "offline")
    assert by_id(client)["pat-01"]["exceptions"] == ["offline"]


def test_exceptions_first(client, hub):
    send(hub, "status", example("status.running"))
    ids = [p["id"] for p in client.get("/api/patients").json()]
    assert ids[-1] == "pat-01"  # the only online patient with no exceptions


def test_under_target_needs_three_days_in_a_row(hub):
    days = [TODAY - timedelta(days=i) for i in range(4)]
    reports.load_history_data(hub.conn, history([
        day("pat-01", days[3], 800), day("pat-01", days[2], 900),  # one good day
        day("pat-01", days[1], 800), day("pat-01", days[0], 800),
    ]))  # fmt: skip
    assert not reports.under_target(hub.conn, "pat-01")
    reports.load_history_data(hub.conn, history([
        day("pat-01", d, 800) for d in days[:3]
    ]))  # fmt: skip
    assert reports.under_target(hub.conn, "pat-01")


def test_night_alarms_more_than_two_last_night(hub, client):
    send(hub, "status", example("status.running"))
    reports.load_history_data(hub.conn, history([], [
        alarm("pat-01", last_night(23)), alarm("pat-01", last_night(2)),
    ]))  # fmt: skip
    assert "night_alarms" not in by_id(client)["pat-01"]["exceptions"]
    reports.load_history_data(hub.conn, history([], [
        alarm("pat-01", last_night(23)), alarm("pat-01", last_night(2)),
        alarm("pat-01", last_night(5)),
    ]))  # fmt: skip
    assert "night_alarms" in by_id(client)["pat-01"]["exceptions"]


def test_night_alarms_outside_the_window_do_not_count(hub):
    reports.load_history_data(hub.conn, history([], [
        alarm("pat-01", last_night(12)) for _ in range(5)
    ]))  # fmt: skip
    assert reports.night_alarm_count(hub.conn, "pat-01", PUMP, datetime.now(UTC)) == 0


def test_night_window():
    assert reports.night_window(datetime(2026, 10, 3, 12, tzinfo=UTC)) == (
        "2026-10-02T22:00:00Z", "2026-10-03T06:00:00Z")  # fmt: skip
    assert reports.night_window(datetime(2026, 10, 3, 23, tzinfo=UTC)) == (
        "2026-10-03T22:00:00Z", "2026-10-04T06:00:00Z")  # fmt: skip
    assert reports.night_window(datetime(2026, 10, 3, 3, tzinfo=UTC))[0] == "2026-10-02T22:00:00Z"


def test_daily_is_oldest_first_and_limited(hub, client):
    rows = [day("pat-01", TODAY - timedelta(days=i), 850) for i in range(10)]
    reports.load_history_data(hub.conn, history(rows))
    body = client.get("/api/patients/pat-01/daily?days=3").json()
    assert [r["date"] for r in body] == [
        (TODAY - timedelta(days=i)).isoformat() for i in (2, 1, 0)
    ]
    assert set(body[0]) == {"date", "delivered_ml", "prescribed_ml", "alarm_count", "simulated"}
    assert body[0]["simulated"] is True
    assert len(client.get("/api/patients/pat-01/daily").json()) == 10


def test_daily_errors(client):
    assert client.get("/api/patients/pat-99/daily").json()["error"] == "unknown_patient"
    assert client.get("/api/patients/pat-01/daily?days=0").status_code == 422


def test_weekly_summary(hub, client):
    rows = [day("pat-01", TODAY - timedelta(days=i), 900) for i in range(7, 14)]
    rows += [day("pat-01", TODAY - timedelta(days=i), 720) for i in range(7)]
    when = datetime.combine(TODAY, datetime.min.time(), UTC)
    reports.load_history_data(hub.conn, history(rows, [
        alarm("pat-01", when, "occlusion"), alarm("pat-01", when, "occlusion"),
        alarm("pat-01", when, "bag_empty"),
        alarm("pat-01", when - timedelta(days=10), "low_battery"),  # prior week
    ]))  # fmt: skip
    body = client.get("/api/patients/pat-01/summary").json()
    assert body["days"] == 7 and body["to_date"] == TODAY.isoformat()
    assert body["delivered_pct"] == 80.0 and body["prior_week_delivered_pct"] == 100.0
    assert body["trend"] == "declining"
    assert body["days_under_target"] == 7
    assert body["alarms_by_code"] == {"occlusion": 2, "bag_empty": 1}
    assert body["simulated"] is True


def test_weekly_summary_without_history(client):
    body = client.get("/api/patients/pat-01/summary").json()
    assert body["days"] == 0 and body["delivered_pct"] is None and body["trend"] is None
    assert client.get("/api/patients/pat-99/summary").status_code == 404


def test_profiles(client):
    body = client.get("/api/patients/pat-01/profiles").json()
    assert body and all(p["patient_id"] == "pat-01" and p["simulated"] for p in body)
    assert {"name", "mode", "rate_ml_hr", "volume_ml"} <= set(body[0])
    assert client.get("/api/patients/pat-99/profiles").status_code == 404


def test_history_file_shape_matches_the_contract_example(tmp_path):
    path = tmp_path / "h.json"
    generate_history.write(generate_history.generate(end_date=TODAY), path)
    data = json.loads(path.read_text())
    assert {"simulated", "patients", "daily", "alarms"} <= set(data)
