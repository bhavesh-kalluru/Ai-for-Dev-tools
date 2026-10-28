# RouteRelay — Transit Disruption & ETA Dashboard

**Sector:** Transportation / Public Transit Operations  
**Status:** Educational portfolio prototype; not a passenger-safety or dispatch system.

RouteRelay helps small transit operators track routes, publish service alerts, log delays, and show estimated arrival times in one responsive, real-time dashboard. It addresses a practical problem: without a central operations board, riders and dispatchers have no shared view of delayed or cancelled services.

## Features

- Create bus, rail, tram, and ferry routes with ordered stops and travel-time offsets
- Schedule trips on any service date with departure times and initial delays
- Record operator updates and status changes (scheduled, boarding, en_route, completed, cancelled)
- Calculate stop-level scheduled and predicted arrivals, including overnight rollover
- Publish and resolve route-level service alerts by severity
- Live WebSocket event broadcasts plus automatic reconnect and periodic refresh
- Persistent SQLite database, API docs, automated tests, GitHub Actions CI, Docker

## Stack

Python 3.11+, FastAPI, Pydantic v2, SQLite, WebSockets, HTML/CSS/vanilla JavaScript, Pytest, Docker. No paid services or API keys.

## Local setup

From the repository root:

```bash
cd routerelay-transit-operations
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements-dev.txt
uvicorn app:app --reload
```

Open http://localhost:8000. Interactive API docs: http://localhost:8000/docs.

### Docker

```bash
docker build -t routerelay .
docker run --rm -p 8000:8000 -v routerelay-data:/data routerelay
```

The Docker volume persists the SQLite database.

## Quick demo

1. Create an "Airport Express" bus route with stops "Central Station | 0" and "Airport Terminal | 35".
2. Schedule a trip for today's date departing at 09:30, with a 10-minute delay.
3. Select the route in the live board; see the scheduled and predicted arrival times.
4. Mark the trip "en_route" with an update note; predicted times refresh for connected browsers.
5. Post a "major" alert, then resolve it.

### API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Browser dashboard |
| GET | `/api/health` | Health check |
| GET | `/api/routes` | List routes and ordered stops |
| POST | `/api/routes` | Create route with stops |
| POST | `/api/trips` | Schedule trip |
| GET | `/api/trips/{trip_id}` | Trip and update history |
| PATCH | `/api/trips/{trip_id}` | Update status and/or delay |
| GET | `/api/board/{route_id}?service_date=YYYY-MM-DD` | Stop arrival predictions and active alerts |
| POST | `/api/alerts` | Publish service alert |
| POST | `/api/alerts/{alert_id}/resolve` | Resolve alert |
| WS | `/ws` | Subscribe to change events |

Example route creation:

```bash
curl -X POST http://localhost:8000/api/routes \\
  -H 'Content-Type: application/json' \\
  -d '{"name":"Airport Express","mode":"bus","stops":[{"name":"Central Station","offset_minutes":0},{"name":"Airport Terminal","offset_minutes":35}]}'
```

Copy the returned route ID into a trip creation request or use the dashboard.

## Tests

```bash
pytest -q
```

The suite covers route validation, persistence, trip lifecycle, delays, midnight rollover, alerts, missing resources, and WebSocket events. GitHub Actions runs tests on pushes and pull requests affecting this project.

## Architecture

```text
Browser (dashboard)
  ├── REST API ──> FastAPI ──> SQLite (routes, stops, trips, events, alerts)
  └── WebSocket <─ FastAPI change broadcast
```

All timetable and predicted arrival values are **route-local naive times** (ISO 8601 without time-zone offset). Predictions are simply scheduled stop arrival plus manually reported trip delay; no GPS or external traffic data is involved. A cancelled or completed trip has no predicted arrival.

Set `ROUTERELAY_DB=/path/to/routerelay.db` to change the SQLite location.

## Deployment guidance

For a private demo, deploy the Docker image on a host with a persistent disk and HTTPS reverse proxy. Configure `ROUTERELAY_DB` to use persistent storage. The single-process WebSocket fan-out does not work across multiple worker instances.

**Important limitations:** No authentication, authorization, rate limiting, real GPS, timezone-aware timetables, GTFS ingestion, public passenger notifications, or service-level redundancy. **Do not expose write endpoints publicly or use this for actual dispatch or safety-critical transit operations.** For production, add identity and operator roles, PostgreSQL, shared pub/sub (Redis), observability, backups, audit controls, GTFS-RT support, and correct agency timezone/DST handling.

## Portfolio value

Demonstrates API design, relational schema and referential integrity, real-time WebSockets, server-side validation, schedule arithmetic across midnight, frontend state management, integration testing, containerization, and deployment tradeoffs.

## License

MIT; see [LICENSE](LICENSE).
