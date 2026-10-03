"""The simulator against the shared prescription test cases (firmware/sim parity).

The same file, shared/protocol/cases/prescription_cases.json, is meant to be run
by the firmware's native tests too. If both pass, the two pumps agree on every
case on the wire. See docs/PROTOCOL.md "Shared test cases".
"""

import json
from pathlib import Path

import pytest

from sim import pump_sim
from sim.pump_sim import PumpCore
from sim.test_pump_sim import FakeClock, FakePublisher

PROTOCOL = Path(__file__).resolve().parents[1] / "shared" / "protocol"
DOC = json.loads((PROTOCOL / "cases" / "prescription_cases.json").read_text())
CASES = DOC["cases"]
REASONS = set(
    json.loads((PROTOCOL / "event.schema.json").read_text())["properties"]["reason"]["enum"]
)
OUTCOME_EVENT = {
    "applied": ("prescription_applied", "prescription_version"),
    "queued": ("prescription_queued", "pending_version"),
    "rejected": ("prescription_rejected", "last_rejected_version"),
}


def pump_in(setup: dict) -> tuple[PumpCore, FakePublisher]:
    clock, pub = FakeClock(), FakePublisher()
    core = PumpCore(DOC["pump_id"], publish=pub, clock=clock)
    # current_version: a persisted prescription at 60 mL/hr, 500 mL (the DEMO.md seed).
    assert setup["current_version"] == pump_sim.DEMO_SEED["version"]
    assert core.seed_demo_prescription()
    if setup["state"] in ("running", "paused"):
        assert core.start()
        while core.state == "priming":
            clock.t += 0.5
            core.tick()
        assert core.state == "running"
    if setup["pending_version"] is not None:
        rx = json.loads((PROTOCOL / "examples" / "prescription.json").read_text())
        rx["version"] = setup["pending_version"]
        assert core.handle_prescription(json.dumps(rx)) == "queued"
    if setup["state"] == "paused":
        assert core.toggle_pause()
    assert core.state == setup["state"]
    pub.clear()
    return core, pub


def test_cases_file_is_well_formed():
    assert len(CASES) >= 50
    assert len({c["name"] for c in CASES}) == len(CASES)
    for c in CASES:
        assert c["expect"]["outcome"] in ("applied", "queued", "ignored", "dropped", "rejected")
        assert ("reason" in c["expect"]) == (c["expect"]["outcome"] == "rejected"), c["name"]
        assert c["expect"].get("reason", "malformed") in REASONS, c["name"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_sim_matches_case(case):
    core, pub = pump_in(case["setup"])
    expect = case["expect"]

    result = core.handle_prescription(case["payload"])

    outcome = "rejected" if result in REASONS else result
    assert outcome == expect["outcome"]
    if outcome == "rejected":
        assert result == expect["reason"]

    rx_events = [e for e in pub.events() if e["type"].startswith("prescription_")]
    if outcome in OUTCOME_EVENT:
        event_type, version_field = OUTCOME_EVENT[outcome]
        [event] = rx_events
        assert event["type"] == event_type
        assert event["version"] == expect["status_after"][version_field]
        if outcome == "rejected":
            assert event["reason"] == expect["reason"]
    else:
        assert rx_events == [], "ignored and dropped payloads publish nothing"

    status = core.status()
    for field, value in expect["status_after"].items():
        assert status[field] == value, field
