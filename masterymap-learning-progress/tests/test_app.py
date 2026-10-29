import pytest
from fastapi.testclient import TestClient

from app import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "test.db")) as client:
        yield client


def course(client, name="Physics 101"):
    response = client.post("/api/courses", json={"name": name, "subject": "Science"})
    assert response.status_code == 201
    return response.json()["id"]


def learner(client, course_id, alias="Learner A"):
    return client.post(
        f"/api/courses/{course_id}/learners", json={"alias": alias}
    )


def skill(client, course_id, title="Analyze charts"):
    return client.post(
        f"/api/courses/{course_id}/skills",
        json={"title": title, "description": "Explain a trend"},
    )


def test_health_and_frontend(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 200
    assert "MasteryMap" in client.get("/").text


def test_course_and_empty_dashboard(client):
    cid = course(client)
    assert len(client.get("/api/courses").json()) == 1
    data = client.get(f"/api/courses/{cid}/dashboard").json()
    assert data["metrics"]["mastery_percent"] == 0
    assert data["matrix"] == []
    assert data["skills"] == []


def test_create_learner_and_skill_and_reject_duplicates(client):
    cid = course(client)
    assert learner(client, cid).status_code == 201
    assert skill(client, cid).status_code == 201
    assert learner(client, cid, "learner a").status_code == 409
    assert skill(client, cid, "ANALYZE CHARTS").status_code == 409
    assert learner(client, "missing").status_code == 404


def test_assessment_updates_mastery_and_history(client):
    cid = course(client)
    lid = learner(client, cid).json()["id"]
    sid = skill(client, cid).json()["id"]
    path = "/api/evidence"
    first = client.post(path, json={"learner_id": lid, "skill_id": sid, "score": 45})
    assert first.status_code == 201
    assert first.json()["level"] == "needs_support"
    second = client.post(path, json={"learner_id": lid, "skill_id": sid,
                                     "score": 92, "note": "Retake passed"})
    assert second.status_code == 201
    data = client.get(f"/api/courses/{cid}/dashboard").json()
    assert data["metrics"]["coverage_percent"] == 100
    assert data["metrics"]["mastery_percent"] == 100
    assert data["matrix"][0]["cells"][0] == {
        "skill_id": sid, "score": 92, "level": "mastered"
    }
    assert len(data["recent_evidence"]) == 2


def test_cross_course_assessment_blocked(client):
    c1, c2 = course(client, "Course one"), course(client, "Course two")
    lid = learner(client, c1).json()["id"]
    sid = skill(client, c2).json()["id"]
    response = client.post("/api/evidence", json={
        "learner_id": lid, "skill_id": sid, "score": 90
    })
    assert response.status_code == 422


def test_validation_and_missing_records(client):
    assert client.post("/api/courses", json={
        "name": "  ", "subject": "Math"
    }).status_code == 422
    assert client.get("/api/courses/not-found/dashboard").status_code == 404
    assert client.post("/api/evidence", json={
        "learner_id": "missing", "skill_id": "missing", "score": 50
    }).status_code == 404
    assert client.post("/api/evidence", json={
        "learner_id": "x", "skill_id": "y", "score": 101
    }).status_code == 422


def test_unassessed_and_progressing_levels(client):
    cid = course(client)
    lid = learner(client, cid).json()["id"]
    sid = skill(client, cid).json()["id"]
    data = client.get(f"/api/courses/{cid}/dashboard").json()
    assert data["matrix"][0]["cells"][0]["level"] == "unassessed"
    client.post("/api/evidence", json={"learner_id": lid, "skill_id": sid, "score": 60})
    data = client.get(f"/api/courses/{cid}/dashboard").json()
    assert data["matrix"][0]["cells"][0]["level"] == "progressing"
    assert data["metrics"]["mastery_percent"] == 0


def test_websocket_notifications(client):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "connected"
        cid = course(client)
        event = ws.receive_json()
        assert event == {"type": "course_created", "course_id": cid}


def test_persistence(tmp_path):
    db = tmp_path / "persist.db"
    with TestClient(create_app(db)) as first:
        cid = course(first)
    with TestClient(create_app(db)) as second:
        assert second.get(f"/api/courses/{cid}/dashboard").status_code == 200
