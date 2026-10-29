# MasteryMap — Competency-Based Learning Progress Tracker

**Sector:** Education technology · **Status:** portfolio prototype, not a student-information system.

Teachers often track learning objectives in disconnected spreadsheets. MasteryMap is a small, end-to-end demonstration of how an instructor can define skills, record repeated assessment evidence, and see the **latest competency level** for every pseudonymous learner at a glance.

## Features

- Create courses and course-specific skills
- Register learners using **aliases only**
- Record assessment evidence with 0–100 scores and optional notes
- Reassess any skill; newest evidence determines the displayed competency level
- Competency matrix: **mastered (80–100)**, **progressing (50–79)**, **needs support (0–49)**, or **unassessed**
- Course metrics: learners, skills, assessment coverage, and mastery rate
- Audit-style assessment history, including previous scores
- Live WebSocket change events and reconnecting browser dashboard
- Validated REST API, SQLite persistence, integration tests, Docker, GitHub Actions CI
- No API keys, paid services, or frontend build step

## Technology

Python 3.11+ · FastAPI · Pydantic v2 · SQLite · WebSockets · HTML/CSS/JavaScript · pytest/HTTPX · Docker.

## Quick start

From this project directory:

~~~bash
python -m venv .venv
source .venv/bin/activate
# On Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
uvicorn app:app --reload
~~~

Open **http://127.0.0.1:8000** for the dashboard and **http://127.0.0.1:8000/docs** for interactive API documentation.

1. Create a course.
2. Add a skill and an anonymous learner.
3. Record an assessment score.
4. Record another score to see the latest result replace the old one in the matrix, while both remain in history.

## Test

~~~bash
python -m pytest -q
~~~

## Docker

~~~bash
docker build -t masterymap .
docker run --rm -p 8000:8000 -v masterymap-data:/data masterymap
~~~

The Docker volume preserves the SQLite database across container restarts. You can override the file path using the environment variable MASTERYMAP_DB.

## API reference

| Method | Path | Description |
| --- | --- | --- |
| GET | / | Browser UI |
| GET | /api/health | Health probe |
| GET | /api/courses | List courses |
| POST | /api/courses | Create course |
| POST | /api/courses/{course_id}/skills | Add competency |
| POST | /api/courses/{course_id}/learners | Add pseudonymous learner |
| POST | /api/evidence | Record score and note |
| GET | /api/courses/{course_id}/dashboard | Matrix, metrics, latest evidence and history |
| WS | /ws | Real-time JSON notifications |

Example:

~~~bash
curl -X POST http://127.0.0.1:8000/api/courses \
  -H 'Content-Type: application/json' \
  -d '{"name":"Biology Fundamentals","subject":"Science"}'
~~~

Use the returned course ID in the skills and learners endpoints. See /docs for request/response schemas.

## Architecture

~~~text
Browser (responsive UI)
  |  REST for CRUD + snapshots
  |  WebSocket for change notifications
  v
FastAPI (validation, domain rules, dashboard aggregation)
  |
  v
SQLite (courses, skills, learners, evidence)
~~~

The server emits a small event when records change. The browser then refetches the selected course. A 60-second refresh handles missed events. The most recent evidence is selected by timestamp and insertion order. Metrics use **learner × skill** cells as the denominator; unassessed cells count against coverage and mastery.

## Production and privacy limitations

**Do not use this demo with real student records.** There is no login, authorization, consent management, retention policy, encryption at rest, or multi-tenant isolation. Use fictional aliases and nonsensitive assessment notes only. This is not FERPA-compliant or approved for school deployment. Before production use, add identity and role-based access, audit controls, retention/deletion workflows, secure hosting and HTTPS, backups, accessibility testing, and a privacy/security review. For horizontal scaling, replace SQLite with PostgreSQL and the in-memory WebSocket broadcaster with Redis pub/sub.

## Deployment guidance

For a personal demonstration, run Docker on a low-cost/free-tier compatible host that supports persistent volumes and WebSockets, set the MASTERYMAP_DB path to a persistent mount, and terminate HTTPS at the host or reverse proxy. Free-tier availability and persistent-disk support vary; verify your provider's current terms. **No live deployment is included.**

## Portfolio value

Shows data modeling, transactional validation, relational integrity, real-time events, responsive UI, stateful dashboard aggregation, API integration tests, CI, and realistic privacy/operational tradeoffs.

## License

MIT — see LICENSE.
