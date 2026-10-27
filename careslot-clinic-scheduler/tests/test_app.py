from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'test.sqlite')) as test_client:
        yield test_client


def slot_data(**overrides):
    data = {
        'service': 'Routine check-in',
        'starts_at': (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
        'duration_minutes': 30,
        'capacity': 1,
    }
    data.update(overrides)
    return data


def create_slot(client, **kwargs):
    response = client.post('/api/slots', json=slot_data(**kwargs))
    assert response.status_code == 201, response.text
    return response.json()


def reserve(client, slot_id):
    return client.post(f'/api/slots/{slot_id}/reservations')


def test_health_dashboard_and_initial_metrics(client):
    assert client.get('/api/health').json() == {'status': 'ok'}
    assert 'CareSlot' in client.get('/').text
    assert client.get('/api/metrics').json() == {'slots': 0, 'confirmed': 0, 'waitlisted': 0, 'cancelled': 0}


def test_create_slot_and_service_filter(client):
    slot = create_slot(client)
    assert slot['available'] == 1
    assert len(client.get('/api/slots?service=Routine%20check-in').json()) == 1
    assert client.get('/api/slots?service=Other').json() == []


def test_waitlist_and_automatic_promotion(client):
    slot = create_slot(client)
    first = reserve(client, slot['id']).json()
    second = reserve(client, slot['id']).json()
    third = reserve(client, slot['id']).json()
    assert first['status'] == 'confirmed'
    assert second['status'] == 'waitlisted' and second['queue_position'] == 1
    assert third['queue_position'] == 2
    assert client.get('/api/metrics').json()['waitlisted'] == 2
    cancelled = client.post(f"/api/reservations/{first['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()['promoted']['id'] == second['id']
    assert client.get(f"/api/reservations/{second['id']}").json()['status'] == 'confirmed'
    assert client.get(f"/api/reservations/{third['id']}").json()['queue_position'] == 1
    assert client.get('/api/metrics').json() == {'slots': 1, 'confirmed': 1, 'waitlisted': 1, 'cancelled': 1}
    history = client.get(f"/api/reservations/{second['id']}/history").json()
    assert [row['event'] for row in history] == ['created_waitlisted', 'promoted_to_confirmed']


def test_cancel_waitlisted_does_not_promote(client):
    slot = create_slot(client)
    first = reserve(client, slot['id']).json()
    second = reserve(client, slot['id']).json()
    response = client.post(f"/api/reservations/{second['id']}/cancel")
    assert response.json()['promoted'] is None
    assert client.get(f"/api/reservations/{first['id']}").json()['status'] == 'confirmed'
    assert client.post(f"/api/reservations/{second['id']}/cancel").status_code == 409


def test_input_validation(client):
    assert client.post('/api/slots', json=slot_data(capacity=0)).status_code == 422
    assert client.post('/api/slots', json=slot_data(duration_minutes=5)).status_code == 422
    assert client.post('/api/slots', json=slot_data(starts_at='2020-01-01T10:00:00+00:00')).status_code == 422
    assert client.post('/api/slots', json=slot_data(starts_at='2030-01-01T10:00:00')).status_code == 422
    assert client.post('/api/slots', json=slot_data(service='ab')).status_code == 422


def test_missing_resource(client):
    assert reserve(client, 'missing').status_code == 404
    assert client.get('/api/reservations/missing').status_code == 404
    assert client.get('/api/reservations/missing/history').status_code == 404
    assert client.post('/api/reservations/missing/cancel').status_code == 404


def test_capacity_never_exceeded(client):
    slot = create_slot(client, capacity=2)
    statuses = [reserve(client, slot['id']).json()['status'] for _ in range(5)]
    assert statuses == ['confirmed', 'confirmed', 'waitlisted', 'waitlisted', 'waitlisted']
    state = client.get('/api/slots').json()[0]
    assert state['available'] == 0 and state['confirmed'] == 2 and state['waitlisted'] == 3


def test_websocket_event(client):
    with client.websocket_connect('/ws') as ws:
        assert ws.receive_json()['event'] == 'connected'
        slot = create_slot(client)
        event = ws.receive_json()
        assert event['event'] == 'slot_created' and event['data']['id'] == slot['id']
        reservation = reserve(client, slot['id'])
        assert reservation.status_code == 201
        assert ws.receive_json()['event'] == 'reservation_created'
