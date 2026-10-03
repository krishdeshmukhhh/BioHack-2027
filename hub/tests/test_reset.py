"""Demo reset: archive, never delete (S7); clear only the retained prescription."""

from datetime import UTC, datetime
from pathlib import Path

from hub.app.db import audit, connect
from hub.reset import archive_db, clear_retained, reset
from hub.tests.helpers import PUMP


def make_db(path: Path) -> None:
    conn = connect(str(path))
    audit(
        conn, actor="clin-01", actor_role="clinician", entity="prescription",
        entity_id=f"{PUMP}/8", action="proposed", old_value=None, new_value="90",
    )  # fmt: skip
    conn.close()


def test_archive_keeps_every_audit_row(tmp_path: Path) -> None:
    db = tmp_path / "hub.sqlite3"
    make_db(db)
    archived = archive_db(db, now=datetime(2026, 10, 3, 12, 0, tzinfo=UTC))
    assert archived == tmp_path / "archive" / "hub-20261003T120000Z.sqlite3"
    assert not db.exists()
    conn = connect(str(archived))
    assert conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 1


def test_archive_without_a_database(tmp_path: Path) -> None:
    assert archive_db(tmp_path / "hub.sqlite3") is None


def test_reset_clears_only_the_prescription_topic(tmp_path: Path) -> None:
    db = tmp_path / "hub.sqlite3"
    make_db(db)
    cleared: list[str] = []
    assert reset(db, PUMP, lambda t: cleared.append(t) or True, hub_running=False) == 0
    assert cleared == [f"pump/{PUMP}/prescription"]
    assert not db.exists()


def test_reset_refuses_while_the_hub_runs(tmp_path: Path) -> None:
    db = tmp_path / "hub.sqlite3"
    make_db(db)
    cleared: list[str] = []
    assert reset(db, PUMP, lambda t: cleared.append(t) or True, hub_running=True) == 1
    assert db.exists() and cleared == []


def test_reset_reports_a_broker_failure(tmp_path: Path) -> None:
    assert reset(tmp_path / "hub.sqlite3", PUMP, lambda t: False, hub_running=False) == 1


class FakeInfo:
    def __init__(self, published: bool) -> None:
        self._published = published

    def wait_for_publish(self, timeout: float | None = None) -> None:
        pass

    def is_published(self) -> bool:
        return self._published


class FakeClient:
    def __init__(self, reachable: bool = True) -> None:
        self.reachable = reachable
        self.published: list[tuple] = []
        self.disconnected = False

    def connect(self, host: str, port: int, keepalive: int) -> None:
        if not self.reachable:
            raise ConnectionRefusedError("no broker")

    def loop_start(self) -> None:
        pass

    def loop_stop(self) -> None:
        pass

    def disconnect(self) -> None:
        self.disconnected = True

    def publish(self, topic: str, payload: bytes, qos: int, retain: bool) -> FakeInfo:
        self.published.append((topic, payload, qos, retain))
        return FakeInfo(True)


def test_clear_retained_publishes_an_empty_retained_message() -> None:
    client = FakeClient()
    topic = f"pump/{PUMP}/prescription"
    assert clear_retained("localhost", 1883, topic, client=client)
    assert client.published == [(topic, b"", 1, True)]
    assert client.disconnected


def test_clear_retained_without_a_broker() -> None:
    client = FakeClient(reachable=False)
    assert not clear_retained("localhost", 1883, f"pump/{PUMP}/prescription", client=client)
    assert client.published == []
