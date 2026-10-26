# PulseOps — Real-Time Incident Tracker

A working full-stack incident response dashboard for small engineering and operations teams. When a service goes down, people need one place to report the problem, track response progress, and share updates instantly. PulseOps solves that using an HTTP API, persistent SQLite storage, and WebSocket-powered live UI refresh.

## Features

- Report incidents with title, affected service, severity, and description
- Track investigations through **investigating → identified → monitoring → resolved**
- Log a timestamped, auditable update history for each incident
- Live WebSocket broadcasts when incidents are created or updated
- Filter incidents by status; view counts of open, resolved, and critical incidents
- REST API documentation at `/docs`
- SQLite persistence, automated API/WebSocket tests, Docker support, CI workflow
- No external API keys or paid dependencies needed

## Stack

**Backend:** Python 3.11+, FastAPI, Pydantic, SQLite, WebSockets  
**Frontend:** responsive HTML/CSS/vanilla JavaScript  
**Tests:** Pytest, HTTPX / FastAPI TestClient  
**Deployment:** Docker or any Python host with persistent disk

## Run locally

```bash
cd live-incident-tracker
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements-dev.txt
uvicorn app:app --reload
```

Visit **http://localhost:8000**. API explorer: **http://localhost:8000/docs**.

### Docker

```bash
docker build -t pulseops .
docker run --rm -p 8000:8000 -v pulseops-data:/data pulseops
```

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Browser dashboard |
| GET | `/api/health` | Health probe |
| GET | `/api/metrics` | Incident counts |
| GET | `/api/incidents` | List incidents (optional `status`, `service` filters) |
| GET | `/api/incidents/{id}` | Detail and update timeline |
| POST | `/api/incidents` | Create incident |
| POST | `/api/incidents/{id}/updates` | Add status / progress update |
| WS | `/ws` | Subscribe to JSON events: `connected`, `incident_created`, `incident_updated` |

Example:

```bash
curl -X POST http://localhost:8000/api/incidents \\
  -H "Content-Type: application/json" \\
  -d '{"title":"Checkout failing","service":"payments","severity":"high","description":"Customers receive HTTP 503"}'
```

## Run tests

```bash
pytest -q
```

## Architecture

```text
Browser ──HTTP──► FastAPI ──SQL──► SQLite
   ▲                 │
   └── WebSocket ◄──┘   (broadcast on writes)
```

Data is stored in `incidents.db` by default. Set `INCIDENT_DB=/path/to/file.db` for a custom location. Docker uses `/data/incidents.db` in a persistent volume.

## Security and production limitations

This is a **portfolio/demo application**, not a production-ready multi-tenant incident management service. It deliberately has no user authentication, role-based access, rate limiting, or notifications. **Do not expose it publicly without adding authentication and HTTPS**. SQLite and in-process WebSocket fan-out work for a single server process; production scaling would require PostgreSQL, a shared pub/sub broker (e.g., Redis), backups, and structured observability. WebSocket clients reconnect automatically and poll every minute to catch missed events. The app intentionally forbids reopening resolved incidents; future versions could add a dedicated reopen workflow.

## Suggested next improvements

- OIDC login and incident-level RBAC
- SLO monitoring integrations and alert ingestion
- Slack/email notifications
- Post-incident review and mean-time-to-recovery reporting
- PostgreSQL / Redis for multi-instance deployment

## Portfolio talking points

Demonstrates API design, relational persistence, real-time event delivery, input validation, responsive web UI, integration tests, containerization, and documented operational tradeoffs.

## License

MIT — see [LICENSE](LICENSE).
