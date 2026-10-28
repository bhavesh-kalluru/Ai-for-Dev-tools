"""RouteRelay: transit schedule disruption and ETA API (prototype)."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator

MODES = {"bus", "tram", "rail", "ferry"}
TRIP_STATUSES = {"scheduled", "boarding", "en_route", "completed", "cancelled"}
SEVERITIES = {"info", "minor", "major", "critical"}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return str(uuid4())


class StopInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    offset_minutes: int = Field(ge=0, le=2880)


class RouteInput(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    mode: str = "bus"
    stops: list[StopInput] = Field(min_length=2, max_length=50)

    @model_validator(mode="after")
    def validate_route(self):
        if self.mode not in MODES:
            raise ValueError("Unsupported transit mode")
        offsets = [stop.offset_minutes for stop in self.stops]
        if offsets[0] != 0 or any(b <= a for a, b in zip(offsets, offsets[1:])):
            raise ValueError("Stops must start at minute 0 and have strictly increasing offsets")
        if len({s.name.strip().casefold() for s in self.stops}) != len(self.stops):
            raise ValueError("Stop names must be unique within a route")
        return self


class TripInput(BaseModel):
    route_id: str
    service_date: date
    departure_time: str = Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
    delay_minutes: int = Field(default=0, ge=-60, le=360)


class TripUpdate(BaseModel):
    status: str | None = None
    delay_minutes: int | None = Field(default=None, ge=-60, le=360)
    note: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_update(self):
        if self.status is None and self.delay_minutes is None:
            raise ValueError("Provide a status or delay change")
        if self.status is not None and self.status not in TRIP_STATUSES:
            raise ValueError("Invalid trip status")
        return self


class AlertInput(BaseModel):
    route_id: str
    severity: str = "minor"
    message: str = Field(min_length=5, max_length=500)

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value):
        if value not in SEVERITIES:
            raise ValueError("Invalid alert severity")
        return value


def create_app(db_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="RouteRelay Transit Operations", version="1.0.0")
    database = str(db_path or os.getenv("ROUTERELAY_DB", "routerelay.db"))
    write_lock = Lock()
    clients: set[WebSocket] = set()

    @contextmanager
    def connect():
        db = sqlite3.connect(database, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
        finally:
            db.close()

    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS routes (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS stops (
            id TEXT PRIMARY KEY, route_id TEXT NOT NULL REFERENCES routes(id),
            name TEXT NOT NULL, position INTEGER NOT NULL, offset_minutes INTEGER NOT NULL,
            UNIQUE(route_id, position)
        );
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY, route_id TEXT NOT NULL REFERENCES routes(id),
            service_date TEXT NOT NULL, departure_time TEXT NOT NULL,
            delay_minutes INTEGER NOT NULL, status TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trip_events (
            id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id),
            status TEXT NOT NULL, delay_minutes INTEGER NOT NULL,
            note TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id TEXT PRIMARY KEY, route_id TEXT NOT NULL REFERENCES routes(id),
            severity TEXT NOT NULL, message TEXT NOT NULL, active INTEGER NOT NULL,
            created_at TEXT NOT NULL, resolved_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_trips_route_date ON trips(route_id, service_date);
        CREATE INDEX IF NOT EXISTS idx_alerts_route ON alerts(route_id, active);
        """)
        db.commit()

    def require_route(db, route_id):
        row = db.execute("SELECT * FROM routes WHERE id = ?", (route_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Route not found")
        return dict(row)

    def get_route(db, route_id):
        route = require_route(db, route_id)
        route["stops"] = [dict(r) for r in db.execute(
            "SELECT * FROM stops WHERE route_id = ? ORDER BY position", (route_id,)
        )]
        return route

    def get_trip(db, trip_id):
        row = db.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Trip not found")
        trip = dict(row)
        trip["events"] = [dict(r) for r in db.execute(
            "SELECT * FROM trip_events WHERE trip_id = ? ORDER BY created_at, rowid",
            (trip_id,),
        )]
        return trip

    async def broadcast(event):
        stale = []
        for client in tuple(clients):
            try:
                await client.send_json(event)
            except Exception:
                stale.append(client)
        for client in stale:
            clients.discard(client)

    @app.get("/")
    def dashboard():
        return FileResponse(Path(__file__).with_name("index.html"))

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/routes")
    def list_routes():
        with connect() as db:
            ids = [r["id"] for r in db.execute("SELECT id FROM routes ORDER BY name, id")]
            return [get_route(db, route_id) for route_id in ids]

    @app.post("/api/routes", status_code=201)
    async def create_route(payload: RouteInput):
        route_id, timestamp = uid(), now_utc()
        with write_lock, connect() as db:
            db.execute("INSERT INTO routes VALUES (?, ?, ?, ?)",
                       (route_id, payload.name.strip(), payload.mode, timestamp))
            for index, stop in enumerate(payload.stops):
                db.execute("INSERT INTO stops VALUES (?, ?, ?, ?, ?)",
                           (uid(), route_id, stop.name.strip(), index, stop.offset_minutes))
            db.commit()
            route = get_route(db, route_id)
        await broadcast({"type": "route_created", "route_id": route_id})
        return route

    @app.post("/api/trips", status_code=201)
    async def create_trip(payload: TripInput):
        trip_id, timestamp = uid(), now_utc()
        with write_lock, connect() as db:
            require_route(db, payload.route_id)
            db.execute("INSERT INTO trips VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (trip_id, payload.route_id, payload.service_date.isoformat(),
                        payload.departure_time, payload.delay_minutes, "scheduled", timestamp))
            db.execute("INSERT INTO trip_events VALUES (?, ?, ?, ?, ?, ?)",
                       (uid(), trip_id, "scheduled", payload.delay_minutes, "Trip created", timestamp))
            db.commit()
            trip = get_trip(db, trip_id)
        await broadcast({"type": "trip_created", "route_id": payload.route_id})
        return trip

    @app.get("/api/trips/{trip_id}")
    def trip_detail(trip_id: str):
        with connect() as db:
            return get_trip(db, trip_id)

    @app.patch("/api/trips/{trip_id}")
    async def update_trip(trip_id: str, payload: TripUpdate):
        timestamp = now_utc()
        with write_lock, connect() as db:
            trip = get_trip(db, trip_id)
            if trip["status"] in {"completed", "cancelled"}:
                raise HTTPException(409, "Finalized trips cannot be edited")
            status = payload.status if payload.status is not None else trip["status"]
            delay = payload.delay_minutes if payload.delay_minutes is not None else trip["delay_minutes"]
            db.execute("UPDATE trips SET status = ?, delay_minutes = ?, updated_at = ? WHERE id = ?",
                       (status, delay, timestamp, trip_id))
            db.execute("INSERT INTO trip_events VALUES (?, ?, ?, ?, ?, ?)",
                       (uid(), trip_id, status, delay, payload.note.strip(), timestamp))
            db.commit()
            result = get_trip(db, trip_id)
        await broadcast({"type": "trip_updated", "route_id": result["route_id"]})
        return result

    @app.get("/api/board/{route_id}")
    def arrival_board(route_id: str, service_date: date | None = None):
        selected_date = (service_date or date.today()).isoformat()
        with connect() as db:
            route = get_route(db, route_id)
            trips = [dict(t) for t in db.execute(
                "SELECT * FROM trips WHERE route_id = ? AND service_date = ? ORDER BY departure_time, id",
                (route_id, selected_date),
            )]
            alerts = [dict(a) for a in db.execute(
                "SELECT * FROM alerts WHERE route_id = ? AND active = 1 ORDER BY created_at DESC",
                (route_id,),
            )]
        arrivals = []
        for trip in trips:
            departure = datetime.fromisoformat(trip["service_date"] + "T" + trip["departure_time"])
            for stop in route["stops"]:
                scheduled = departure + timedelta(minutes=stop["offset_minutes"])
                predicted = None if trip["status"] in {"completed", "cancelled"} else (
                    scheduled + timedelta(minutes=trip["delay_minutes"])
                ).isoformat(timespec="minutes")
                arrivals.append({
                    "trip_id": trip["id"], "stop_id": stop["id"], "stop": stop["name"],
                    "status": trip["status"], "delay_minutes": trip["delay_minutes"],
                    "scheduled_at": scheduled.isoformat(timespec="minutes"),
                    "predicted_at": predicted,
                })
        arrivals.sort(key=lambda a: (a["scheduled_at"], a["stop"]))
        return {"route": route, "service_date": selected_date, "trips": trips,
                "arrivals": arrivals, "alerts": alerts}

    @app.post("/api/alerts", status_code=201)
    async def create_alert(payload: AlertInput):
        alert_id, timestamp = uid(), now_utc()
        with write_lock, connect() as db:
            require_route(db, payload.route_id)
            db.execute("INSERT INTO alerts VALUES (?, ?, ?, ?, 1, ?, NULL)",
                       (alert_id, payload.route_id, payload.severity, payload.message.strip(), timestamp))
            db.commit()
            alert = dict(db.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone())
        await broadcast({"type": "alert_created", "route_id": payload.route_id})
        return alert

    @app.post("/api/alerts/{alert_id}/resolve")
    async def resolve_alert(alert_id: str):
        with write_lock, connect() as db:
            alert = db.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
            if alert is None:
                raise HTTPException(404, "Alert not found")
            if not alert["active"]:
                raise HTTPException(409, "Alert already resolved")
            db.execute("UPDATE alerts SET active = 0, resolved_at = ? WHERE id = ?",
                       (now_utc(), alert_id))
            db.commit()
            result = dict(db.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone())
        await broadcast({"type": "alert_resolved", "route_id": result["route_id"]})
        return result

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        clients.add(websocket)
        try:
            await websocket.send_json({"type": "connected"})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(websocket)

    return app


app = create_app()
