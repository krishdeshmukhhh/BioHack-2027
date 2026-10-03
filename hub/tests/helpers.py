"""Test helpers: fake MQTT publisher, protocol examples, and API shortcuts."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from hub.app.service import Hub

EXAMPLES = Path(__file__).resolve().parents[2] / "shared" / "protocol" / "examples"
PUMP = "pump-001"


class FakePublisher:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict, int, bool]] = []
        self.fail = False

    def publish(self, topic: str, payload: str, qos: int, retain: bool) -> bool:
        if self.fail:
            return False
        self.sent.append((topic, json.loads(payload), qos, retain))
        return True


def example(name: str, **overrides) -> dict:
    """A protocol example message, with the demo pump id and any overrides."""
    message = json.loads((EXAMPLES / f"{name}.json").read_text())
    message["pump_id"] = PUMP
    message.update(overrides)
    return message


def send(hub: Hub, kind: str, message: dict | str) -> None:
    """Deliver an MQTT message to the hub's ingest path, as the bridge would."""
    payload = message if isinstance(message, str) else json.dumps(message)
    hub.handle_message(f"pump/{PUMP}/{kind}", payload.encode())


def propose(client: TestClient, rate: float = 90, volume: float = 500) -> dict:
    body = {"mode": "continuous", "rate_ml_hr": rate, "volume_ml": volume,
            "proposed_by": "clin-01"}  # fmt: skip
    response = client.post(f"/api/pumps/{PUMP}/prescriptions", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client: TestClient, version: int, by: str = "care-01"):
    return client.post(
        f"/api/pumps/{PUMP}/prescriptions/{version}/confirm", json={"confirmed_by": by}
    )
