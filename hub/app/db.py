"""SQLite connection, seed data, and the audit log. Standard library only, no ORM."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")

# Fixed demo users, as in docs/API.md. There is no authentication in the prototype.
USERS: dict[str, tuple[str, str]] = {
    "clin-01": ("clinician", "Dr. Demo"),
    "care-01": ("parent", "Parent (demo)"),
    "care-02": ("school_nurse", "School nurse (demo)"),
}
CAREGIVER_ROLES = {"parent", "school_nurse"}


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # The connection is only used from the asyncio event loop thread.
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text())
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    """One atomic unit, so a state change never lands without its audit row (S7)."""
    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def seed(conn: sqlite3.Connection, demo_pump_id: str) -> None:
    """Fictional patients. The first one uses the pump id this hub is configured for."""
    patients = [
        ("pat-01", "Sam (fictional)", demo_pump_id, 1000.0),
        ("pat-02", "Robin (fictional)", "pump-002", 900.0),
        ("pat-03", "Kai (fictional)", "pump-003", 1100.0),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO patients (id, display_name, pump_id, daily_goal_ml, simulated)"
        " VALUES (?, ?, ?, ?, 1)",
        patients,
    )


def audit(
    conn: sqlite3.Connection,
    *,
    actor: str,
    actor_role: str,
    entity: str,
    entity_id: str,
    action: str,
    old_value: str | None,
    new_value: str | None,
) -> None:
    """Append one audit row (S7). There is deliberately no update or delete helper."""
    conn.execute(
        "INSERT INTO audit (at, actor, actor_role, entity, entity_id, action, old_value, new_value)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (utc_now(), actor, actor_role, entity, entity_id, action, old_value, new_value),
    )


def known_pump(conn: sqlite3.Connection, pump_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM patients WHERE pump_id = ?", (pump_id,)).fetchone()
    return row is not None
