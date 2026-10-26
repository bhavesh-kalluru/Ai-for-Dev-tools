import pytest
from fastapi.testclient import TestClient
from app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.sqlite")) as test_client:
        yield test_client


def create(client, severity="critical"):
    return client.post("/api/incidents", json={
        "title": "Checkout unavailable",
        "description": "Customers cannot check out",
        "severity": severity,
        "service": "checkout",
    })


def test_health_and_dashboard(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert "PulseOps" in client.get("/").text


def test_create_update_filter_metrics(client):
    response = create(client)
    assert response.status_code == 201
    incident = response.json()
    assert incident["status"] == "investigating"
    assert len(incident["updates"]) == 1
    assert client.get("/api/metrics").json() == {
        "total": 1, "open": 1, "resolved": 0, "critical_open": 1
    }
    assert len(client.get("/api/incidents?status=investigating").json()) == 1
    assert client.get("/api/incidents?service=wrong").json() == []
    result = client.post("/api/incidents/" + incident["id"] + "/updates", json={
        "status": "resolved", "message": "Rollback completed"
    })
    assert result.status_code == 200
    assert len(result.json()["updates"]) == 2
    assert client.get("/api/metrics").json()["resolved"] == 1
    assert client.get("/api/incidents?status=investigating").json() == []


def test_reject_invalid_and_missing(client):
    assert create(client, severity="invalid").status_code == 422
    assert client.post("/api/incidents", json={}).status_code == 422
    assert client.get("/api/incidents/no-such-id").status_code == 404
    assert client.get("/api/incidents?status=invalid").status_code == 422
    assert client.post("/api/incidents/no-such-id/updates", json={
        "status": "resolved", "message": "Done now"
    }).status_code == 404


def test_resolved_cannot_reopen(client):
    incident_id = create(client).json()["id"]
    path = "/api/incidents/" + incident_id + "/updates"
    assert client.post(path, json={"status": "resolved", "message": "Recovered"}).status_code == 200
    assert client.post(path, json={"status": "investigating", "message": "Again"}).status_code == 409


def test_websocket_broadcast(client):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "connected"
        response = create(client)
        event = ws.receive_json()
        assert event["type"] == "incident_created"
        assert event["incident"]["id"] == response.json()["id"]
