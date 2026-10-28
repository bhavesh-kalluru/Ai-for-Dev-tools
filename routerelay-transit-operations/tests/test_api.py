from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.db")) as client:
        yield client


def route(client):
    response = client.post("/api/routes", json={
        "name": "Airport Express", "mode": "bus",
        "stops": [
            {"name": "Central Station", "offset_minutes": 0},
            {"name": "Airport Terminal", "offset_minutes": 35},
        ],
    })
    assert response.status_code == 201, response.text
    return response.json()


def trip(client, route_id, departure="09:30"):
    response = client.post("/api/trips", json={
        "route_id": route_id, "service_date": "2026-11-01",
        "departure_time": departure, "delay_minutes": 10,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_health_dashboard_and_empty_routes(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert "RouteRelay" in client.get("/").text
    assert client.get("/api/routes").json() == []


def test_route_validation(client):
    invalid = {
        "name": "Wrong offsets", "mode": "bus",
        "stops": [{"name": "A stop", "offset_minutes": 1},
                  {"name": "B stop", "offset_minutes": 0}],
    }
    assert client.post("/api/routes", json=invalid).status_code == 422
    invalid["stops"] = [{"name": "Same", "offset_minutes": 0},
                        {"name": "same", "offset_minutes": 20}]
    assert client.post("/api/routes", json=invalid).status_code == 422
    assert len(route(client)["stops"]) == 2


def test_trip_arrivals_with_midnight_rollover(client):
    route_id = route(client)["id"]
    item = trip(client, route_id, "23:50")
    board = client.get(f"/api/board/{route_id}?service_date=2026-11-01").json()
    assert len(board["arrivals"]) == 2
    last = next(a for a in board["arrivals"] if a["stop"] == "Airport Terminal")
    assert last["scheduled_at"] == "2026-11-02T00:25"
    assert last["predicted_at"] == "2026-11-02T00:35"
    assert last["trip_id"] == item["id"]


def test_update_history_and_finalized_trip(client):
    route_id = route(client)["id"]
    item = trip(client, route_id)
    response = client.patch(f"/api/trips/{item['id']}", json={
        "status": "en_route", "delay_minutes": 20, "note": "Road congestion",
    })
    assert response.status_code == 200
    assert len(response.json()["events"]) == 2
    board = client.get(f"/api/board/{route_id}?service_date=2026-11-01").json()
    assert board["arrivals"][0]["predicted_at"] == "2026-11-01T09:50"
    assert client.patch(f"/api/trips/{item['id']}", json={
        "status": "cancelled", "note": "Vehicle unavailable",
    }).status_code == 200
    board = client.get(f"/api/board/{route_id}?service_date=2026-11-01").json()
    assert all(a["predicted_at"] is None for a in board["arrivals"])
    assert client.patch(f"/api/trips/{item['id']}", json={
        "status": "scheduled", "note": "Restart",
    }).status_code == 409


def test_alert_lifecycle(client):
    route_id = route(client)["id"]
    response = client.post("/api/alerts", json={
        "route_id": route_id, "severity": "major",
        "message": "Bridge closed due to maintenance",
    })
    assert response.status_code == 201
    alert = response.json()
    assert len(client.get(f"/api/board/{route_id}").json()["alerts"]) == 1
    assert client.post(f"/api/alerts/{alert['id']}/resolve").status_code == 200
    assert client.get(f"/api/board/{route_id}").json()["alerts"] == []
    assert client.post(f"/api/alerts/{alert['id']}/resolve").status_code == 409


def test_missing_resources_and_bad_input(client):
    assert client.get("/api/board/missing").status_code == 404
    assert client.get("/api/trips/missing").status_code == 404
    assert client.post("/api/trips", json={
        "route_id": "missing", "service_date": "2026-11-01",
        "departure_time": "09:30",
    }).status_code == 404
    route_id = route(client)["id"]
    assert client.post("/api/trips", json={
        "route_id": route_id, "service_date": "2026-11-01",
        "departure_time": "29:99",
    }).status_code == 422
    assert client.post("/api/alerts", json={
        "route_id": route_id, "severity": "severe", "message": "Major closure",
    }).status_code == 422
    assert client.post("/api/alerts/missing/resolve").status_code == 404


def test_websocket_events(client):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "connected"
        item = route(client)
        event = ws.receive_json()
        assert event == {"type": "route_created", "route_id": item["id"]}
        trip(client, item["id"])
        assert ws.receive_json()["type"] == "trip_created"


def test_persistence(tmp_path):
    path = tmp_path / "persist.db"
    with TestClient(create_app(path)) as first:
        route_id = route(first)["id"]
    with TestClient(create_app(path)) as second:
        assert second.get("/api/routes").json()[0]["id"] == route_id
