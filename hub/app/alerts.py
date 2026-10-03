"""Alerts: the hub's reading of pump alarms (FR-14, FR-15). Codes only; the copy is in web/.

Alarm events arrive at QoS 0 and can be lost, so the `alarm` field in every status
also opens and closes alerts. The pump holds at most one alarm at a time.
"""

import sqlite3
from typing import Any

from hub.app.db import audit, utc_now


def as_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "pump_id": row["pump_id"],
        "alarm": row["alarm"],
        "active": row["cleared_at"] is None,
        "raised_at": row["raised_at"],
        "cleared_at": row["cleared_at"],
        "simulated": bool(row["simulated"]),
    }


def list_for_pump(conn: sqlite3.Connection, pump_id: str) -> list[dict[str, Any]]:
    """Active first, then newest first."""
    rows = conn.execute(
        "SELECT * FROM alerts WHERE pump_id = ? ORDER BY cleared_at IS NOT NULL, id DESC",
        (pump_id,),
    ).fetchall()
    return [as_dict(r) for r in rows]


def active_for_pump(conn: sqlite3.Connection, pump_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM alerts WHERE pump_id = ? AND cleared_at IS NULL ORDER BY id", (pump_id,)
    ).fetchall()
    return [as_dict(r) for r in rows]


def _audit(conn: sqlite3.Connection, pump_id: str, alert_id: int, action: str,
           old: str | None, new: str) -> None:  # fmt: skip
    audit(
        conn, actor=pump_id, actor_role="pump", entity="alarm",
        entity_id=f"{pump_id}/alert/{alert_id}", action=action, old_value=old, new_value=new,
    )  # fmt: skip


def raise_alert(
    conn: sqlite3.Connection, pump_id: str, alarm: str, simulated: bool
) -> dict[str, Any] | None:
    """Open an alert unless one with this code is already open. Returns it if new."""
    open_row = conn.execute(
        "SELECT 1 FROM alerts WHERE pump_id = ? AND alarm = ? AND cleared_at IS NULL",
        (pump_id, alarm),
    ).fetchone()
    if open_row is not None:
        return None
    cur = conn.execute(
        "INSERT INTO alerts (pump_id, alarm, raised_at, simulated) VALUES (?, ?, ?, ?)",
        (pump_id, alarm, utc_now(), int(simulated)),
    )
    _audit(conn, pump_id, cur.lastrowid, "alarm_raised", None, alarm)
    row = conn.execute("SELECT * FROM alerts WHERE id = ?", (cur.lastrowid,)).fetchone()
    return as_dict(row)


def clear_alerts(
    conn: sqlite3.Connection, pump_id: str, alarm: str | None = None, keep: str | None = None
) -> list[dict[str, Any]]:
    """Close open alerts for one code, or every open code except `keep`. Returns those closed."""
    rows = conn.execute(
        "SELECT * FROM alerts WHERE pump_id = ? AND cleared_at IS NULL", (pump_id,)
    ).fetchall()
    closed = []
    now = utc_now()
    for row in rows:
        if (alarm is not None and row["alarm"] != alarm) or row["alarm"] == keep:
            continue
        conn.execute("UPDATE alerts SET cleared_at = ? WHERE id = ?", (now, row["id"]))
        _audit(conn, pump_id, row["id"], "alarm_cleared", row["alarm"], "cleared")
        closed.append({**as_dict(row), "active": False, "cleared_at": now})
    return closed


def apply_pump_event(conn: sqlite3.Connection, event: dict[str, Any]) -> list[dict[str, Any]]:
    if event["type"] == "alarm_raised":
        raised = raise_alert(conn, event["pump_id"], event["alarm"], event["simulated"])
        return [raised] if raised else []
    if event["type"] == "alarm_cleared":
        return clear_alerts(conn, event["pump_id"], alarm=event["alarm"])
    return []


def apply_pump_status(conn: sqlite3.Connection, status: dict[str, Any]) -> list[dict[str, Any]]:
    """Make the open alerts match the alarm the pump reports, in case an event was lost."""
    pump_id, alarm = status["pump_id"], status["alarm"]
    changed = clear_alerts(conn, pump_id, keep=alarm)
    if alarm is not None:
        raised = raise_alert(conn, pump_id, alarm, status["simulated"])
        if raised:
            changed.append(raised)
    return changed
