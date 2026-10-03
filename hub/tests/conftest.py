"""Fixtures: an in-memory hub with a fake MQTT publisher. No broker needed."""

import pytest
from fastapi.testclient import TestClient

from hub.app.main import create_app
from hub.app.service import Hub
from hub.tests.helpers import PUMP, FakePublisher


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def hub(publisher: FakePublisher) -> Hub:
    return Hub(":memory:", PUMP, publisher=publisher)


@pytest.fixture
def client(hub: Hub) -> TestClient:
    return TestClient(create_app(hub=hub))
