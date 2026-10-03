"""MOCK hub for the web lane. Prototype and demo only, not a medical device.

A standard-library stand-in for the hub so the web apps never wait on the hub
lane. It serves `web/` and fakes every endpoint and the SSE stream in
`docs/API.md`. Behind the fake API sit real simulated pumps (`sim.pump_sim.PumpCore`),
so validation, rejection reasons, queueing and alarms behave exactly as on the
wire. The mock follows the same rules the hub must:

- prescriptions reach a pump only after a caregiver confirmation (S2);
- `active`, `rejected` and `superseded` are set only from pump events or status (S5);
- the audit list only grows (S7);
- everything it serves is labelled simulated (S8).

Run from the repo root:

    python web/_mock/mock_api.py              # http://localhost:8003
    python web/_mock/mock_api.py --speed 60   # feeds run 60x faster

Pages: `/family/` (and `/`) family app, `/clinician/` portal, `/_mock/` controls (start feed,
faults, wifi drop). The `/_mock/` routes are mock-only and not part of the contract.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import queue
import sys
import threading
import time
from datetime import UTC, date, datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

WEB = Path(__file__).resolve().parent.parent
ROOT = WEB.parent
sys.path.insert(0, str(ROOT))

from sim import generate_history  # noqa: E402
from sim.pump_sim import ALARMS, MODES, PumpCore  # noqa: E402

USERS = {
    "clin-01": "clinician",
    "care-01": "parent",
    "care-02": "school_nurse",
}
FINAL_STATES = ("active", "rejected", "superseded")
OPEN_STATES = ("proposed", "confirmed", "sent")
OFFLINE_AFTER_S = 10.0
DELIVERY_DELAY_S = 1.0  # so the chip visibly shows Sent before the pump answers
KEEPALIVE_S = 15.0
NOTE_MAX = 200


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_positive_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value  # not NaN
        and value not in (float("inf"), float("-inf"))
        and value > 0
    )


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


class Pump:
    """One simulated pump plus the hub-side records about it."""

    def __init__(self, hub: MockHub, pump_id: str, speed: float) -> None:
        self.hub = hub
        self.pump_id = pump_id
        self.link_up = True
        self.core = PumpCore(pump_id, self._publish, speed=speed)
        self.core.seed_demo_prescription()
        self.status: dict[str, Any] | None = None
        self.availability_online = True
        self.last_seen_at: str | None = None
        self.last_seen_mono: float | None = None
        self.prescriptions: dict[int, dict[str, Any]] = {}
        self.alerts: list[dict[str, Any]] = []
        self.subscribers: list[queue.Queue] = []
        seed = self.core.prescription or {}
        if seed:
            self.prescriptions[seed["version"]] = {
                "pump_id": pump_id, "version": seed["version"], "mode": seed["mode"],
                "rate_ml_hr": seed["rate_ml_hr"], "volume_ml": seed["volume_ml"],
                "note": "", "state": "active", "reject_reason": None,
                "proposed_by": "clin-01", "proposed_at": seed["confirmed_at"],
                "confirmed_by": seed["confirmed_by"],
                "confirmed_role": USERS[seed["confirmed_by"]],
                "confirmed_at": seed["confirmed_at"], "sent_at": seed["confirmed_at"],
                "resolved_at": seed["confirmed_at"],
            }

    def _publish(self, topic: str, payload: str) -> None:
        # Called by PumpCore under its own lock. Hand off; never touch hub state here.
        if self.link_up:
            self.hub.inbox.put((self.pump_id, topic, payload))

    @property
    def online(self) -> bool:
        if not self.availability_online or self.last_seen_mono is None:
            return False
        return time.monotonic() - self.last_seen_mono <= OFFLINE_AFTER_S

    def availability(self) -> dict[str, Any]:
        return {"pump_id": self.pump_id, "online": self.online, "last_seen_at": self.last_seen_at}

    def status_view(self) -> dict[str, Any]:
        base = self.status or {
            "pump_id": self.pump_id, "state": "idle", "rate_ml_hr": 0, "delivered_ml": 0,
            "target_ml": 0, "alarm": None, "prescription_version": 0,
            "pending_version": None, "simulated": True, "received_at": None,
        }
        view = {k: v for k, v in base.items() if k != "uptime_ms"}
        view["online"] = self.online
        return view

    def latest_version(self) -> int:
        return max(self.prescriptions, default=0)


class MockHub:
    def __init__(self, speed: float) -> None:
        self.lock = threading.RLock()
        self.inbox: queue.Queue = queue.Queue()
        self.audit: list[dict[str, Any]] = []
        self.pumps = {pid: Pump(self, pid, speed) for pid in ("pump-001", "pump-002", "pump-003")}
        self.history = self._load_history()
        self._stop = threading.Event()

    # ---- history ---------------------------------------------------------

    @staticmethod
    def _load_history() -> dict[str, Any]:
        path = ROOT / "sim" / "data" / "history.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except ValueError:
                pass
        return generate_history.generate(end_date=datetime.now(UTC).date())

    # ---- threads ---------------------------------------------------------

    def start(self) -> None:
        threading.Thread(target=self._tick_loop, daemon=True).start()
        threading.Thread(target=self._ingest_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _tick_loop(self) -> None:
        was_online = {pid: False for pid in self.pumps}
        while not self._stop.is_set():
            for pump in self.pumps.values():
                pump.core.tick()
            with self.lock:
                for pid, pump in self.pumps.items():
                    if pump.online != was_online[pid]:
                        was_online[pid] = pump.online
                        self._broadcast(pump, "availability", pump.availability())
            time.sleep(0.2)

    def _ingest_loop(self) -> None:
        while not self._stop.is_set():
            try:
                pump_id, topic, payload = self.inbox.get(timeout=0.5)
            except queue.Empty:
                continue
            with self.lock:
                self._ingest(self.pumps[pump_id], topic, json.loads(payload))

    # ---- pump to hub (what the real hub's MQTT bridge does) -------------

    def _ingest(self, pump: Pump, topic: str, msg: dict[str, Any]) -> None:
        received_at = now_iso()
        came_online = not pump.online
        pump.last_seen_at = received_at
        pump.last_seen_mono = time.monotonic()
        if came_online:
            self._broadcast(pump, "availability", pump.availability())
            self._redeliver(pump)
        if topic.endswith("/status"):
            pump.status = dict(msg, received_at=received_at)
            self._fold_status(pump, msg)
            self._broadcast(pump, "status", pump.status_view())
        elif topic.endswith("/event"):
            self._fold_event(pump, msg)
            self._broadcast(pump, "pump_event", dict(msg, received_at=received_at))

    def _fold_status(self, pump: Pump, msg: dict[str, Any]) -> None:
        # S5: the version the pump reports is the only proof of "active".
        version = msg.get("prescription_version") or 0
        rx = pump.prescriptions.get(version)
        if rx and rx["state"] == "sent":
            self._activate(pump, version)
        # R1: rejection repeated in telemetry, in case the event was lost.
        rejected = msg.get("last_rejected_version")
        rx = pump.prescriptions.get(rejected) if rejected else None
        if rx and rx["state"] == "sent" and msg.get("last_reject_reason"):
            self._resolve(pump, rx, "rejected", msg["last_reject_reason"])

    def _fold_event(self, pump: Pump, msg: dict[str, Any]) -> None:
        kind = msg["type"]
        if kind == "prescription_applied":
            self._activate(pump, msg["version"])
        elif kind == "prescription_rejected":
            rx = pump.prescriptions.get(msg["version"])
            if rx and rx["state"] == "sent":
                self._resolve(pump, rx, "rejected", msg["reason"])
        elif kind == "prescription_queued":
            # R6: an older version still waiting is replaced by this one.
            for rx in pump.prescriptions.values():
                if rx["state"] == "sent" and rx["version"] < msg["version"]:
                    self._resolve(pump, rx, "superseded", None)
        elif kind == "alarm_raised":
            alert = {"pump_id": pump.pump_id, "alarm": msg["alarm"], "active": True,
                     "raised_at": now_iso(), "cleared_at": None}
            pump.alerts.insert(0, alert)
            self._broadcast(pump, "alert", alert)
        elif kind == "alarm_cleared":
            for alert in pump.alerts:
                if alert["active"] and alert["alarm"] == msg["alarm"]:
                    alert["active"] = False
                    alert["cleared_at"] = now_iso()
                    self._broadcast(pump, "alert", alert)

    def _activate(self, pump: Pump, version: int) -> None:
        rx = pump.prescriptions.get(version)
        if not rx or rx["state"] != "sent":
            return
        self._resolve(pump, rx, "active", None)
        for other in pump.prescriptions.values():
            if other["version"] < version and other["state"] in ("active", "sent"):
                self._resolve(pump, other, "superseded", None)

    def _resolve(self, pump: Pump, rx: dict[str, Any], state: str, reason: str | None) -> None:
        old = rx["state"]
        rx["state"] = state
        rx["reject_reason"] = reason
        rx["resolved_at"] = now_iso()
        self._audit("pump", "pump", rx, state, old, state)
        self._broadcast(pump, "prescription", rx)

    # ---- hub to pump -----------------------------------------------------

    def _publish_gate(self, pump: Pump, rx: dict[str, Any]) -> None:
        """The only way a prescription reaches a pump. Refuses anything unconfirmed (S2)."""
        if not rx.get("confirmed_by") or not rx.get("confirmed_at"):
            raise ApiError(HTTPStatus.CONFLICT, "not_confirmed", "No caregiver confirmation.")
        wire = {k: rx[k] for k in (
            "pump_id", "version", "mode", "rate_ml_hr", "volume_ml",
            "proposed_by", "proposed_at", "confirmed_by", "confirmed_at",
        )}
        if rx.get("note"):
            wire["note"] = rx["note"]
        old = rx["state"]
        rx["state"] = "sent"
        rx["sent_at"] = now_iso()
        self._audit("hub", "system", rx, "sent", old, "sent")
        self._broadcast(pump, "prescription", rx)

        def deliver() -> None:
            if pump.link_up:  # offline: stays sent; redelivered when the pump returns
                pump.core.handle_prescription(json.dumps(wire))

        threading.Timer(DELIVERY_DELAY_S, deliver).start()

    def _redeliver(self, pump: Pump) -> None:
        """R3: re-publish the latest sent prescription when the pump comes back."""
        sent = [rx for rx in pump.prescriptions.values() if rx["state"] == "sent"]
        if sent:
            rx = max(sent, key=lambda r: r["version"])
            wire = {k: rx[k] for k in (
                "pump_id", "version", "mode", "rate_ml_hr", "volume_ml",
                "proposed_by", "proposed_at", "confirmed_by", "confirmed_at",
            )}
            threading.Timer(
                DELIVERY_DELAY_S, pump.core.handle_prescription, args=(json.dumps(wire),)
            ).start()

    # ---- audit and fan-out ----------------------------------------------

    def _audit(
        self, actor: str, role: str, rx: dict[str, Any], action: str, old: Any, new: Any
    ) -> None:
        self.audit.append({
            "id": len(self.audit) + 1, "at": now_iso(), "actor": actor, "actor_role": role,
            "entity": "prescription", "entity_id": f"{rx['pump_id']}/{rx['version']}",
            "action": action, "old_value": old, "new_value": new,
        })

    def _broadcast(self, pump: Pump, event: str, data: dict[str, Any]) -> None:
        for q in list(pump.subscribers):
            q.put((event, json.loads(json.dumps(data))))

    # ---- API operations --------------------------------------------------

    def pump(self, pump_id: str) -> Pump:
        pump = self.pumps.get(pump_id)
        if pump is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "unknown_pump", f"No pump {pump_id}.")
        return pump

    def prescription(self, pump: Pump, version: str) -> dict[str, Any]:
        rx = pump.prescriptions.get(int(version)) if version.isdigit() else None
        if rx is None:
            raise ApiError(HTTPStatus.NOT_FOUND, "unknown_prescription", "No such version.")
        return rx

    def propose(self, pump: Pump, body: dict[str, Any]) -> dict[str, Any]:
        # Shape only. No limit check: S1 lives in the pump (FR-2).
        problems = []
        if body.get("mode") not in MODES:
            problems.append("mode")
        for field in ("rate_ml_hr", "volume_ml"):
            if not is_positive_number(body.get(field)):
                problems.append(field)
        note = body.get("note", "")
        if not isinstance(note, str) or len(note) > NOTE_MAX:
            problems.append("note")
        if USERS.get(body.get("proposed_by")) != "clinician":
            problems.append("proposed_by")
        if problems:
            raise ApiError(422, "invalid_input", "Check: " + ", ".join(problems))
        version = pump.latest_version() + 1
        rx = {
            "pump_id": pump.pump_id, "version": version, "mode": body["mode"],
            "rate_ml_hr": body["rate_ml_hr"], "volume_ml": body["volume_ml"], "note": note,
            "state": "proposed", "reject_reason": None,
            "proposed_by": body["proposed_by"], "proposed_at": now_iso(),
            "confirmed_by": None, "confirmed_role": None, "confirmed_at": None,
            "sent_at": None, "resolved_at": None,
        }
        pump.prescriptions[version] = rx
        self._audit(body["proposed_by"], "clinician", rx, "proposed", None, "proposed")
        self._broadcast(pump, "prescription", rx)
        return rx

    def confirm(self, pump: Pump, rx: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        who = body.get("confirmed_by")
        role = USERS.get(who)
        if role not in ("parent", "school_nurse"):
            raise ApiError(422, "invalid_input", "confirmed_by must be a caregiver.")
        if rx["state"] != "proposed":
            raise ApiError(HTTPStatus.CONFLICT, "not_proposed", f"State is {rx['state']}.")
        rx.update(state="confirmed", confirmed_by=who, confirmed_role=role,
                  confirmed_at=now_iso())
        self._audit(who, role, rx, "confirmed", "proposed", "confirmed")
        self._broadcast(pump, "prescription", rx)
        self._publish_gate(pump, rx)
        return rx

    def decline(self, pump: Pump, rx: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
        who = body.get("declined_by")
        role = USERS.get(who)
        if role not in ("parent", "school_nurse"):
            raise ApiError(422, "invalid_input", "declined_by must be a caregiver.")
        if rx["state"] != "proposed":
            raise ApiError(HTTPStatus.CONFLICT, "not_proposed", f"State is {rx['state']}.")
        rx.update(state="rejected", reject_reason="declined", resolved_at=now_iso())
        self._audit(who, role, rx, "declined", "proposed", "rejected")
        self._broadcast(pump, "prescription", rx)
        return rx

    def patients(self) -> list[dict[str, Any]]:
        rows = []
        for p in self.history["patients"]:
            pump = self.pumps.get(p["pump_id"])
            online = bool(pump and pump.online)
            exceptions = []
            if not online:
                exceptions.append("offline")
            daily = [d for d in self.history["daily"] if d["patient_id"] == p["id"]][-3:]
            if len(daily) == 3 and all(d["delivered_ml"] < 0.9 * d["prescribed_ml"] for d in daily):
                exceptions.append("under_target")
            if self._night_alarm_count(p["id"]) > 2:
                exceptions.append("night_alarms")
            rows.append({"id": p["id"], "display_name": p["display_name"],
                         "pump_id": p["pump_id"], "exceptions": exceptions,
                         "online": online, "simulated": True})
        rows.sort(key=lambda r: (not r["exceptions"], r["id"]))
        return rows

    def _night_alarm_count(self, patient_id: str) -> int:
        end = date.fromisoformat(self.history["generated_for_end_date"])
        start = datetime(end.year, end.month, end.day, tzinfo=UTC) - timedelta(hours=2)
        stop = start + timedelta(hours=8)
        count = 0
        for a in self.history["alarms"]:
            if a["patient_id"] != patient_id:
                continue
            raised = datetime.fromisoformat(a["raised_at"].replace("Z", "+00:00"))
            if start <= raised < stop:
                count += 1
        return count

    def daily(self, patient_id: str, days: int) -> list[dict[str, Any]]:
        if not any(p["id"] == patient_id for p in self.history["patients"]):
            raise ApiError(HTTPStatus.NOT_FOUND, "unknown_patient", f"No patient {patient_id}.")
        rows = [d for d in self.history["daily"] if d["patient_id"] == patient_id][-days:]
        return [{k: d[k] for k in ("date", "delivered_ml", "prescribed_ml", "alarm_count",
                                   "simulated")} for d in rows]

    def snapshot(self, pump: Pump) -> list[tuple[str, dict[str, Any]]]:
        events = [("status", pump.status_view()), ("availability", pump.availability())]
        for v in sorted(pump.prescriptions):
            if pump.prescriptions[v]["state"] in OPEN_STATES:
                events.append(("prescription", pump.prescriptions[v]))
        return [(e, json.loads(json.dumps(d))) for e, d in events]

    # ---- mock-only controls (what a caregiver or fault does at the pump) ---

    def control(self, pump: Pump, action: str) -> dict[str, Any]:
        core = pump.core
        if action == "start":
            ok = core.start()
        elif action == "pause":
            ok = core.toggle_pause()
        elif action == "clear":
            ok = core.clear_alarm()
        elif action in ALARMS:
            ok = core.raise_alarm(action)
        elif action == "offline":
            ok = pump.link_up
            pump.link_up = False
            with self.lock:
                pump.availability_online = False
                self._broadcast(pump, "availability", pump.availability())
        elif action == "online":
            ok = not pump.link_up
            with self.lock:
                pump.link_up = True
                pump.availability_online = True
            core.publish_status()
        else:
            raise ApiError(HTTPStatus.NOT_FOUND, "unknown_action", action)
        return {"ok": ok, "state": core.state, "simulated": True}


class Handler(BaseHTTPRequestHandler):
    hub: MockHub
    server_version = "SmartPumpMock/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        if "/stream" not in self.path:
            sys.stderr.write("mock: " + fmt % args + "\n")

    # ---- plumbing --------------------------------------------------------

    def _send_json(self, status: int, data: Any) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _cors(self) -> None:
        # Lets a page served by the hub (another port) use the mock while USE_MOCK is on.
        self.send_header("Access-Control-Allow-Origin", "*")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError as exc:
            raise ApiError(422, "invalid_input", "Body is not JSON.") from exc
        if not isinstance(data, dict):
            raise ApiError(422, "invalid_input", "Body must be an object.")
        return data

    def _dispatch(self, method: str) -> None:
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        try:
            if parts[:1] == ["api"] or parts[:1] == ["_mock"] and method == "POST":
                self._api(method, parts, parse_qs(url.query))
            elif url.path == "/health":
                self._send_json(200, {"status": "ok"})
            elif method == "GET":
                self._static(url.path)
            else:
                raise ApiError(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", method)
        except ApiError as err:
            self._send_json(err.status, {"error": err.code, "detail": err.detail})

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    # ---- static files ----------------------------------------------------

    def _static(self, path: str) -> None:
        if path.startswith("/clinician"):
            base, rest = WEB / "clinician", path[len("/clinician"):]
        elif path.startswith("/shared/"):
            base, rest = WEB / "shared", path[len("/shared"):]
        elif path.startswith("/_mock"):
            base, rest = WEB / "_mock", path[len("/_mock"):]
        elif path.startswith("/family"):
            base, rest = WEB / "family", path[len("/family"):]
        else:  # docs/API.md also serves the family app at /
            base, rest = WEB / "family", path
        if path in ("/clinician", "/_mock", "/family"):
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", path + "/")
            self.end_headers()
            return
        target = (base / rest.lstrip("/")).resolve()
        if target.is_dir():
            target = target / "index.html"
        if base.resolve() not in target.parents or not target.is_file() or target.suffix == ".py":
            raise ApiError(HTTPStatus.NOT_FOUND, "not_found", path)
        body = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---- API routes ------------------------------------------------------

    def _api(self, method: str, parts: list[str], query: dict[str, list[str]]) -> None:
        hub = self.hub
        if parts[0] == "_mock":  # POST /_mock/pumps/{id}/{action}
            if len(parts) == 4 and parts[1] == "pumps":
                self._send_json(200, hub.control(hub.pump(parts[2]), parts[3]))
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "not_found", "/".join(parts))

        if parts == ["api", "patients"] and method == "GET":
            with hub.lock:
                self._send_json(200, hub.patients())
            return
        if len(parts) == 4 and parts[:2] == ["api", "patients"] and parts[3] == "daily":
            raw = (query.get("days") or ["30"])[0]
            days = int(raw) if raw.isdigit() else 30
            self._send_json(200, hub.daily(parts[2], max(1, min(days, 90))))
            return
        if len(parts) < 4 or parts[1] != "pumps":
            raise ApiError(HTTPStatus.NOT_FOUND, "not_found", "/".join(parts))

        pump = hub.pump(parts[2])
        tail = parts[3:]
        if method == "GET" and tail == ["stream"]:
            self._stream(pump)
            return
        with hub.lock:
            if method == "GET" and tail == ["status"]:
                self._send_json(200, pump.status_view())
            elif method == "GET" and tail == ["prescriptions"]:
                rows = sorted(pump.prescriptions.values(), key=lambda r: -r["version"])
                self._send_json(200, rows)
            elif method == "POST" and tail == ["prescriptions"]:
                self._send_json(200, hub.propose(pump, self._body()))
            elif method == "POST" and len(tail) == 3 and tail[0] == "prescriptions":
                rx = hub.prescription(pump, tail[1])
                if tail[2] == "confirm":
                    self._send_json(200, hub.confirm(pump, rx, self._body()))
                elif tail[2] == "decline":
                    self._send_json(200, hub.decline(pump, rx, self._body()))
                else:
                    raise ApiError(HTTPStatus.NOT_FOUND, "not_found", tail[2])
            elif method == "GET" and tail == ["alerts"]:
                rows = sorted(pump.alerts, key=lambda a: not a["active"])
                self._send_json(200, rows)
            elif method == "GET" and tail == ["audit"]:
                prefix = pump.pump_id + "/"
                rows = [a for a in reversed(hub.audit) if a["entity_id"].startswith(prefix)]
                self._send_json(200, rows)
            else:
                raise ApiError(HTTPStatus.NOT_FOUND, "not_found", "/".join(parts))

    def _stream(self, pump: Pump) -> None:
        q: queue.Queue = queue.Queue()
        with self.hub.lock:
            for item in self.hub.snapshot(pump):
                q.put(item)
            pump.subscribers.append(q)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()
        try:
            while True:
                try:
                    event, data = q.get(timeout=KEEPALIVE_S)
                    chunk = f"event: {event}\ndata: {json.dumps(data)}\n\n"
                except queue.Empty:
                    chunk = ": keep-alive\n\n"
                self.wfile.write(chunk.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            with self.hub.lock:
                if q in pump.subscribers:
                    pump.subscribers.remove(q)


def make_server(
    port: int, speed: float, host: str = "0.0.0.0"
) -> tuple[ThreadingHTTPServer, MockHub]:
    hub = MockHub(speed)
    handler = type("BoundHandler", (Handler,), {"hub": hub})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    hub.start()
    return server, hub


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Mock hub for the web lane (SIMULATED).")
    parser.add_argument("--port", type=int, default=8003)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--speed", type=float, default=60.0,
                        help="simulated time factor for feeds (default 60)")
    args = parser.parse_args(argv)
    server, hub = make_server(args.port, args.speed, args.host)
    print(f"mock hub (SIMULATED) on http://localhost:{args.port}/  "
          f"portal /clinician/  controls /_mock/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hub.stop()
        server.server_close()


if __name__ == "__main__":
    main()
