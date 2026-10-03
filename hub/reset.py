"""Demo reset for the hub (docs/DEMO.md: "v7 at 60 mL/hr, pump idle"). Prototype only.

Run from the repo root with the hub stopped:

    python -m hub.reset

1. Moves the hub database to hub/data/archive/. Nothing is deleted, so every audit
   row survives (S7); the next `make hub` starts a fresh database.
2. Clears the retained prescription on the broker for PUMP_ID by publishing an
   empty retained message. Otherwise a pump reset to v7 would receive the last
   demo's retained prescription on connect and apply it. An empty payload is not
   a prescription: the pump drops it as malformed with no readable version, so
   this never changes what a pump is running (S2, S6).

The pump side of the reset is separate: `python -m sim.pump_sim --demo-seed` for the
simulator, or the firmware's own reset for the ESP32 (versions only go up, S3).
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sqlite3
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger("hub.reset")

DB_SUFFIXES = ("", "-wal", "-shm", "-journal")


class Publisher(Protocol):
    def __call__(self, topic: str) -> bool: ...


def hub_is_running(port: int, timeout_s: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout_s):
            return True
    except OSError:
        return False


def archive_db(db_path: Path, now: datetime | None = None) -> Path | None:
    """Move the database (and any SQLite side files) into an archive folder.

    Returns the archived database path, or None if there was no database.
    """
    if not db_path.exists():
        return None
    # Fold any write-ahead log into the main file first, so the move cannot split
    # audit rows between the archive and a leftover side file (S7).
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = db_path.parent / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / f"{db_path.stem}-{stamp}{db_path.suffix}"
    if target.exists():
        raise FileExistsError(f"{target} already exists; try again in a second")
    for suffix in DB_SUFFIXES:
        src = Path(f"{db_path}{suffix}")
        if src.exists():
            shutil.move(src, f"{target}{suffix}")
    return target


def clear_retained(
    host: str, port: int, topic: str, timeout_s: float = 5.0, client: Any = None
) -> bool:
    """Publish an empty retained message, which removes the retained one (MQTT 3.1.1).

    Tests pass a fake paho client.
    """
    if client is None:
        import paho.mqtt.client as mqtt
        from paho.mqtt.enums import CallbackAPIVersion

        client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="smart-pump-hub-reset")
    try:
        client.connect(host, port, keepalive=10)
    except OSError as exc:
        log.error("cannot reach the broker at %s:%s: %s", host, port, exc)
        return False
    client.loop_start()
    try:
        info = client.publish(topic, b"", qos=1, retain=True)
        info.wait_for_publish(timeout=timeout_s)
        return info.is_published()
    finally:
        client.disconnect()
        client.loop_stop()


def reset(db_path: Path, pump_id: str, clear: Publisher | None, *, hub_running: bool) -> int:
    if hub_running:
        log.error("the hub is running; stop it first (Ctrl+C on `make hub`), then reset")
        return 1
    archived = archive_db(db_path)
    if archived is None:
        log.info("no database at %s; nothing to archive", db_path)
    else:
        log.info("archived the database to %s (audit rows kept, S7)", archived)
    if clear is not None:
        topic = f"pump/{pump_id}/prescription"
        if not clear(topic):
            log.error("could not clear the retained prescription on %s", topic)
            return 1
        log.info("cleared the retained prescription on %s", topic)
    log.info(
        "next: start the hub, then the pump in its reset state "
        "(simulator: python -m sim.pump_sim --demo-seed, without an old --state-file). "
        "Wait until the portal shows the pump online at v7 before proposing: until the "
        "first status arrives the hub cannot know the pump's version."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m hub.reset",
        description="Return the hub to the DEMO.md starting state. Prototype demo only.",
    )
    p.add_argument("--db", type=Path, default=os.environ.get("HUB_DB_PATH", "hub/data/hub.sqlite3"))
    p.add_argument("--pump-id", default=os.environ.get("PUMP_ID", "pump-001"))
    p.add_argument("--host", default=os.environ.get("MQTT_HOST", "localhost"))
    p.add_argument("--port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    p.add_argument("--hub-port", type=int, default=int(os.environ.get("HUB_PORT", "8000")))
    p.add_argument("--no-broker", action="store_true", help="only archive the database")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def clear(topic: str) -> bool:
        return clear_retained(args.host, args.port, topic)

    return reset(
        args.db, args.pump_id, None if args.no_broker else clear,
        hub_running=hub_is_running(args.hub_port),
    )  # fmt: skip


if __name__ == "__main__":
    sys.exit(main())
