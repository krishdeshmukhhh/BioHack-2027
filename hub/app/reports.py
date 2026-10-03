"""Clinician reports: generated history, exceptions, daily totals, weekly facts, profiles.

Thresholds are the demo values in docs/API.md, not clinical guidance. Everything
built from generated history is labelled simulated (S8).
"""

import json
import logging
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("hub.reports")

HISTORY_FILE = Path(__file__).resolve().parents[2] / "sim" / "data" / "history.json"

UNDER_TARGET_FRACTION = 0.9
UNDER_TARGET_DAYS = 3
NIGHT_ALARMS_MAX = 2
NIGHT_START_HOUR = 22  # UTC; the window runs 8 hours, to 06:00
NIGHT_HOURS = 8
WEEK_DAYS = 7

# Demo feed profiles that pre-fill a proposal (FR-28). Demo values, not guidance.
DEMO_PROFILES = [
    ("pat-01", "Overnight continuous", "continuous", 60.0, 500.0),
    ("pat-01", "Daytime bolus", "bolus", 120.0, 200.0),
    ("pat-02", "Overnight continuous", "continuous", 50.0, 400.0),
    ("pat-03", "Overnight continuous", "continuous", 40.0, 350.0),
]


# --- loading ---


def load_history(conn: sqlite3.Connection, path: Path = HISTORY_FILE) -> bool:
    """Replace the generated history with the file's rows. False if there is no file.

    Rows for patients the hub does not know are skipped. The pump id in the file is
    ignored: the hub's patients table decides which pump a patient uses.
    """
    if not path.is_file():
        return False
    data = json.loads(path.read_text())
    load_history_data(conn, data)
    return True


def load_history_data(conn: sqlite3.Connection, data: dict[str, Any]) -> None:
    if data.get("simulated") is not True:
        raise ValueError("history must be labelled simulated (S8)")
    known = {r["id"] for r in conn.execute("SELECT id FROM patients")}
    conn.execute("DELETE FROM history_daily")
    conn.execute("DELETE FROM history_alarms")
    conn.executemany(
        "INSERT INTO history_daily (patient_id, date, delivered_ml, prescribed_ml, alarm_count,"
        " simulated) VALUES (?, ?, ?, ?, ?, 1)",
        [
            (d["patient_id"], d["date"], d["delivered_ml"], d["prescribed_ml"], d["alarm_count"])
            for d in data["daily"]
            if d["patient_id"] in known
        ],
    )
    conn.executemany(
        "INSERT INTO history_alarms (patient_id, alarm, raised_at, cleared_at, simulated)"
        " VALUES (?, ?, ?, ?, 1)",
        [
            (a["patient_id"], a["alarm"], a["raised_at"], a.get("cleared_at"))
            for a in data["alarms"]
            if a["patient_id"] in known
        ],
    )
    log.info("loaded history ending %s", data.get("generated_for_end_date"))


def seed_profiles(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]:
        return
    conn.executemany(
        "INSERT INTO profiles (patient_id, name, mode, rate_ml_hr, volume_ml)"
        " VALUES (?, ?, ?, ?, ?)",
        DEMO_PROFILES,
    )


# --- queries ---


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def night_window(now: datetime) -> tuple[str, str]:
    """The most recent night window: from the latest 22:00 UTC at or before now, 8 hours."""
    start = now.replace(hour=NIGHT_START_HOUR, minute=0, second=0, microsecond=0)
    if start > now:
        start -= timedelta(days=1)
    return _iso(start), _iso(start + timedelta(hours=NIGHT_HOURS))


def night_alarm_count(
    conn: sqlite3.Connection, patient_id: str, pump_id: str, now: datetime
) -> int:
    """Generated alarms plus live alerts raised in the most recent night window."""
    start, stop = night_window(now)
    history = conn.execute(
        "SELECT COUNT(*) FROM history_alarms WHERE patient_id = ? AND raised_at >= ?"
        " AND raised_at < ?",
        (patient_id, start, stop),
    ).fetchone()[0]
    live = conn.execute(
        "SELECT COUNT(*) FROM alerts WHERE pump_id = ? AND raised_at >= ? AND raised_at < ?",
        (pump_id, start, stop),
    ).fetchone()[0]
    return history + live


def under_target(conn: sqlite3.Connection, patient_id: str) -> bool:
    rows = conn.execute(
        "SELECT delivered_ml, prescribed_ml FROM history_daily WHERE patient_id = ?"
        " ORDER BY date DESC LIMIT ?",
        (patient_id, UNDER_TARGET_DAYS),
    ).fetchall()
    return len(rows) == UNDER_TARGET_DAYS and all(
        r["delivered_ml"] < UNDER_TARGET_FRACTION * r["prescribed_ml"] for r in rows
    )


def patients(
    conn: sqlite3.Connection, is_online: Callable[[str], bool], now: datetime | None = None
) -> list[dict[str, Any]]:
    """Patient list with exception codes, patients with exceptions first (FR-19)."""
    now = now or datetime.now(UTC)
    rows = []
    for p in conn.execute("SELECT * FROM patients ORDER BY id"):
        online = is_online(p["pump_id"])
        exceptions = []
        if not online:
            exceptions.append("offline")
        if under_target(conn, p["id"]):
            exceptions.append("under_target")
        if night_alarm_count(conn, p["id"], p["pump_id"], now) > NIGHT_ALARMS_MAX:
            exceptions.append("night_alarms")
        rows.append({
            "id": p["id"], "display_name": p["display_name"], "pump_id": p["pump_id"],
            "exceptions": exceptions, "online": online, "simulated": bool(p["simulated"]),
        })  # fmt: skip
    rows.sort(key=lambda r: (not r["exceptions"], r["id"]))
    return rows


def known_patient(conn: sqlite3.Connection, patient_id: str) -> bool:
    return conn.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,)).fetchone() is not None


def daily(conn: sqlite3.Connection, patient_id: str, days: int) -> list[dict[str, Any]]:
    """Delivered versus prescribed per day, oldest first (FR-20)."""
    rows = conn.execute(
        "SELECT * FROM (SELECT * FROM history_daily WHERE patient_id = ? ORDER BY date DESC"
        " LIMIT ?) ORDER BY date",
        (patient_id, days),
    ).fetchall()
    return [
        {
            "date": r["date"], "delivered_ml": r["delivered_ml"],
            "prescribed_ml": r["prescribed_ml"], "alarm_count": r["alarm_count"],
            "simulated": bool(r["simulated"]),
        }  # fmt: skip
        for r in rows
    ]


def weekly_summary(conn: sqlite3.Connection, patient_id: str) -> dict[str, Any]:
    """Rule-based weekly facts (FR-21). Codes and numbers only; the web app words them."""
    days = daily(conn, patient_id, WEEK_DAYS * 2)
    week, prior = days[-WEEK_DAYS:], days[:-WEEK_DAYS]

    def pct(rows: list[dict[str, Any]]) -> float | None:
        prescribed = sum(r["prescribed_ml"] for r in rows)
        if not prescribed:
            return None
        return round(100 * sum(r["delivered_ml"] for r in rows) / prescribed, 1)

    week_pct, prior_pct = pct(week), pct(prior)
    if week_pct is None or prior_pct is None:
        trend = None
    elif week_pct - prior_pct >= 5:
        trend = "improving"
    elif prior_pct - week_pct >= 5:
        trend = "declining"
    else:
        trend = "steady"
    alarms: dict[str, int] = {}
    if week:
        for r in conn.execute(
            "SELECT alarm, COUNT(*) AS n FROM history_alarms WHERE patient_id = ?"
            " AND substr(raised_at, 1, 10) >= ? GROUP BY alarm ORDER BY n DESC, alarm",
            (patient_id, week[0]["date"]),
        ):
            alarms[r["alarm"]] = r["n"]
    return {
        "patient_id": patient_id,
        "from_date": week[0]["date"] if week else None,
        "to_date": week[-1]["date"] if week else None,
        "days": len(week),
        "delivered_pct": week_pct,
        "prior_week_delivered_pct": prior_pct,
        "trend": trend,
        "days_under_target": sum(
            r["delivered_ml"] < UNDER_TARGET_FRACTION * r["prescribed_ml"] for r in week
        ),
        "alarm_count": sum(alarms.values()),
        "alarms_by_code": alarms,
        "simulated": True,
    }


def profiles(conn: sqlite3.Connection, patient_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM profiles WHERE patient_id = ? ORDER BY id", (patient_id,)
    ).fetchall()
    return [
        {"id": r["id"], "patient_id": r["patient_id"], "name": r["name"], "mode": r["mode"],
         "rate_ml_hr": r["rate_ml_hr"], "volume_ml": r["volume_ml"], "simulated": True}
        for r in rows
    ]  # fmt: skip
