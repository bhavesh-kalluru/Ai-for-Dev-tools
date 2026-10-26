"""FastAPI + SQLite real-time incident management service."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

STATUSES = {"investigating", "identified", "monitoring", "resolved"}
SEVERITIES = {"low", "medium", "high", "critical"}


class NewIncident(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=3, max_length=2000)
    severity: str = "medium"
    service: str = Field(min_length=2, max_length=80)


class IncidentUpdate(BaseModel):
    status: str
    message: str = Field(min_length=3, max_length=1000)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def create_app(db_path=None):
    app = FastAPI(title="Live Incident Tracker", version="1.0.0")
    db_file = str(db_path or os.environ.get("INCIDENT_DB", "incidents.db"))
    write_lock = Lock()
    listeners = set()

    @contextmanager
    def connection():
        db = sqlite3.connect(db_file, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def initialize():
        with connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                severity TEXT NOT NULL, service TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS updates (
                id TEXT PRIMARY KEY, incident_id TEXT NOT NULL, status TEXT NOT NULL,
                message TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(incident_id) REFERENCES incidents(id)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_updates_incident ON updates(incident_id, created_at)")
            db.commit()

    initialize()

    def get_incident(incident_id):
        with connection() as db:
            incident = db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
            if incident is None:
                raise HTTPException(404, "Incident not found")
            updates = db.execute(
                "SELECT * FROM updates WHERE incident_id = ? ORDER BY created_at, rowid",
                (incident_id,),
            ).fetchall()
            return {**dict(incident), "updates": [dict(row) for row in updates]}

    async def broadcast(event):
        stale = []
        for client in tuple(listeners):
            try:
                await client.send_json(event)
            except Exception:
                stale.append(client)
        for client in stale:
            listeners.discard(client)

    @app.get("/")
    def dashboard():
        return FileResponse(Path(__file__).with_name("index.html"))

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/incidents")
    def list_incidents(status: str | None = None, service: str | None = None):
        if status and status not in STATUSES:
            raise HTTPException(422, "Invalid status")
        sql, values = "SELECT * FROM incidents WHERE 1=1", []
        if status:
            sql += " AND status = ?"
            values.append(status)
        if service:
            sql += " AND service = ?"
            values.append(service)
        sql += " ORDER BY created_at DESC, rowid DESC"
        with connection() as db:
            return [dict(row) for row in db.execute(sql, values).fetchall()]

    @app.get("/api/incidents/{incident_id}")
    def incident_detail(incident_id: str):
        return get_incident(incident_id)

    @app.get("/api/metrics")
    def metrics():
        with connection() as db:
            total = db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
            open_count = db.execute(
                "SELECT COUNT(*) FROM incidents WHERE status != 'resolved'"
            ).fetchone()[0]
            critical = db.execute(
                "SELECT COUNT(*) FROM incidents WHERE severity = 'critical' AND status != 'resolved'"
            ).fetchone()[0]
        return {"total": total, "open": open_count, "resolved": total - open_count,
                "critical_open": critical}

    @app.post("/api/incidents", status_code=201)
    async def create_incident(payload: NewIncident):
        if payload.severity not in SEVERITIES:
            raise HTTPException(422, "Invalid severity")
        now, incident_id = utc_now(), str(uuid4())
        with write_lock, connection() as db:
            db.execute(
                """INSERT INTO incidents
                (id, title, description, severity, service, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (incident_id, payload.title, payload.description, payload.severity,
                 payload.service, "investigating", now, now),
            )
            db.execute(
                "INSERT INTO updates VALUES (?, ?, ?, ?, ?)",
                (str(uuid4()), incident_id, "investigating", "Incident reported", now),
            )
            db.commit()
        result = get_incident(incident_id)
        await broadcast({"type": "incident_created", "incident": result})
        return result

    @app.post("/api/incidents/{incident_id}/updates")
    async def update_incident(incident_id: str, payload: IncidentUpdate):
        if payload.status not in STATUSES:
            raise HTTPException(422, "Invalid status")
        now = utc_now()
        with write_lock, connection() as db:
            current = db.execute(
                "SELECT status FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
            if current is None:
                raise HTTPException(404, "Incident not found")
            if current["status"] == "resolved" and payload.status != "resolved":
                raise HTTPException(409, "Resolved incidents cannot be reopened")
            db.execute(
                "UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?",
                (payload.status, now, incident_id),
            )
            db.execute(
                "INSERT INTO updates VALUES (?, ?, ?, ?, ?)",
                (str(uuid4()), incident_id, payload.status, payload.message, now),
            )
            db.commit()
        result = get_incident(incident_id)
        await broadcast({"type": "incident_updated", "incident": result})
        return result

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        listeners.add(websocket)
        try:
            await websocket.send_json({"type": "connected"})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            listeners.discard(websocket)

    return app


app = create_app()
