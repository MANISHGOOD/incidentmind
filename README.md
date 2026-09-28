# IncidentMind — AI Incident Response with Organizational Memory

> Every incident makes the organization smarter.

IncidentMind is an AI incident-response agent that remembers how the company solved previous
production incidents and uses that accumulated knowledge to help engineers resolve the next
incident faster. Built for **HackWithHyderabad 3.0**.

## The problem

When a production incident hits, engineers re-investigate problems the company has already
solved: Has this happened before? What was the root cause? Which fix actually worked? That
experience exists — in old tickets, in people's heads — but it isn't available as context
during the next incident. Teams pay the same investigation cost again and again.

## The solution

An incident agent backed by **persistent organizational memory**
([Hindsight](https://github.com/vectorize-io/hindsight)):

- **Recall** — every new incident retrieves similar past incidents, root causes, resolutions and outcomes
- **Compare** — the agent explicitly checks whether a historical pattern matches *current* evidence before recommending it
- **Learn** — every engineer-approved resolution is retained back into memory, so the system gets smarter with each incident
- **Measure** — investigation steps are counted per run; the dashboard shows with-memory vs. without-memory on paired runs of the same alert

## Features

- Ocean-themed React dashboard: KPIs, incident table, live investigation timeline
- Agent investigation streamed step-by-step over SSE (every tool call is visible and persisted)
- Recommendation card: ranked root causes, historical match, confidence, proposed actions
- Engineer-in-the-loop resolve flow — the agent proposes, only the engineer approves
- One-click demo controls: simulate the payment-503 alert, seed memory, reset, A/B memory toggle
- Metrics computed from real recorded tool calls, not claimed statistics
- Graceful degradation: Hindsight offline → app still works, agent falls back to evidence + runbooks

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
- **Hindsight = agent memory** (incident facts, lessons learned, consolidated observations)
- **Groq = LLM reasoning** (OpenAI-compatible function calling; provider/model swappable via env)

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, TypeScript, Tailwind CSS 4, React Router |
| Backend | Python 3.10+, FastAPI, SQLAlchemy 2, Pydantic v2 |
| Agent | Plain Groq function-calling loop (no framework), 7 tools |
| Memory | Hindsight (self-hosted Docker) — retain / recall / reflect |
| Database | PostgreSQL 16 (SQLite fallback for zero-setup dev) |
| Infra | Docker Compose |
| Tests | pytest (26 tests) + HTTP end-to-end probe |

## Folder structure

```
frontend/            React dashboard (pages, services, hooks)
backend/
  main.py            FastAPI routes, SSE streaming, demo controls
  agents/            agent loop, prompts, tool registry, events
  memory/            Hindsight wrapper (retain / recall / reflect)
  services/          incident lifecycle, demo seeds, metrics
  models.py          SQLAlchemy schema
data/
  incidents/         15 realistic synthetic incidents (JSON)
  logs/              per-incident synthetic log files
  runbooks/          9 operational runbooks (markdown)
tests/               pytest suite (tools, memory, agent loop, lifecycle)
scripts/e2e_check.py end-to-end HTTP probe
docs/DEMO.md         judge-facing 5-minute demo script
docker-compose.yml   postgres + self-hosted Hindsight
```

## Setup on Windows

Prerequisites: Python 3.10+, Node 18+, Git. Docker Desktop optional (needed only for Hindsight/Postgres).

```powershell
# 1. Clone and enter
git clone <your-repo-url> incidentmind
cd incidentmind

# 2. Environment file
copy .env.example .env        # then edit .env and set GROQ_API_KEY

# 3. Backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 4. Frontend (second terminal)
cd frontend
npm install
```

## Environment variables

Never commit `.env`. Copy `.env.example` and fill in:

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Groq API key for the agent LLM (and Hindsight's own extraction LLM) |
| `AGENT_MODEL` | Groq chat model, default `openai/gpt-oss-120b` |
| `DATABASE_URL` | SQLite default; switch to the Postgres URL for the full stack |
| `HINDSIGHT_BASE_URL` | `http://localhost:8888` for the bundled Docker setup |
| `HINDSIGHT_BANK_ID` | memory bank id, default `incidentmind` |
| `MEMORY_ENABLED` | global memory switch (runtime A/B toggle also exists in the UI) |
| `CORS_ORIGINS` | allowed frontend origins for the API |

## Running the stack

### 1. Infrastructure (Docker: Postgres + Hindsight)

```bash
docker compose up -d          # hindsight :8888 (API) / :9999 (UI), postgres :5432
```

No Docker? Skip this — the backend runs on SQLite and degrades gracefully while
Hindsight is offline (dashboard shows "Hindsight offline"; the agent works from
current evidence + runbooks only, which is exactly the demo's "before" state).

Point the backend at Postgres by setting in `.env`:

```
DATABASE_URL=postgresql+psycopg://incidentmind:incidentmind@localhost:5432/incidentmind
```

### 2. Backend

```bash
.venv\Scripts\activate        # Windows (bash: source .venv/Scripts/activate)
uvicorn backend.main:app --reload --port 8000
```

On boot the API **auto-seeds**: 15 historical incidents, 104 log lines, 9 runbooks.

### 3. Frontend

```bash
cd frontend
npm run dev                   # http://localhost:5173 (proxies /api to :8000)
```

## Seeding & demo data

- **Automatic**: application data (incidents/logs/runbooks) seeds on backend startup — idempotent.
- **Organizational memory**: click **Seed memory** in the header (or `POST /api/demo/seed-memory`)
  to retain all historical incidents into Hindsight. This is demo Act 2.
- **Reset**: click **Reset demo** to drop live incidents (`INC-02xx+`) and keep the historical set.

## Demo workflow (see docs/DEMO.md for the full script)

1. **Fresh system** — memory empty. Investigate "Payment API is returning HTTP 503":
   the agent works from logs and runbooks alone (generic troubleshooting).
2. **Seed memory** — one click loads the historical incidents into Hindsight.
3. **Same alert again** — the agent recalls INC-0101 (Redis connection-pool exhaustion),
   compares it against current log evidence, and proposes the resolution that worked before.
4. **Resolve** — the engineer approves; the resolution is retained into Hindsight.
5. **Metrics** — the dashboard shows measured average investigation steps with vs. without
   memory for paired runs of the same alert.

## Tests

```bash
python -m pytest tests/ -q     # 26 tests: tools, memory layer, agent loop, lifecycle
python scripts/e2e_check.py    # with the API running on :8012
cd frontend && npm run build   # typecheck + production build
```

## Safety note

- The agent **proposes** actions; nothing is executed autonomously. Only the engineer's
  **Resolve** writes a resolution — and what it writes is exactly what future incidents remember.
- No secrets are stored in the repository: `.env` is git-ignored; `.env.example` contains
  placeholders only. API keys live only in your local `.env`.
- All incident data in `data/` is synthetic, created for the demo.

## Future improvements

- Webhook/alert ingest (PagerDuty, Grafana) to create incidents automatically
- Log-parsing connectors for real log stores instead of bundled synthetic logs
- Per-team memory banks with cross-bank pattern sharing
- Post-resolution verification ("did the fix actually hold?") feeding memory outcomes
- Mental-model–powered "known patterns" page rendered straight from Hindsight
