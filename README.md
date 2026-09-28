# IncidentMind — AI Incident Response with Organizational Memory

> Every incident makes the organization smarter.

IncidentMind is an AI incident-response agent that remembers how the company solved previous
production incidents and uses that accumulated knowledge to help engineers resolve the next
incident faster. Built for **HackWithHyderabad 3.0**.

- **Agent**: one plain function-calling loop (Groq, OpenAI-compatible API) — no framework
- **Memory**: [Hindsight](https://github.com/vectorize-io/hindsight) — retain / recall / reflect
- **App data**: PostgreSQL (SQLite fallback for zero-setup dev)
- **UI**: React + Vite + Tailwind (ocean theme)

## Architecture

```
Engineer ──> React dashboard ──> FastAPI backend ──> Agent (Groq function-calling)
                                        │                 │
                                        │        ┌────────┼────────────┐
                                        │        ▼        ▼            ▼
                                        │   PostgreSQL   Hindsight    Runbooks/Logs
                                        │  (incidents,   (past incidents,
                                        │   events,       root causes,
                                        │   resolutions)  resolutions, patterns)
                                        ▼
                          Every resolution is retained back into Hindsight
```

- **PostgreSQL = application data** (incidents, events, resolutions, runbooks, logs)
- **Hindsight = agent memory** (incident facts, lessons, consolidated observations)

## Quick start

### 1. Infrastructure (Hindsight + Postgres)

```bash
cp .env.example .env          # add your GROQ_API_KEY
docker compose up -d          # hindsight :8888 (API) / :9999 (UI), postgres :5432
```

No Docker? The backend still runs: it uses SQLite and degrades gracefully while
Hindsight is offline (the dashboard shows "Hindsight offline" and the agent works
from current evidence + runbooks only).

### 2. Backend

```bash
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

The API seeds 15 historical incidents + 105 log lines + 9 runbooks automatically.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                   # http://localhost:5173 (proxies /api to :8000)
```

## Repository layout

```
frontend/            React dashboard (pages, services, hooks)
backend/
  api logic          main.py (FastAPI routes, SSE streaming)
  agents/            agent loop, prompts, tool registry, events
  memory/            Hindsight wrapper (retain / recall / reflect)
  services/          incident lifecycle, demo seeds, metrics
  models.py          SQLAlchemy schema
data/
  incidents/         15 realistic synthetic incidents (JSON)
  logs/              per-incident synthetic log files
  runbooks/          9 operational runbooks (markdown)
tests/               pytest suite (tools, memory, agent loop, lifecycle)
docker-compose.yml   postgres + self-hosted Hindsight
```

## How the demo works

1. **Fresh system** — memory empty. Investigate "Payment API is returning HTTP 503":
   the agent works from logs and runbooks alone (generic troubleshooting).
2. **Seed memory** — one click loads the historical incidents into Hindsight.
3. **Same alert again** — the agent recalls INC-0101 (Redis connection-pool exhaustion),
   compares it against current log evidence, and proposes the resolution that worked before.
4. **Resolve** — the engineer approves; the resolution is retained into Hindsight.
   The metrics panel then shows measured steps with vs. without memory.

Toggle **Memory: ON/OFF** in the header for a live A/B run of the same alert.

## Agent tools

| Tool | Purpose |
|---|---|
| `get_incident` | current incident record |
| `search_logs` | grep the current incident's log lines |
| `search_memory` | recall similar past incidents from Hindsight |
| `compare_with_history` | full record of a historical incident (by ref) |
| `reflect_patterns` | recurring problems / what worked (Hindsight reflect) |
| `get_runbook` | operational runbook for the service/trigger |
| `record_step` | persist a hypothesis/finding to the timeline |

Every tool call is persisted as an incident event — the timeline and the
step-count metric are exact, not estimated.

## Configuration

See `.env.example` (`GROQ_API_KEY`, `AGENT_MODEL`, `DATABASE_URL`,
`HINDSIGHT_BASE_URL`, `HINDSIGHT_BANK_ID`, `MEMORY_ENABLED`, `CORS_ORIGINS`).
Never commit `.env`.

## Tests

```bash
python -m pytest tests/ -q     # 26 tests: tools, memory layer, agent loop, lifecycle
cd frontend && npm run build   # typecheck + production build
```

## What we deliberately did NOT build

No agent swarm, no generic chatbot, no autonomous production changes, no fake
predictive claims. One workflow — memory-assisted incident resolution — done well.
