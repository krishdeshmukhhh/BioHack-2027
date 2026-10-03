"""MQTT ingest: validation, storage, availability, and the append-only audit table."""

import sqlite3

import pytest

from hub.app import protocol
from hub.tests.helpers import PUMP, example, send


def test_status_is_stored_with_received_at(hub, client):
    send(hub, "status", example("status.running"))
    body = client.get(f"/api/pumps/{PUMP}/status").json()
    assert body["state"] == "running"
    assert body["delivered_ml"] == 142.5
    assert body["online"] is True
    assert body["received_at"].endswith("Z")
    assert body["simulated"] is True


def test_status_before_any_data(client):
    body = client.get(f"/api/pumps/{PUMP}/status").json()
    assert body == {"pump_id": PUMP, "online": False, "received_at": None}


def test_unknown_pump_is_404(client):
    response = client.get("/api/pumps/pump-nope/status")
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_pump"


@pytest.mark.parametrize(
    "kind, payload",
    [
        ("status", "not json"),
        ("status", '{"pump_id": "pump-001"}'),
        ("event", '{"pump_id": "pump-001", "uptime_ms": 1, "type": "exploded", "simulated": true}'),
    ],
)
def test_invalid_messages_are_dropped(hub, kind, payload):
    send(hub, kind, payload)
    assert hub.conn.execute("SELECT COUNT(*) FROM status_samples").fetchone()[0] == 0
    assert hub.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_pump_id_must_match_topic(hub):
    send(hub, "status", example("status.running", pump_id="pump-002"))
    assert hub.conn.execute("SELECT COUNT(*) FROM status_samples").fetchone()[0] == 0


def test_unknown_pump_messages_are_ignored(hub):
    hub.handle_message("pump/pump-zzz/status", b"{}")
    assert hub.availability == {}


@pytest.mark.parametrize("name", ["event.alarm", "event.applied", "event.rejected", "event.state"])
def test_every_event_example_is_stored(hub, name):
    send(hub, "event", example(name))
    assert hub.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_availability_offline_then_online(hub):
    send(hub, "status", example("status.running"))
    send(hub, "availability", "offline")
    assert hub.availability_of(PUMP)["online"] is False
    assert hub.availability_of(PUMP)["last_seen_at"] is not None
    send(hub, "availability", "online")
    assert hub.availability_of(PUMP)["online"] is True


def test_audit_update_and_delete_raise(hub):
    hub.conn.execute(
        "INSERT INTO audit (at, actor, actor_role, entity, entity_id, action)"
        " VALUES ('t', 'x', 'hub', 'prescription', 'p/1', 'test')"
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        hub.conn.execute("UPDATE audit SET action = 'changed'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        hub.conn.execute("DELETE FROM audit")


def test_format_checker_rejects_bad_timestamps():
    bad = example("prescription", confirmed_at="yesterday")
    assert protocol.errors("prescription", bad)
