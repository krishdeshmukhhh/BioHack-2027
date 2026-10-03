"""The DEMO.md loop end to end against the real simulator core, with no broker.

The hub's publisher hands prescriptions to sim.pump_sim.PumpCore, and the pump's
publishes go straight into the hub's ingest path, as the broker would deliver them.
"""

import pytest
from fastapi.testclient import TestClient

from hub.app.main import create_app
from hub.app.service import Hub
from hub.tests.helpers import PUMP
from sim.pump_sim import PumpCore


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class Wire:
    """Stands in for the broker between one hub and one simulated pump."""

    def __init__(self) -> None:
        self.hub: Hub | None = None
        self.core: PumpCore | None = None
        self.in_flight: list[str] = []

    def publish(self, topic: str, payload: str, qos: int, retain: bool) -> bool:  # hub side
        # Delivered on the next tick, never inside the hub's call, as with a real broker.
        assert topic == f"pump/{PUMP}/prescription" and qos == 1 and retain
        self.in_flight.append(payload)
        return True

    def deliver(self) -> None:
        assert self.core is not None
        while self.in_flight:
            self.core.handle_prescription(self.in_flight.pop(0))

    def from_pump(self, topic: str, payload: str) -> None:  # pump side
        assert self.hub is not None
        self.hub.handle_message(topic, payload.encode())


@pytest.fixture
def loop():
    clock, wire = Clock(), Wire()
    wire.hub = Hub(":memory:", PUMP, publisher=wire)
    wire.core = PumpCore(PUMP, publish=wire.from_pump, clock=clock, speed=600)
    wire.from_pump(f"pump/{PUMP}/availability", "online")
    client = TestClient(create_app(hub=wire.hub))

    def run(seconds: float) -> None:
        end = clock.t + seconds
        while clock.t < end:
            clock.t += 0.5
            wire.deliver()
            wire.core.tick()

    run(3)
    return client, wire, run


def propose(client, rate):
    body = {"mode": "continuous", "rate_ml_hr": rate, "volume_ml": 500, "proposed_by": "clin-01"}
    return client.post(f"/api/pumps/{PUMP}/prescriptions", json=body).json()


def confirm(client, version):
    url = f"/api/pumps/{PUMP}/prescriptions/{version}/confirm"
    return client.post(url, json={"confirmed_by": "care-01"}).json()


def state(client, version):
    rows = client.get(f"/api/pumps/{PUMP}/prescriptions").json()
    return next(r for r in rows if r["version"] == version)


def test_demo_script_on_the_sim(loop):
    client, wire, run = loop

    # Steps 3-4: propose 90, confirm, Sent then Active on pump only from the pump.
    v = propose(client, 90)["version"]
    assert state(client, v)["state"] == "proposed"
    assert confirm(client, v)["state"] == "sent"
    run(3)
    assert state(client, v)["state"] == "active"
    status = client.get(f"/api/pumps/{PUMP}/status").json()
    assert status["prescription_version"] == v and status["rate_ml_hr"] in (0, 90)

    # Step 5: out of range is refused by the pump, not the hub.
    bad = propose(client, 500)["version"]
    confirm(client, bad)
    run(3)
    rejected = state(client, bad)
    assert rejected["state"] == "rejected" and rejected["reject_reason"] == "rate_out_of_range"
    assert client.get(f"/api/pumps/{PUMP}/status").json()["prescription_version"] == v

    # Steps 6-8: feed runs, occlusion raises an alert, clearing it ends the alert.
    assert wire.core.start()
    run(10)
    assert client.get(f"/api/pumps/{PUMP}/status").json()["delivered_ml"] > 0
    wire.core.raise_alarm("occlusion")
    run(1)
    alerts = client.get(f"/api/pumps/{PUMP}/alerts").json()
    assert [(a["alarm"], a["active"]) for a in alerts] == [("occlusion", True)]
    wire.core.clear_alarm()
    run(3)
    assert client.get(f"/api/pumps/{PUMP}/alerts").json()[0]["active"] is False

    # Step 10: the audit trail tells the story.
    actions = [r["action"] for r in reversed(client.get(f"/api/pumps/{PUMP}/audit").json())]
    for expected in ("proposed", "confirmed", "sent", "applied_by_pump", "rejected_by_pump",
                     "alarm_raised", "alarm_cleared"):  # fmt: skip
        assert expected in actions


def test_change_during_a_feed_is_queued_then_applied(loop):
    client, wire, run = loop
    first = propose(client, 60)["version"]
    confirm(client, first)
    run(3)
    assert wire.core.start()
    run(5)
    second = propose(client, 90)["version"]
    confirm(client, second)
    run(3)
    # S4: not applied mid-feed, and S5: so not active yet.
    assert state(client, second)["state"] == "sent"
    assert client.get(f"/api/pumps/{PUMP}/status").json()["pending_version"] == second
    run(3600)  # the feed completes and the pump goes idle
    assert state(client, second)["state"] == "active"
    assert state(client, first)["state"] == "superseded"
