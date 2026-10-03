from fastapi.testclient import TestClient

from hub.app.main import app


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_web_apps_and_shared_files_are_served(client):
    # The family page imports /shared/*.js; without this mount it renders blank.
    assert client.get("/").status_code == 200
    assert client.get("/shared/core.js").status_code == 200
    assert client.get("/shared/tokens.css").status_code == 200
