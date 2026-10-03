"""The remote programming loop: propose, confirm, publish gate, and pump-driven lifecycle."""

import pytest

from hub.app import prescriptions, protocol
from hub.app.mqtt_bridge import CONNECTED
from hub.app.prescriptions import PublishRefused
from hub.tests.helpers import PUMP, confirm, example, propose, send


def state(hub, version: int) -> str:
    return prescriptions.get(hub.conn, PUMP, version)["state"]


def applied(version: int) -> dict:
    return example("event.applied", version=version)


# --- propose ---


def test_propose_gets_next_version_above_what_the_pump_reports(hub, client):
    send(hub, "status", example("status.running"))  # pump has v7, pending v8
    p = propose(client)
    assert p["version"] == 9
    assert p["state"] == "proposed"
    assert propose(client)["version"] == 10


def test_propose_has_no_limit_check(client):
    # S1 lives in the pump; the demo needs the pump to be the one that refuses.
    assert propose(client, rate=500)["state"] == "proposed"


@pytest.mark.parametrize(
    "body",
    [
        {"mode": "continuous", "rate_ml_hr": 0, "volume_ml": 500, "proposed_by": "clin-01"},
        {"mode": "drip", "rate_ml_hr": 90, "volume_ml": 500, "proposed_by": "clin-01"},
        {"mode": "continuous", "rate_ml_hr": 90, "proposed_by": "clin-01"},
        {"mode": "continuous", "rate_ml_hr": 90, "volume_ml": 500, "proposed_by": "care-01"},
    ],
)
def test_propose_rejects_bad_shape(client, body):
    response = client.post(f"/api/pumps/{PUMP}/prescriptions", json=body)
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_input"


# --- confirm and the publish gate (S2) ---


def test_confirm_publishes_retained_qos1_and_is_sent_not_active(client, hub, publisher):
    v = propose(client)["version"]
    response = confirm(client, v)
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "sent"  # never active on send (S5)
    assert body["confirmed_role"] == "parent"
    [(topic, message, qos, retain)] = publisher.sent
    assert (topic, qos, retain) == (f"pump/{PUMP}/prescription", 1, True)
    assert message["confirmed_by"] == "care-01"
    assert protocol.errors("prescription", message) == []


def test_unconfirmed_is_never_published(client, hub, publisher):
    v = propose(client)["version"]
    with pytest.raises(PublishRefused):
        prescriptions.publish_prescription(hub.conn, publisher, PUMP, v)
    assert publisher.sent == []


def test_gate_refuses_confirmed_state_without_a_stored_confirmation(client, hub, publisher):
    v = propose(client)["version"]
    hub.conn.execute("UPDATE prescriptions SET state = 'confirmed' WHERE version = ?", (v,))
    with pytest.raises(PublishRefused, match="no caregiver confirmation"):
        prescriptions.publish_prescription(hub.conn, publisher, PUMP, v)
    assert publisher.sent == []


def test_clinician_cannot_confirm(client, publisher):
    v = propose(client)["version"]
    response = confirm(client, v, by="clin-01")
    assert response.status_code == 422
    assert publisher.sent == []


def test_confirm_twice_is_409(client):
    v = propose(client)["version"]
    confirm(client, v)
    response = confirm(client, v)
    assert response.status_code == 409
    assert response.json()["error"] == "not_proposed"


def test_confirm_unknown_version_is_404(client):
    assert confirm(client, 99).status_code == 404


def test_failed_publish_leaves_it_confirmed_then_reconnect_sends_it(client, hub, publisher):
    publisher.fail = True
    v = propose(client)["version"]
    assert confirm(client, v).json()["state"] == "confirmed"
    publisher.fail = False
    hub.handle_message(CONNECTED, b"")
    assert state(hub, v) == "sent"
    assert len(publisher.sent) == 1


def test_decline_rejects_and_publishes_nothing(client, hub, publisher):
    v = propose(client)["version"]
    response = client.post(
        f"/api/pumps/{PUMP}/prescriptions/{v}/decline", json={"declined_by": "care-02"}
    )
    assert response.json()["state"] == "rejected"
    assert response.json()["reject_reason"] == "declined"
    assert publisher.sent == []
    assert confirm(client, v).status_code == 409


# --- lifecycle from pump data only (S5) ---


def test_active_only_after_pump_applied_event(client, hub):
    v = propose(client)["version"]
    confirm(client, v)
    assert state(hub, v) == "sent"
    send(hub, "event", applied(v))
    assert state(hub, v) == "active"


def test_active_from_status_alone(client, hub):
    v = propose(client)["version"]
    confirm(client, v)
    send(hub, "status", example("status.running", prescription_version=v, pending_version=None))
    assert state(hub, v) == "active"


def test_out_of_range_is_rejected_by_the_pump(client, hub):
    v = propose(client, rate=500)["version"]
    confirm(client, v)
    send(hub, "event", example("event.rejected", version=v, reason="rate_out_of_range"))
    p = prescriptions.get(hub.conn, PUMP, v)
    assert (p["state"], p["reject_reason"]) == ("rejected", "rate_out_of_range")


def test_events_cannot_change_a_proposed_prescription(client, hub):
    v = propose(client)["version"]
    send(hub, "event", applied(v))
    send(hub, "event", example("event.rejected", version=v))
    assert state(hub, v) == "proposed"


def test_stale_rejection_does_not_undo_active(client, hub):
    v = propose(client)["version"]
    confirm(client, v)
    send(hub, "event", applied(v))
    send(hub, "event", example("event.rejected", version=v, reason="stale_version"))
    assert state(hub, v) == "active"


def test_newer_active_supersedes_older(client, hub):
    v1 = propose(client)["version"]
    confirm(client, v1)
    send(hub, "event", applied(v1))
    v2 = propose(client)["version"]
    confirm(client, v2)
    send(hub, "event", applied(v2))
    assert (state(hub, v1), state(hub, v2)) == ("superseded", "active")


def test_pending_newer_supersedes_older_in_flight(client, hub):
    # R6: v1 sent but not applied, v2 sent and the pump reports v2 pending.
    v1 = propose(client)["version"]
    confirm(client, v1)
    v2 = propose(client)["version"]
    confirm(client, v2)
    send(hub, "status", example("status.running", prescription_version=0, pending_version=v2))
    assert (state(hub, v1), state(hub, v2)) == ("superseded", "sent")


def test_offline_pump_stays_sent_and_gets_it_again_on_online(client, hub, publisher):
    send(hub, "availability", "offline")
    v = propose(client)["version"]
    confirm(client, v)
    assert state(hub, v) == "sent"
    send(hub, "availability", "online")
    assert [m["version"] for _, m, _, _ in publisher.sent] == [v, v]
    assert state(hub, v) == "sent"


def test_every_state_change_is_audited(client, hub):
    v = propose(client)["version"]
    confirm(client, v)
    send(hub, "event", applied(v))
    rows = hub.conn.execute(
        "SELECT actor, action, old_value, new_value FROM audit ORDER BY id"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("clin-01", "proposed", None, "proposed"),
        ("care-01", "confirmed", "proposed", "confirmed"),
        ("hub", "sent", "confirmed", "sent"),
        (PUMP, "applied_by_pump", "sent", "active"),
    ]


# --- live updates ---


def test_snapshot_has_status_availability_and_open_prescriptions(client, hub):
    send(hub, "status", example("status.running"))
    v = propose(client)["version"]
    declined = propose(client)["version"]
    client.post(
        f"/api/pumps/{PUMP}/prescriptions/{declined}/decline", json={"declined_by": "care-01"}
    )
    events = hub.snapshot(PUMP)
    assert [e for e, _ in events] == ["status", "availability", "prescription"]
    assert events[2][1]["version"] == v


def test_lifecycle_changes_reach_subscribers(client, hub):
    queue = hub.live.subscribe(PUMP)
    v = propose(client)["version"]
    confirm(client, v)
    send(hub, "event", applied(v))
    seen = []
    while not queue.empty():
        event, data = queue.get_nowait()
        seen.append((event, data.get("state")))
    assert ("prescription", "sent") in seen
    assert ("prescription", "active") in seen
    assert ("pump_event", None) in seen


# --- from the safety review ---


def test_confirming_an_older_version_after_a_newer_one_is_refused(client, hub, publisher):
    # S3: the retained message must never go back to an older version.
    v1 = propose(client)["version"]
    v2 = propose(client)["version"]
    assert confirm(client, v2).json()["state"] == "sent"
    response = confirm(client, v1)
    assert response.status_code == 409
    assert response.json()["error"] == "stale_version"
    assert state(hub, v1) == "proposed"
    assert [m["version"] for _, m, _, _ in publisher.sent] == [v2]


def test_gate_refuses_an_older_version_when_a_newer_one_is_active(client, hub, publisher):
    v1 = propose(client)["version"]
    confirm(client, v1)
    v2 = propose(client)["version"]
    confirm(client, v2)
    send(hub, "event", applied(v2))  # v1 superseded, v2 active
    hub.conn.execute("UPDATE prescriptions SET state = 'sent' WHERE version = ?", (v1,))
    with pytest.raises(PublishRefused, match="newer"):
        prescriptions.publish_prescription(hub.conn, publisher, PUMP, v1)


@pytest.mark.parametrize("bad", ['"Infinity"', '"NaN"', "1e999"])
def test_propose_rejects_non_finite_numbers(client, bad):
    body = (
        '{"mode": "continuous", "rate_ml_hr": ' + bad
        + ', "volume_ml": 500, "proposed_by": "clin-01"}'
    )  # fmt: skip
    response = client.post(
        f"/api/pumps/{PUMP}/prescriptions",
        content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


def test_pump_stale_rejection_of_a_sent_version(client, hub):
    v = propose(client)["version"]
    confirm(client, v)
    send(hub, "event", example("event.rejected", version=v, reason="stale_version"))
    p = prescriptions.get(hub.conn, PUMP, v)
    assert (p["state"], p["reject_reason"]) == ("rejected", "stale_version")


def test_decline_and_resend_and_failure_are_audited(client, hub, publisher):
    v = propose(client)["version"]
    client.post(
        f"/api/pumps/{PUMP}/prescriptions/{v}/decline",
        json={"declined_by": "care-01", "reason": "talk first"},
    )
    v2 = propose(client)["version"]
    confirm(client, v2)
    send(hub, "availability", "offline")
    send(hub, "availability", "online")  # re-send
    publisher.fail = True
    send(hub, "availability", "offline")
    send(hub, "availability", "online")  # re-send fails
    actions = [r[0] for r in hub.conn.execute("SELECT action FROM audit ORDER BY id")]
    assert actions[1:3] == ["declined", "decline_reason"]
    assert "resent" in actions
    assert actions[-1] == "publish_failed"


def test_failed_change_leaves_no_partial_write(client, hub):
    v = propose(client)["version"]
    before = hub.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
    assert confirm(client, v, by="nobody").status_code == 422
    assert state(hub, v) == "proposed"
    assert hub.conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == before


# --- R1: rejection carried in telemetry (contract-v1) ---


def test_rejection_from_status_when_the_event_was_lost(client, hub):
    v = propose(client, rate=500)["version"]
    confirm(client, v)
    send(hub, "status", example("status.rejected", last_rejected_version=v))
    p = prescriptions.get(hub.conn, PUMP, v)
    assert (p["state"], p["reject_reason"]) == ("rejected", "rate_out_of_range")


def test_old_last_rejected_version_does_not_touch_other_versions(client, hub):
    send(hub, "status", example("status.rejected"))
    v = propose(client)["version"]
    confirm(client, v)
    send(hub, "status", example("status.rejected"))  # still reports the old rejection
    assert state(hub, v) == "sent"


def test_next_version_is_above_last_rejected_version(client, hub):
    send(hub, "status", example("status.rejected", last_rejected_version=40))
    assert propose(client)["version"] == 41


def test_status_passes_optional_fields_through(client, hub):
    send(hub, "status", example("status.rejected"))
    body = client.get(f"/api/pumps/{PUMP}/status").json()
    assert body["last_reject_reason"] == "rate_out_of_range"
    assert "uptime_ms" not in body


# --- H1 (Sync 1 and 2 safety reviews): never publish below a version already sent ---


def _sent_then_pump_rejected(client, hub) -> int:
    v = propose(client, rate=500)["version"]
    confirm(client, v)
    send(hub, "event", example("event.rejected", version=v, reason="rate_out_of_range"))
    assert state(hub, v) == "rejected"
    return v


def test_republish_never_goes_back_below_a_pump_rejected_version(client, hub, publisher):
    send(hub, "availability", "offline")
    v1 = propose(client)["version"]
    confirm(client, v1)  # sent, but the offline pump never saw it
    v2 = _sent_then_pump_rejected(client, hub)  # the retained message is now v2
    before = list(publisher.sent)
    hub.handle_message(CONNECTED, b"")  # hub or broker reconnect
    send(hub, "availability", "online")  # pump back online
    assert publisher.sent == before, "re-published a version older than one already sent"
    assert [m["version"] for _, m, _, _ in publisher.sent] == [v1, v2]


def test_confirm_refuses_an_older_proposal_after_a_newer_was_sent(client, hub, publisher):
    v1 = propose(client)["version"]  # left waiting on the family "Change to review" card
    _sent_then_pump_rejected(client, hub)
    before = list(publisher.sent)
    response = confirm(client, v1)
    assert response.status_code == 409
    assert response.json()["error"] == "stale_version"
    assert publisher.sent == before
    assert state(hub, v1) == "proposed"


def test_a_declined_newer_version_does_not_block_an_older_one(client, hub, publisher):
    v1 = propose(client)["version"]
    v2 = propose(client)["version"]
    response = client.post(
        f"/api/pumps/{PUMP}/prescriptions/{v2}/decline", json={"declined_by": "care-01"}
    )
    assert response.status_code == 200
    assert confirm(client, v1).json()["state"] == "sent"  # v2 was never published
