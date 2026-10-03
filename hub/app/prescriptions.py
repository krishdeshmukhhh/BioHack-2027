"""Prescription lifecycle and the single publish gate.

States: proposed, confirmed, sent, active, rejected, superseded (docs/PROTOCOL.md).

- Web requests may only propose, confirm, or decline (and so publish).
- Only pump data (apply_pump_event, apply_pump_status) may set active, rejected
  for a pump reason, or superseded (S5).
- publish_prescription is the only function that publishes, and it refuses
  anything without a stored caregiver confirmation (S2).
"""

import json
import logging
import sqlite3
from typing import Any, Protocol

from hub.app import protocol
from hub.app.db import CAREGIVER_ROLES, USERS, audit, utc_now

log = logging.getLogger("hub.prescriptions")

FIELDS = (
    "pump_id", "version", "mode", "rate_ml_hr", "volume_ml", "note", "state", "reject_reason",
    "proposed_by", "proposed_at", "confirmed_by", "confirmed_role", "confirmed_at",
    "sent_at", "resolved_at",
)  # fmt: skip
# Hub states in which the pump may still apply or reject a version.
IN_FLIGHT = ("confirmed", "sent")


class Publisher(Protocol):
    def publish(self, topic: str, payload: str, qos: int, retain: bool) -> bool: ...


class LifecycleError(Exception):
    """A request the lifecycle refuses. Maps to an API error code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class PublishRefused(Exception):
    """The publish gate refused to send a prescription."""


def as_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {name: row[name] for name in FIELDS}


def get(conn: sqlite3.Connection, pump_id: str, version: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM prescriptions WHERE pump_id = ? AND version = ?", (pump_id, version)
    ).fetchone()
    return as_dict(row) if row else None


def list_for_pump(conn: sqlite3.Connection, pump_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM prescriptions WHERE pump_id = ? ORDER BY version DESC", (pump_id,)
    ).fetchall()
    return [as_dict(r) for r in rows]


def _set_state(
    conn: sqlite3.Connection,
    pump_id: str,
    version: int,
    new_state: str,
    *,
    actor: str,
    actor_role: str,
    action: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The one place a prescription changes state. Always writes an audit row (S7)."""
    old = get(conn, pump_id, version)
    assert old is not None
    updates = {"state": new_state, **(extra or {})}
    if new_state in ("active", "rejected", "superseded") and not old["resolved_at"]:
        updates["resolved_at"] = utc_now()
    assignments = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE prescriptions SET {assignments} WHERE pump_id = ? AND version = ?",
        (*updates.values(), pump_id, version),
    )
    audit(
        conn,
        actor=actor,
        actor_role=actor_role,
        entity="prescription",
        entity_id=f"{pump_id}/{version}",
        action=action,
        old_value=old["state"],
        new_value=new_state,
    )
    new = get(conn, pump_id, version)
    assert new is not None
    return new


def next_version(conn: sqlite3.Connection, pump_id: str) -> int:
    """Versions only go up (S3): above every stored version and anything the pump reports."""
    stored = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM prescriptions WHERE pump_id = ?", (pump_id,)
    ).fetchone()[0]
    reported = conn.execute(
        "SELECT MAX(prescription_version, COALESCE(pending_version, 0),"
        " COALESCE(last_rejected_version, 0)) FROM status_samples"
        " WHERE pump_id = ? ORDER BY id DESC LIMIT 1",
        (pump_id,),
    ).fetchone()
    return max(stored, reported[0] if reported else 0) + 1


def propose(
    conn: sqlite3.Connection,
    pump_id: str,
    *,
    mode: str,
    rate_ml_hr: float,
    volume_ml: float,
    note: str,
    proposed_by: str,
) -> dict[str, Any]:
    """Store a clinician proposal. The API checks shape only; limits are the pump's job (S1)."""
    if USERS.get(proposed_by, ("",))[0] != "clinician":
        raise LifecycleError("invalid_input", "proposed_by must be a clinician user id")
    version = next_version(conn, pump_id)
    conn.execute(
        "INSERT INTO prescriptions (pump_id, version, mode, rate_ml_hr, volume_ml, note, state,"
        " proposed_by, proposed_at) VALUES (?, ?, ?, ?, ?, ?, 'proposed', ?, ?)",
        (pump_id, version, mode, rate_ml_hr, volume_ml, note, proposed_by, utc_now()),
    )
    audit(
        conn,
        actor=proposed_by,
        actor_role="clinician",
        entity="prescription",
        entity_id=f"{pump_id}/{version}",
        action="proposed",
        old_value=None,
        new_value="proposed",
    )
    created = get(conn, pump_id, version)
    assert created is not None
    return created


def _require_proposed(conn: sqlite3.Connection, pump_id: str, version: int) -> None:
    current = get(conn, pump_id, version)
    if current is None:
        raise LifecycleError("unknown_prescription", f"no version {version} for {pump_id}")
    if current["state"] != "proposed":
        raise LifecycleError("not_proposed", f"version {version} is {current['state']}")


def _newer_version_exists(conn: sqlite3.Connection, pump_id: str, version: int) -> int | None:
    """S3: the highest version above `version` that is confirmed, sent, or active, or
    that was ever published (sent_at set), if any. A newer version the pump rejected
    still counts: re-publishing an older one would make the pump apply a prescription
    the clinician had replaced. Declined versions were never published, so they don't.
    """
    row = conn.execute(
        "SELECT MAX(version) FROM prescriptions WHERE pump_id = ? AND version > ?"
        " AND (state IN ('confirmed', 'sent', 'active') OR sent_at IS NOT NULL)",
        (pump_id, version),
    ).fetchone()
    return row[0]


def _audit_hub(
    conn: sqlite3.Connection, pump_id: str, version: int, action: str, note: str
) -> None:
    audit(
        conn, actor="hub", actor_role="hub", entity="prescription",
        entity_id=f"{pump_id}/{version}", action=action, old_value=None, new_value=note,
    )  # fmt: skip


def _caregiver_role(user_id: str, field: str) -> str:
    role = USERS.get(user_id, ("",))[0]
    if role not in CAREGIVER_ROLES:
        raise LifecycleError("invalid_input", f"{field} must be a caregiver user id")
    return role


def confirm(
    conn: sqlite3.Connection, publisher: Publisher | None, pump_id: str, version: int,
    confirmed_by: str,
) -> list[dict[str, Any]]:  # fmt: skip
    """Record the caregiver confirmation, then send through the publish gate.

    Returns every prescription that changed, latest state last.
    """
    _require_proposed(conn, pump_id, version)
    role = _caregiver_role(confirmed_by, "confirmed_by")
    newer = _newer_version_exists(conn, pump_id, version)
    if newer is not None:
        # Publishing this would replace the retained v{newer} with an older version.
        raise LifecycleError("stale_version", f"version {newer} is already confirmed or newer")
    changed = [
        _set_state(
            conn, pump_id, version, "confirmed",
            actor=confirmed_by, actor_role=role, action="confirmed",
            extra={"confirmed_by": confirmed_by, "confirmed_role": role,
                   "confirmed_at": utc_now()},
        )
    ]  # fmt: skip
    try:
        sent = publish_prescription(conn, publisher, pump_id, version)
    except PublishRefused as exc:
        log.warning("publish of %s/%s failed, left as confirmed: %s", pump_id, version, exc)
        _audit_hub(conn, pump_id, version, "publish_failed", str(exc))
    else:
        if sent is not None:
            changed.append(sent)
    return changed


def decline(
    conn: sqlite3.Connection, pump_id: str, version: int, declined_by: str, reason: str | None
) -> dict[str, Any]:
    """Caregiver says no. Nothing is published (FR-8)."""
    _require_proposed(conn, pump_id, version)
    role = _caregiver_role(declined_by, "declined_by")
    result = _set_state(
        conn, pump_id, version, "rejected",
        actor=declined_by, actor_role=role, action="declined",
        extra={"reject_reason": "declined"},
    )  # fmt: skip
    if reason:
        audit(
            conn, actor=declined_by, actor_role=role, entity="prescription",
            entity_id=f"{pump_id}/{version}", action="decline_reason",
            old_value=None, new_value=reason,
        )  # fmt: skip
    return result


def publish_prescription(
    conn: sqlite3.Connection, publisher: Publisher | None, pump_id: str, version: int
) -> dict[str, Any] | None:
    """THE publish gate (S2). Every prescription the pump receives goes through here.

    Refuses anything without a stored caregiver confirmation or that fails the
    outbound schema. Publishes retained with QoS 1. Moves `confirmed` to `sent`;
    a re-publish of a `sent` version leaves its state alone and returns None.
    """
    p = get(conn, pump_id, version)
    if p is None:
        raise PublishRefused(f"no version {version} for {pump_id}")
    if p["state"] not in IN_FLIGHT:
        raise PublishRefused(f"version {version} is {p['state']}, not confirmed")
    if not p["confirmed_by"] or not p["confirmed_at"] or p["confirmed_role"] not in CAREGIVER_ROLES:
        raise PublishRefused(f"version {version} has no caregiver confirmation")
    newer = _newer_version_exists(conn, pump_id, version)
    if newer is not None:
        raise PublishRefused(f"version {newer} is newer; never publish an older version (S3)")

    message: dict[str, Any] = {
        "pump_id": pump_id,
        "version": version,
        "mode": p["mode"],
        "rate_ml_hr": p["rate_ml_hr"],
        "volume_ml": p["volume_ml"],
        "proposed_by": p["proposed_by"],
        "proposed_at": p["proposed_at"],
        "confirmed_by": p["confirmed_by"],
        "confirmed_at": p["confirmed_at"],
    }
    if p["note"]:
        message["note"] = p["note"]  # omitted when empty to keep the payload small (R2)
    problems = protocol.errors("prescription", message)
    if problems:
        raise PublishRefused(f"outbound prescription invalid: {problems}")
    if publisher is None:
        raise PublishRefused("no MQTT publisher")
    payload = json.dumps(message, separators=(",", ":"), allow_nan=False)
    if not publisher.publish(f"pump/{pump_id}/prescription", payload, qos=1, retain=True):
        raise PublishRefused("broker publish failed")

    if p["state"] == "sent":
        _audit_hub(conn, pump_id, version, "resent", "sent")
        return None
    return _set_state(
        conn, pump_id, version, "sent",
        actor="hub", actor_role="hub", action="sent", extra={"sent_at": utc_now()},
    )  # fmt: skip


def republish_latest(
    conn: sqlite3.Connection, publisher: Publisher | None, pump_id: str
) -> dict[str, Any] | None:
    """R3: re-send the newest in-flight version (on hub start, broker reconnect, pump online).

    Duplicates are harmless because the pump ignores versions it already has (S3).
    """
    row = conn.execute(
        "SELECT version FROM prescriptions WHERE pump_id = ? AND state IN ('confirmed', 'sent')"
        " ORDER BY version DESC LIMIT 1",
        (pump_id,),
    ).fetchone()
    if row is None:
        return None
    try:
        return publish_prescription(conn, publisher, pump_id, row["version"])
    except PublishRefused as exc:
        log.warning("re-publish of %s/%s failed: %s", pump_id, row["version"], exc)
        _audit_hub(conn, pump_id, row["version"], "publish_failed", str(exc))
        return None


# --- Pump-driven transitions (the only path to active, pump rejection, superseded) ---


def _activate(conn: sqlite3.Connection, pump_id: str, version: int) -> list[dict[str, Any]]:
    p = get(conn, pump_id, version)
    if p is None or p["state"] not in IN_FLIGHT:
        return []
    changed = [
        _set_state(
            conn, pump_id, version, "active",
            actor=pump_id, actor_role="pump", action="applied_by_pump",
        )
    ]  # fmt: skip
    # FR-9: older active versions, and older ones still in flight, are superseded.
    older = conn.execute(
        "SELECT version FROM prescriptions WHERE pump_id = ? AND version < ?"
        " AND state IN ('active', 'confirmed', 'sent')",
        (pump_id, version),
    ).fetchall()
    for row in older:
        changed.append(_supersede(conn, pump_id, row["version"], by=version))
    return changed


def _supersede(conn: sqlite3.Connection, pump_id: str, version: int, by: int) -> dict[str, Any]:
    return _set_state(
        conn, pump_id, version, "superseded",
        actor=pump_id, actor_role="pump", action=f"superseded_by_{by}",
    )  # fmt: skip


def _supersede_older_in_flight(
    conn: sqlite3.Connection, pump_id: str, pending: int
) -> list[dict[str, Any]]:
    """R6: the pump holds `pending`, so any older version still in flight will never apply."""
    rows = conn.execute(
        "SELECT version FROM prescriptions WHERE pump_id = ? AND version < ?"
        " AND state IN ('confirmed', 'sent')",
        (pump_id, pending),
    ).fetchall()
    return [_supersede(conn, pump_id, r["version"], by=pending) for r in rows]


def _reject(
    conn: sqlite3.Connection, pump_id: str, version: int, reason: str
) -> list[dict[str, Any]]:
    p = get(conn, pump_id, version)
    if p is None or p["state"] not in IN_FLIGHT:
        return []
    return [
        _set_state(
            conn, pump_id, version, "rejected",
            actor=pump_id, actor_role="pump", action="rejected_by_pump",
            extra={"reject_reason": reason},
        )
    ]  # fmt: skip


def apply_pump_event(conn: sqlite3.Connection, event: dict[str, Any]) -> list[dict[str, Any]]:
    """Lifecycle changes from a validated pump event."""
    pump_id, kind, version = event["pump_id"], event["type"], event.get("version")
    if kind == "prescription_applied":
        return _activate(conn, pump_id, version)
    if kind == "prescription_rejected":
        return _reject(conn, pump_id, version, event["reason"])
    if kind == "prescription_queued":
        return _supersede_older_in_flight(conn, pump_id, version)
    return []


def apply_pump_status(conn: sqlite3.Connection, status: dict[str, Any]) -> list[dict[str, Any]]:
    """Lifecycle changes from validated telemetry (S5: active only once the pump reports it)."""
    pump_id = status["pump_id"]
    changed: list[dict[str, Any]] = []
    if status["prescription_version"] > 0:
        changed += _activate(conn, pump_id, status["prescription_version"])
    if status["pending_version"] is not None:
        changed += _supersede_older_in_flight(conn, pump_id, status["pending_version"])
    # R1: the pump repeats its last rejection in telemetry, since QoS 0 events can be lost.
    if status.get("last_rejected_version") and status.get("last_reject_reason"):
        changed += _reject(
            conn, pump_id, status["last_rejected_version"], status["last_reject_reason"]
        )
    return changed
