"""The hub's state: database, MQTT ingest, availability, and live fan-out.

handle_message() is the MQTT ingest path. It is the only caller of the
pump-driven lifecycle functions, so only pump data can make a prescription
active, rejected by the pump, or superseded (S5).
"""

import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from hub.app import alerts, prescriptions, protocol, reports
from hub.app.db import connect, known_pump, seed, transaction, utc_now
from hub.app.live import Broadcaster
from hub.app.mqtt_bridge import CONNECTED
from hub.app.prescriptions import Publisher

log = logging.getLogger("hub.service")

SNAPSHOT_STATES = ("proposed", "confirmed", "sent", "active")
# docs/API.md: a pump with no status for this long counts as offline.
STALE_AFTER = timedelta(seconds=10)


def _parse(at: str) -> datetime:
    return datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


class Hub:
    def __init__(self, db_path: str, demo_pump_id: str, publisher: Publisher | None) -> None:
        self.conn: sqlite3.Connection = connect(db_path)
        with transaction(self.conn):
            seed(self.conn, demo_pump_id)
            reports.seed_profiles(self.conn)
        self.publisher = publisher
        self.live = Broadcaster()
        # pump_id -> {"online": bool, "last_seen_at": str | None}
        self.availability: dict[str, dict[str, Any]] = {}

    # --- queries used by the API and the SSE snapshot ---

    def known_pump(self, pump_id: str) -> bool:
        return known_pump(self.conn, pump_id)

    def pump_ids(self) -> list[str]:
        return [r["pump_id"] for r in self.conn.execute("SELECT pump_id FROM patients")]

    def availability_of(self, pump_id: str) -> dict[str, Any]:
        a = self.availability.get(pump_id, {"online": False, "last_seen_at": None})
        return {"pump_id": pump_id, **a}

    def is_online(self, pump_id: str) -> bool:
        return bool(self.availability_of(pump_id)["online"])

    def load_history(self) -> bool:
        with transaction(self.conn):
            return reports.load_history(self.conn)

    def check_stale(self, now: datetime | None = None) -> None:
        """Mark a pump offline once its last message is older than STALE_AFTER (docs/API.md).

        A pulled wifi link only fires the Last Will after the broker keepalive runs
        out, so the hub does not wait for it. The next valid message marks it online.
        """
        now = now or datetime.now(UTC)
        for pump_id, a in self.availability.items():
            if a["online"] and a["last_seen_at"] and now - _parse(a["last_seen_at"]) > STALE_AFTER:
                a["online"] = False
                self.live.send(pump_id, "availability", self.availability_of(pump_id))

    def pump_status(self, pump_id: str) -> dict[str, Any]:
        """PumpStatus from docs/API.md: latest status plus `online` and `received_at`."""
        row = self.conn.execute(
            "SELECT * FROM status_samples WHERE pump_id = ? ORDER BY id DESC LIMIT 1", (pump_id,)
        ).fetchone()
        online = self.availability_of(pump_id)["online"]
        if row is None:
            return {"pump_id": pump_id, "online": False, "received_at": None}
        # The validated message as received, so optional fields pass through (docs/API.md).
        status = json.loads(row["raw"])
        status.pop("uptime_ms", None)
        return {**status, "online": online, "received_at": row["received_at"]}

    def audit_for_pump(self, pump_id: str) -> list[dict[str, Any]]:
        """AuditRow list for one pump, newest first. Covers prescriptions and alarms."""
        prefix = f"{pump_id}/"
        rows = self.conn.execute(
            "SELECT * FROM audit WHERE substr(entity_id, 1, ?) = ? ORDER BY id DESC",
            (len(prefix), prefix),
        ).fetchall()
        return [dict(r) for r in rows]

    def snapshot(self, pump_id: str) -> list[tuple[str, Any]]:
        """What a new SSE subscriber gets first, so the page renders without extra requests."""
        events: list[tuple[str, Any]] = [
            ("status", self.pump_status(pump_id)),
            ("availability", self.availability_of(pump_id)),
        ]
        for p in reversed(prescriptions.list_for_pump(self.conn, pump_id)):
            if p["state"] in SNAPSHOT_STATES:
                events.append(("prescription", p))
        events += [("alert", a) for a in alerts.active_for_pump(self.conn, pump_id)]
        return events

    # --- web actions ---

    def broadcast_prescriptions(self, changed: list[dict[str, Any]]) -> None:
        for p in changed:
            self.live.send(p["pump_id"], "prescription", p)

    def broadcast_alerts(self, changed: list[dict[str, Any]]) -> None:
        for a in changed:
            self.live.send(a["pump_id"], "alert", a)

    def propose(self, pump_id: str, **fields: Any) -> dict[str, Any]:
        with transaction(self.conn):
            p = prescriptions.propose(self.conn, pump_id, **fields)
        self.broadcast_prescriptions([p])
        return p

    def confirm(self, pump_id: str, version: int, confirmed_by: str) -> dict[str, Any]:
        with transaction(self.conn):
            changed = prescriptions.confirm(
                self.conn, self.publisher, pump_id, version, confirmed_by
            )
        self.broadcast_prescriptions(changed)
        return changed[-1]

    def decline(
        self, pump_id: str, version: int, declined_by: str, reason: str | None
    ) -> dict[str, Any]:
        with transaction(self.conn):
            p = prescriptions.decline(self.conn, pump_id, version, declined_by, reason)
        self.broadcast_prescriptions([p])
        return p

    def republish_all(self) -> None:
        """R3: on hub start and after every broker (re)connect."""
        for pump_id in self.pump_ids():
            with transaction(self.conn):
                sent = prescriptions.republish_latest(self.conn, self.publisher, pump_id)
            if sent:
                self.broadcast_prescriptions([sent])

    # --- MQTT ingest ---

    def handle_message(self, topic: str, payload: bytes) -> None:
        if topic == CONNECTED:
            self.republish_all()
            return
        with transaction(self.conn):
            self._ingest(topic, payload)

    def _ingest(self, topic: str, payload: bytes) -> None:
        parts = topic.split("/")
        if len(parts) != 3 or parts[0] != "pump":
            log.warning("ignoring unexpected topic %s", topic)
            return
        _, pump_id, kind = parts
        if not self.known_pump(pump_id):
            log.warning("ignoring message from unknown pump %s", pump_id)
            return
        if kind == "availability":
            self._on_availability(pump_id, payload)
            return
        if kind not in ("status", "event"):
            return  # includes our own retained prescription topic

        try:
            message = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            log.warning("dropping non-JSON %s from %s", kind, pump_id)
            return
        problems = protocol.errors(kind, message)
        if problems:
            log.warning("dropping invalid %s from %s: %s", kind, pump_id, problems)
            return
        if message["pump_id"] != pump_id:
            log.warning("dropping %s: topic %s but pump_id %s", kind, pump_id, message["pump_id"])
            return

        received_at = utc_now()
        self._seen(pump_id, received_at)
        if kind == "status":
            self._on_status(message, received_at)
        else:
            self._on_event(message, received_at)

    def _seen(self, pump_id: str, at: str) -> None:
        """Any valid message proves the pump is online."""
        before = self.availability.get(pump_id, {}).get("online")
        self.availability[pump_id] = {"online": True, "last_seen_at": at}
        if not before:
            self.live.send(pump_id, "availability", self.availability_of(pump_id))

    def _on_availability(self, pump_id: str, payload: bytes) -> None:
        text = payload.decode(errors="replace").strip()
        if text not in ("online", "offline"):
            log.warning("dropping availability %r from %s", text, pump_id)
            return
        was_online = self.availability.get(pump_id, {}).get("online")
        last_seen = self.availability.get(pump_id, {}).get("last_seen_at")
        online = text == "online"
        self.availability[pump_id] = {
            "online": online,
            "last_seen_at": utc_now() if online else last_seen,
        }
        if online != was_online:
            self.live.send(pump_id, "availability", self.availability_of(pump_id))
        if online and not was_online:
            # R3: the retained message may be gone after a broker restart; send it again.
            sent = prescriptions.republish_latest(self.conn, self.publisher, pump_id)
            if sent:
                self.broadcast_prescriptions([sent])

    def _on_status(self, status: dict[str, Any], received_at: str) -> None:
        self.conn.execute(
            "INSERT INTO status_samples (pump_id, received_at, uptime_ms, state, rate_ml_hr,"
            " delivered_ml, target_ml, alarm, prescription_version, pending_version,"
            " battery_pct, level_pct, last_rejected_version, last_reject_reason, simulated, raw)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                status["pump_id"], received_at, status["uptime_ms"], status["state"],
                status["rate_ml_hr"], status["delivered_ml"], status["target_ml"],
                status["alarm"], status["prescription_version"], status["pending_version"],
                status.get("battery_pct"), status.get("level_pct"),
                status.get("last_rejected_version"), status.get("last_reject_reason"),
                int(status["simulated"]),
                json.dumps(status),
            ),
        )  # fmt: skip
        self.broadcast_prescriptions(prescriptions.apply_pump_status(self.conn, status))
        self.broadcast_alerts(alerts.apply_pump_status(self.conn, status))
        self.live.send(status["pump_id"], "status", self.pump_status(status["pump_id"]))

    def _on_event(self, event: dict[str, Any], received_at: str) -> None:
        self.conn.execute(
            "INSERT INTO events (pump_id, received_at, uptime_ms, type, version, reason, alarm,"
            " from_state, to_state, simulated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event["pump_id"], received_at, event["uptime_ms"], event["type"],
                event.get("version"), event.get("reason"), event.get("alarm"),
                event.get("from_state"), event.get("to_state"), int(event["simulated"]),
            ),
        )  # fmt: skip
        self.broadcast_prescriptions(prescriptions.apply_pump_event(self.conn, event))
        self.broadcast_alerts(alerts.apply_pump_event(self.conn, event))
        self.live.send(event["pump_id"], "pump_event", {**event, "received_at": received_at})
