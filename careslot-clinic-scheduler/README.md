# CareSlot — Community Clinic Appointment & Waitlist Scheduler

**Sector:** Healthcare operations · **Type:** educational prototype (not for patient care)

CareSlot helps a community clinic manage limited appointment capacity without spreadsheets. Staff can publish time slots, anonymous visitors can reserve a place, and when a confirmed reservation is cancelled the oldest waitlisted ticket is promoted automatically. Changes propagate to connected dashboards over WebSockets.

> **Safety & privacy:** This is a portfolio demo, **not a clinical or HIPAA-compliant system**. It intentionally collects no names, contact information, diagnoses, or medical records. Do not enter protected health information (PHI), connect it to a real clinic, or expose it publicly without authentication, authorization, privacy review, and security hardening.

## Features

- Create future appointment slots with a service, duration, and capacity (1–20)
- Atomic reservations that never exceed slot capacity; automatic FIFO waitlist
- Cancel confirmed or waitlisted reservations; promote earliest waitlisted ticket on cancellation
- Anonymous reservation tickets stored in the browser, with waitlist position and event history
- Real-time WebSocket updates, with periodic HTTP refresh as fallback
- Responsive HTML/CSS/JavaScript dashboard, FastAPI REST endpoints, SQLite persistence
- Input validation, error responses, audit events, API tests, WebSocket tests, GitHub Actions, Docker
- No paid APIs, credentials, or third-party services required

## Quick start

Requires Python 3.11+.

```bash
cd careslot-clinic-scheduler
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app:app --reload
```

Open **http://localhost:8000**. API explorer: **http://localhost:8000/docs**.

To create a slot, choose a service, future local date/time, duration and capacity. Click **Reserve a spot**. Once the slot fills, subsequent bookings join a waitlist. Cancel a confirmed ticket to observe automatic promotion.

## Docker

```bash
docker build -t careslot .
docker run --rm -p 8000:8000 -v careslot-data:/data careslot
```

Docker persists the database in the named volume. Locally, set `CARESLOT_DB=/path/to/careslot.db` to override the default `careslot.db`.

## API reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Web dashboard |
| GET | `/api/health` | Liveness check |
| GET | `/api/metrics` | Slot and ticket counts |
| GET | `/api/slots?service=...` | List slots with capacity and waitlist counts |
| POST | `/api/slots` | Create future appointment slot |
| POST | `/api/slots/{id}/reservations` | Reserve or join FIFO waitlist |
| GET | `/api/reservations/{id}` | Ticket status and queue position |
| GET | `/api/reservations/{id}/history` | Append-only ticket event history |
| POST | `/api/reservations/{id}/cancel` | Cancel; automatically promote if applicable |
| WS | `/ws` | Live events: slot_created, reservation_created, reservation_cancelled |

Create a slot (choose a future time):

```bash
curl -X POST http://localhost:8000/api/slots \
  -H 'Content-Type: application/json' \
  -d '{"service":"Routine check-in","starts_at":"2030-01-01T15:00:00+00:00","duration_minutes":30,"capacity":2}'
```

Use the returned slot `id`:

```bash
curl -X POST http://localhost:8000/api/slots/SLOT_ID/reservations
```

Reservations require no patient details; the server issues a random ticket ID. The browser stores ticket IDs in local storage. **Treat ticket IDs as bearer credentials in this demo**: anyone who knows one can inspect or cancel that reservation.

## Run tests

```bash
pytest -q
```

Tests cover health, validation, filtering, capacity limits, FIFO promotion, cancellation conflicts, missing records, audit history and WebSocket events. CI runs the suite on pushes affecting this project.

## Architecture

```text
Browser (vanilla JS)
    |-- HTTP REST ----------> FastAPI ------> SQLite (slots, reservations, audit_events)
    |-- WebSocket <----------|                 transaction lock + BEGIN IMMEDIATE
    |-- localStorage (anonymous ticket IDs)
```

The server uses a process-local lock plus SQLite write transactions to prevent capacity overbooking. WebSocket broadcasting is in-process and works with a **single Uvicorn worker**; for multi-worker production deployment, replace it with a shared event broker and add appropriate distributed locking and a production database.

## Deployment guidance

A container host with persistent disk (or a VM) can run the Docker image. Bind to port 8000 and mount a persistent volume at `/data`. Set HTTPS at the reverse proxy. The example is **not publicly deployed** and **not suitable for real patient scheduling**. Before any real deployment: add OIDC login, staff/visitor roles, audit access controls, rate limiting, CSRF defenses where applicable, data retention policies, backup/restore procedures, monitoring, security tests, and a legal/privacy review. Do not treat anonymous ticket IDs as secure authentication.

## Future enhancements

- Staff approval and scoped accounts
- Notifications with explicit opt-in and privacy safeguards
- Calendar integration and accessible localization
- Rescheduling and configurable appointment policies
- PostgreSQL + Redis for multi-instance reliability

## License

MIT — see [LICENSE](LICENSE).
