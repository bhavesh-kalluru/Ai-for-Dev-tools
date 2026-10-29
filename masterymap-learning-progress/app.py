"""MasteryMap: competency-based learning progress tracker (demo only)."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CleanModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("*", mode="after")
    @classmethod
    def reject_blank(cls, value):
        if isinstance(value, str) and not value:
            raise ValueError("Text fields cannot be blank")
        return value


class CourseIn(CleanModel):
    name: str = Field(min_length=3, max_length=100)
    subject: str = Field(min_length=2, max_length=80)


class SkillIn(CleanModel):
    title: str = Field(min_length=3, max_length=100)
    description: str = Field(default="", max_length=500)


class LearnerIn(CleanModel):
    alias: str = Field(min_length=2, max_length=60)


class EvidenceIn(CleanModel):
    learner_id: str
    skill_id: str
    score: int = Field(ge=0, le=100)
    note: str = Field(default="", max_length=500)


def now():
    return datetime.now(timezone.utc).isoformat()


def level(score):
    if score is None:
        return "unassessed"
    if score >= 80:
        return "mastered"
    if score >= 50:
        return "progressing"
    return "needs_support"


def create_app(db_path=None):
    app = FastAPI(title="MasteryMap Learning Progress", version="1.0.0")
    path = str(db_path if db_path is not None else os.environ.get("MASTERYMAP_DB", "masterymap.db"))
    lock = Lock()
    subscribers = set()

    @contextmanager
    def connect():
        db = sqlite3.connect(path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
        finally:
            db.close()

    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS courses (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, subject TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id),
            title TEXT NOT NULL COLLATE NOCASE, description TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE(course_id, title)
        );
        CREATE TABLE IF NOT EXISTS learners (
            id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id),
            alias TEXT NOT NULL COLLATE NOCASE, created_at TEXT NOT NULL,
            UNIQUE(course_id, alias)
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id TEXT PRIMARY KEY, learner_id TEXT NOT NULL REFERENCES learners(id),
            skill_id TEXT NOT NULL REFERENCES skills(id), score INTEGER NOT NULL
            CHECK(score BETWEEN 0 AND 100), note TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_lookup
            ON evidence(learner_id, skill_id, created_at);
        """)
        db.commit()

    def require_course(db, course_id):
        row = db.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Course not found")
        return dict(row)

    async def broadcast(kind, course_id):
        failed = []
        for ws in tuple(subscribers):
            try:
                await ws.send_json({"type": kind, "course_id": course_id})
            except Exception:
                failed.append(ws)
        for ws in failed:
            subscribers.discard(ws)

    @app.get("/")
    def home():
        return FileResponse(Path(__file__).with_name("index.html"))

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/courses")
    def courses():
        with connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM courses ORDER BY created_at DESC, rowid DESC"
            )]

    @app.post("/api/courses", status_code=201)
    async def add_course(data: CourseIn):
        item = {"id": str(uuid4()), "name": data.name, "subject": data.subject,
                "created_at": now()}
        with lock, connect() as db:
            db.execute("INSERT INTO courses VALUES (:id,:name,:subject,:created_at)", item)
            db.commit()
        await broadcast("course_created", item["id"])
        return item

    @app.post("/api/courses/{course_id}/skills", status_code=201)
    async def add_skill(course_id: str, data: SkillIn):
        item = {"id": str(uuid4()), "course_id": course_id, "title": data.title,
                "description": data.description, "created_at": now()}
        with lock, connect() as db:
            require_course(db, course_id)
            try:
                db.execute("""INSERT INTO skills
                    (id,course_id,title,description,created_at)
                    VALUES (:id,:course_id,:title,:description,:created_at)""", item)
                db.commit()
            except sqlite3.IntegrityError:
                raise HTTPException(409, "Skill title already exists in this course")
        await broadcast("skill_created", course_id)
        return item

    @app.post("/api/courses/{course_id}/learners", status_code=201)
    async def add_learner(course_id: str, data: LearnerIn):
        item = {"id": str(uuid4()), "course_id": course_id, "alias": data.alias,
                "created_at": now()}
        with lock, connect() as db:
            require_course(db, course_id)
            try:
                db.execute("""INSERT INTO learners
                    (id,course_id,alias,created_at)
                    VALUES (:id,:course_id,:alias,:created_at)""", item)
                db.commit()
            except sqlite3.IntegrityError:
                raise HTTPException(409, "Learner alias already exists in this course")
        await broadcast("learner_created", course_id)
        return item

    @app.post("/api/evidence", status_code=201)
    async def add_evidence(data: EvidenceIn):
        item = {"id": str(uuid4()), "learner_id": data.learner_id,
                "skill_id": data.skill_id, "score": data.score,
                "note": data.note, "created_at": now()}
        with lock, connect() as db:
            learner = db.execute(
                "SELECT course_id FROM learners WHERE id=?", (data.learner_id,)
            ).fetchone()
            skill = db.execute(
                "SELECT course_id FROM skills WHERE id=?", (data.skill_id,)
            ).fetchone()
            if learner is None or skill is None:
                raise HTTPException(404, "Learner or skill not found")
            if learner["course_id"] != skill["course_id"]:
                raise HTTPException(422, "Learner and skill must belong to the same course")
            db.execute("""INSERT INTO evidence
                (id,learner_id,skill_id,score,note,created_at)
                VALUES (:id,:learner_id,:skill_id,:score,:note,:created_at)""", item)
            db.commit()
        await broadcast("evidence_added", learner["course_id"])
        return {**item, "level": level(data.score)}

    @app.get("/api/courses/{course_id}/dashboard")
    def dashboard(course_id: str):
        with connect() as db:
            course = require_course(db, course_id)
            skills = [dict(r) for r in db.execute(
                "SELECT * FROM skills WHERE course_id=? ORDER BY created_at,rowid",
                (course_id,)
            )]
            learners = [dict(r) for r in db.execute(
                "SELECT * FROM learners WHERE course_id=? ORDER BY alias",
                (course_id,)
            )]
            history = [dict(r) for r in db.execute("""
                SELECT e.*, l.alias AS learner_alias, s.title AS skill_title
                FROM evidence e JOIN learners l ON l.id=e.learner_id
                JOIN skills s ON s.id=e.skill_id
                WHERE l.course_id=?
                ORDER BY e.created_at DESC, e.rowid DESC
            """, (course_id,))]
        latest = {}
        for entry in history:
            latest.setdefault((entry["learner_id"], entry["skill_id"]), entry)
        matrix = []
        mastered = assessed = 0
        for learner in learners:
            cells = []
            for skill in skills:
                entry = latest.get((learner["id"], skill["id"]))
                score = entry["score"] if entry else None
                assessed += score is not None
                mastered += score is not None and score >= 80
                cells.append({"skill_id": skill["id"], "score": score,
                              "level": level(score)})
            matrix.append({"learner_id": learner["id"], "alias": learner["alias"],
                           "cells": cells})
        possible = len(learners) * len(skills)
        return {
            "course": course, "skills": skills, "learners": learners,
            "matrix": matrix, "recent_evidence": history[:25],
            "metrics": {
                "learners": len(learners), "skills": len(skills),
                "assessed": assessed, "mastered": mastered,
                "coverage_percent": round(100 * assessed / possible) if possible else 0,
                "mastery_percent": round(100 * mastered / possible) if possible else 0,
            },
        }

    @app.websocket("/ws")
    async def websocket(ws: WebSocket):
        await ws.accept()
        subscribers.add(ws)
        try:
            await ws.send_json({"type": "connected"})
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            subscribers.discard(ws)

    return app


app = create_app()
