"""CareSlot: a demo clinic slot and waitlist scheduler, with no patient data."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator


class SlotInput(BaseModel):
    service: str = Field(min_length=3, max_length=80)
    starts_at: datetime
    duration_minutes: int = Field(ge=10, le=240)
    capacity: int = Field(ge=1, le=20)

    @field_validator("starts_at")
    @classmethod
    def valid_start(cls, value: datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("starts_at must include a timezone offset")
        if value <= datetime.now(timezone.utc):
            raise ValueError("starts_at must be in the future")
        return value


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_app(database_path=None):
    app = FastAPI(title="CareSlot Clinic Scheduler", version="1.0.0")
    path = str(database_path or os.environ.get("CARESLOT_DB", "careslot.db"))
    lock = Lock()
    subscribers = set()

    @contextmanager
    def database():
        db = sqlite3.connect(path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
        finally:
            db.close()

    with database() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS slots (
          id TEXT PRIMARY KEY,
          service TEXT NOT NULL,
          starts_at TEXT NOT NULL,
          duration_minutes INTEGER NOT NULL CHECK(duration_minutes BETWEEN 10 AND 240),
          capacity INTEGER NOT NULL CHECK(capacity BETWEEN 1 AND 20),
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reservations (
          id TEXT PRIMARY KEY,
          slot_id TEXT NOT NULL REFERENCES slots(id),
          status TEXT NOT NULL CHECK(status IN ('confirmed','waitlisted','cancelled')),
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reservation_queue
          ON reservations(slot_id, status, created_at);
        CREATE TABLE IF NOT EXISTS audit_events (
          id TEXT PRIMARY KEY,
          reservation_id TEXT NOT NULL REFERENCES reservations(id),
          event TEXT NOT NULL,
          occurred_at TEXT NOT NULL
        );
        """)
        db.commit()

    def slot_or_404(db, slot_id):
        slot = db.execute("SELECT * FROM slots WHERE id=?", (slot_id,)).fetchone()
        if not slot:
            raise HTTPException(404, "Slot not found")
        return slot

    def reservation_or_404(db, reservation_id):
        item = db.execute("SELECT * FROM reservations WHERE id=?", (reservation_id,)).fetchone()
        if not item:
            raise HTTPException(404, "Reservation not found")
        return item

    def reservation_view(db, reservation_id):
        item = dict(reservation_or_404(db, reservation_id))
        if item["status"] == "waitlisted":
            position = db.execute("""
                SELECT COUNT(*) FROM reservations
                WHERE slot_id=? AND status='waitlisted'
                AND (created_at < ? OR (created_at = ? AND rowid <=
                  (SELECT rowid FROM reservations WHERE id=?)))
            """, (item["slot_id"], item["created_at"], item["created_at"], reservation_id)).fetchone()[0]
            item["queue_position"] = position
        else:
            item["queue_position"] = None
        return item

    def slot_view(db, slot):
        result = dict(slot)
        counts = db.execute("""
          SELECT status, COUNT(*) AS n FROM reservations WHERE slot_id=? GROUP BY status
        """, (slot["id"],)).fetchall()
        totals = {row["status"]: row["n"] for row in counts}
        result["confirmed"] = totals.get("confirmed", 0)
        result["waitlisted"] = totals.get("waitlisted", 0)
        result["available"] = result["capacity"] - result["confirmed"]
        return result

    async def notify(event, payload):
        stale = []
        for websocket in tuple(subscribers):
            try:
                await websocket.send_json({"event": event, "data": payload})
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            subscribers.discard(websocket)

    @app.get("/")
    def home():
        return FileResponse(Path(__file__).with_name("index.html"))

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/slots")
    def list_slots(service: str | None = None):
        with database() as db:
            if service:
                rows = db.execute("SELECT * FROM slots WHERE service=? ORDER BY starts_at, id", (service,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM slots ORDER BY starts_at, id").fetchall()
            return [slot_view(db, row) for row in rows]

    @app.post("/api/slots", status_code=201)
    async def create_slot(payload: SlotInput):
        slot_id, timestamp = str(uuid4()), now_iso()
        with lock, database() as db:
            db.execute("""INSERT INTO slots(id,service,starts_at,duration_minutes,capacity,created_at)
                          VALUES(?,?,?,?,?,?)""", (
                slot_id, payload.service.strip(), payload.starts_at.astimezone(timezone.utc).isoformat(),
                payload.duration_minutes, payload.capacity, timestamp,
            ))
            db.commit()
            result = slot_view(db, slot_or_404(db, slot_id))
        await notify("slot_created", result)
        return result

    @app.post("/api/slots/{slot_id}/reservations", status_code=201)
    async def reserve(slot_id: str):
        timestamp, reservation_id = now_iso(), str(uuid4())
        with lock, database() as db:
            db.execute("BEGIN IMMEDIATE")
            slot = slot_or_404(db, slot_id)
            if datetime.fromisoformat(slot["starts_at"]) <= datetime.now(timezone.utc):
                raise HTTPException(409, "This appointment slot has already started")
            confirmed = db.execute("SELECT COUNT(*) FROM reservations WHERE slot_id=? AND status='confirmed'", (slot_id,)).fetchone()[0]
            status = "confirmed" if confirmed < slot["capacity"] else "waitlisted"
            db.execute("INSERT INTO reservations VALUES(?,?,?,?,?)", (
                reservation_id, slot_id, status, timestamp, timestamp,
            ))
            db.execute("INSERT INTO audit_events VALUES(?,?,?,?)", (
                str(uuid4()), reservation_id, "created_" + status, timestamp,
            ))
            db.commit()
            result = reservation_view(db, reservation_id)
        await notify("reservation_created", result)
        return result

    @app.get("/api/reservations/{reservation_id}")
    def get_reservation(reservation_id: str):
        with database() as db:
            return reservation_view(db, reservation_id)

    @app.get("/api/reservations/{reservation_id}/history")
    def history(reservation_id: str):
        with database() as db:
            reservation_or_404(db, reservation_id)
            return [dict(row) for row in db.execute(
                "SELECT event, occurred_at FROM audit_events WHERE reservation_id=? ORDER BY rowid",
                (reservation_id,),
            ).fetchall()]

    @app.post("/api/reservations/{reservation_id}/cancel")
    async def cancel(reservation_id: str):
        promoted = None
        with lock, database() as db:
            db.execute("BEGIN IMMEDIATE")
            item = reservation_or_404(db, reservation_id)
            if item["status"] == "cancelled":
                raise HTTPException(409, "Reservation already cancelled")
            timestamp = now_iso()
            db.execute("UPDATE reservations SET status='cancelled',updated_at=? WHERE id=?", (timestamp, reservation_id))
            db.execute("INSERT INTO audit_events VALUES(?,?,?,?)", (str(uuid4()), reservation_id, "cancelled", timestamp))
            slot = slot_or_404(db, item["slot_id"])
            if item["status"] == "confirmed" and datetime.fromisoformat(slot["starts_at"]) > datetime.now(timezone.utc):
                next_item = db.execute("""SELECT id FROM reservations
                    WHERE slot_id=? AND status='waitlisted' ORDER BY created_at,rowid LIMIT 1""", (item["slot_id"],)).fetchone()
                if next_item:
                    db.execute("UPDATE reservations SET status='confirmed',updated_at=? WHERE id=?", (timestamp, next_item["id"]))
                    db.execute("INSERT INTO audit_events VALUES(?,?,?,?)", (str(uuid4()), next_item["id"], "promoted_to_confirmed", timestamp))
                    promoted = next_item["id"]
            db.commit()
            result = reservation_view(db, reservation_id)
            promoted_result = reservation_view(db, promoted) if promoted else None
        await notify("reservation_cancelled", {"reservation": result, "promoted": promoted_result})
        return {"reservation": result, "promoted": promoted_result}

    @app.get("/api/metrics")
    def metrics():
        with database() as db:
            slots = db.execute("SELECT COUNT(*) FROM slots").fetchone()[0]
            rows = db.execute("SELECT status,COUNT(*) AS n FROM reservations GROUP BY status").fetchall()
            totals = {row["status"]: row["n"] for row in rows}
            return {"slots": slots, "confirmed": totals.get("confirmed", 0),
                    "waitlisted": totals.get("waitlisted", 0), "cancelled": totals.get("cancelled", 0)}

    @app.websocket("/ws")
    async def websocket(websocket: WebSocket):
        await websocket.accept()
        subscribers.add(websocket)
        try:
            await websocket.send_json({"event": "connected"})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            subscribers.discard(websocket)

    return app


app = create_app()
