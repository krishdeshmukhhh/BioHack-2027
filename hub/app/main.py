"""Smart pump hub (prototype). HTTP and SSE contract: docs/API.md."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hub.app import alerts, prescriptions, reports
from hub.app.live import CLOSE
from hub.app.mqtt_bridge import MqttBridge
from hub.app.prescriptions import LifecycleError
from hub.app.service import Hub

log = logging.getLogger("hub")

WEB_DIR = Path(__file__).resolve().parents[2] / "web"
STALE_CHECK_S = 2.0

LIFECYCLE_STATUS = {
    "unknown_prescription": 404,
    "not_proposed": 409,
    "stale_version": 409,
    "invalid_input": 422,
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail: str) -> None:
        self.status, self.code, self.detail = status, code, detail


class ProposeBody(BaseModel):
    mode: Literal["continuous", "bolus"]
    # Shape only. No limit check here: hard limits live in the pump (S1).
    rate_ml_hr: float = Field(gt=0, allow_inf_nan=False)
    volume_ml: float = Field(gt=0, allow_inf_nan=False)
    note: str = Field(default="", max_length=200)
    proposed_by: str = Field(min_length=1)


class ConfirmBody(BaseModel):
    confirmed_by: str = Field(min_length=1)


class DeclineBody(BaseModel):
    declined_by: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=200)


def create_app(
    hub: Hub | None = None, bridge: MqttBridge | None = None, web_dir: Path = WEB_DIR
) -> FastAPI:
    """Tests pass a Hub with a fake publisher and no bridge; `make hub` builds both from env."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal hub, bridge
        if hub is None:
            bridge = MqttBridge(
                os.environ.get("MQTT_HOST", "localhost"), int(os.environ.get("MQTT_PORT", 1883))
            )
            hub = Hub(
                os.environ.get("HUB_DB_PATH", "hub/data/hub.sqlite3"),
                os.environ.get("PUMP_ID", "pump-001"),
                publisher=bridge,
            )
        app.state.hub = hub
        tasks = []
        if bridge is not None:
            load_history_or_warn(hub)
            queue: asyncio.Queue[tuple[str, bytes]] = asyncio.Queue()
            # The startup re-publish (R3) runs when the bridge reports its first connect.
            bridge.start(asyncio.get_running_loop(), queue)
            tasks.append(asyncio.create_task(_consume(hub, queue)))
            tasks.append(asyncio.create_task(_watch_stale(hub)))
        yield
        for task in tasks:
            task.cancel()
        if bridge is not None:
            bridge.stop()

    app = FastAPI(title="Smart Pump Hub (prototype)", lifespan=lifespan)
    if hub is not None:
        app.state.hub = hub

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "detail": exc.detail}, status_code=exc.status)

    @app.exception_handler(LifecycleError)
    async def lifecycle_error(request: Request, exc: LifecycleError) -> JSONResponse:
        status = LIFECYCLE_STATUS.get(exc.code, 400)
        return JSONResponse({"error": exc.code, "detail": exc.detail}, status_code=status)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}" for e in exc.errors()
        )
        return JSONResponse({"error": "invalid_input", "detail": detail}, status_code=422)

    def get_hub(request: Request, pump_id: str) -> Hub:
        h: Hub = request.app.state.hub
        if not h.known_pump(pump_id):
            raise ApiError(404, "unknown_pump", f"no pump {pump_id}")
        return h

    def hub_for_patient(request: Request, patient_id: str) -> Hub:
        h: Hub = request.app.state.hub
        if not reports.known_patient(h.conn, patient_id):
            raise ApiError(404, "unknown_patient", f"no patient {patient_id}")
        return h

    # Handlers are async so all database access stays on the event loop thread.

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/pumps/{pump_id}/status")
    async def pump_status(request: Request, pump_id: str) -> dict:
        return get_hub(request, pump_id).pump_status(pump_id)

    @app.get("/api/pumps/{pump_id}/prescriptions")
    async def list_prescriptions(request: Request, pump_id: str) -> list[dict]:
        h = get_hub(request, pump_id)
        return prescriptions.list_for_pump(h.conn, pump_id)

    @app.post("/api/pumps/{pump_id}/prescriptions")
    async def propose(request: Request, pump_id: str, body: ProposeBody) -> dict:
        return get_hub(request, pump_id).propose(pump_id, **body.model_dump())

    @app.post("/api/pumps/{pump_id}/prescriptions/{version}/confirm")
    async def confirm(request: Request, pump_id: str, version: int, body: ConfirmBody) -> dict:
        return get_hub(request, pump_id).confirm(pump_id, version, body.confirmed_by)

    @app.post("/api/pumps/{pump_id}/prescriptions/{version}/decline")
    async def decline(request: Request, pump_id: str, version: int, body: DeclineBody) -> dict:
        h = get_hub(request, pump_id)
        return h.decline(pump_id, version, body.declined_by, body.reason)

    @app.get("/api/pumps/{pump_id}/alerts")
    async def list_alerts(request: Request, pump_id: str) -> list[dict]:
        return alerts.list_for_pump(get_hub(request, pump_id).conn, pump_id)

    @app.get("/api/pumps/{pump_id}/audit")
    async def list_audit(request: Request, pump_id: str) -> list[dict]:
        return get_hub(request, pump_id).audit_for_pump(pump_id)

    @app.get("/api/patients")
    async def list_patients(request: Request) -> list[dict]:
        h: Hub = request.app.state.hub
        return reports.patients(h.conn, h.is_online)

    @app.get("/api/patients/{patient_id}/daily")
    async def patient_daily(
        request: Request, patient_id: str, days: int = Query(default=30, ge=1, le=90)
    ) -> list[dict]:
        return reports.daily(hub_for_patient(request, patient_id).conn, patient_id, days)

    @app.get("/api/patients/{patient_id}/summary")
    async def patient_summary(request: Request, patient_id: str) -> dict:
        return reports.weekly_summary(hub_for_patient(request, patient_id).conn, patient_id)

    @app.get("/api/patients/{patient_id}/profiles")
    async def patient_profiles(request: Request, patient_id: str) -> list[dict]:
        return reports.profiles(hub_for_patient(request, patient_id).conn, patient_id)

    @app.get("/api/pumps/{pump_id}/stream", response_class=EventSourceResponse)
    async def stream(request: Request, pump_id: str) -> AsyncIterator[ServerSentEvent]:
        h = get_hub(request, pump_id)
        queue = h.live.subscribe(pump_id)
        try:
            for event, data in h.snapshot(pump_id):
                yield ServerSentEvent(event=event, data=data)
            while True:
                event, data = await queue.get()
                if event == CLOSE:
                    return
                yield ServerSentEvent(event=event, data=data)
        finally:
            h.live.unsubscribe(pump_id, queue)

    # Web apps, mounted last so the API routes win. Both apps import from /shared/.
    for prefix in ("shared", "clinician", "family"):
        if (web_dir / prefix).is_dir():
            app.mount(f"/{prefix}", StaticFiles(directory=web_dir / prefix, html=True))
    if (web_dir / "family").is_dir():
        app.mount("/", StaticFiles(directory=web_dir / "family", html=True))

    return app


def load_history_or_warn(hub: Hub) -> None:
    """A bad history file costs the dashboard, never the hub: the loop matters more."""
    try:
        if not hub.load_history():
            log.warning("no %s; run `make history` for the dashboard", reports.HISTORY_FILE)
    except Exception:
        log.exception("could not load %s; continuing without history", reports.HISTORY_FILE)


async def _consume(hub: Hub, queue: asyncio.Queue[tuple[str, bytes]]) -> None:
    while True:
        topic, payload = await queue.get()
        try:
            hub.handle_message(topic, payload)
        except Exception:
            log.exception("error handling %s", topic)  # one bad message must not stop ingest


async def _watch_stale(hub: Hub) -> None:
    while True:
        await asyncio.sleep(STALE_CHECK_S)
        try:
            hub.check_stale()
        except Exception:
            log.exception("stale check failed")


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
app = create_app()
