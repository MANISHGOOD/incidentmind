# Production Deployment Runbook (₹0 / free tier)

Target architecture:

```
Browser → Netlify (React SPA) → Render (FastAPI) → Render PostgreSQL
                                                 → Render (Hindsight) → Groq
```

## 1. Deploy the backend on Render (one-time)

1. Render Dashboard → **New + → Blueprint** → select `MANISHGOOD/incidentmind` (branch `main`).
2. Render reads `render.yaml` and creates 3 free resources:
   - `incidentmind-api` (Docker web service, free)
   - `incidentmind-hindsight` (Docker web service, free, no disk — memory self-heals on boot)
   - `incidentmind-db` (PostgreSQL, free — expires 30 days after creation)
3. When prompted for `sync: false` secrets:
   - `incidentmind-api` → `GROQ_API_KEY` = your Groq key (console.groq.com/keys)
   - `incidentmind-hindsight` → `HINDSIGHT_API_LLM_API_KEY` = the same key
   - `HINDSIGHT_API_KEY` stays empty
4. Click **Apply**. First Docker builds take a few minutes — wait for all three to show **Live**.
5. Smoke test in a browser:
   - `https://incidentmind-api-<suffix>.onrender.com/health` → `{"status":"ok"}`
   - `https://incidentmind-api-<suffix>.onrender.com/api/incidents` → 18 incidents (auto-seeded)

## 2. Point Netlify at the backend

1. Netlify → your site → **Site settings → Environment variables**:
   - Key: `VITE_API_URL`
   - Value: `https://incidentmind-api-<suffix>.onrender.com`  (no trailing slash, no secrets)
2. **Deploys → Trigger deploy → Deploy site** (env var changes only apply to new builds).
3. Verify: the live page's JS bundle now contains the Render URL
   (`View source` on the site, or check Network tab calls go to the Render host).
   Note: `VITE_*` values are baked into the public bundle — URLs only, never keys.

## 3. One-time production memory load

With the backend live: `curl -X POST https://<render-api>/api/seed-demo`
(or click **Seed memory** in the dashboard). Idempotent — safe to repeat.
From then on, memory also self-heals automatically on every backend boot.

## 4. End-to-end test (the demo)

1. Open the Netlify site → dashboard shows 18 incidents and Known Patterns ≥ 18.
2. Click **+ Simulate payment 503** → incident detail opens (INC-02xx).
3. Toggle **Memory: ON** (header) → **Investigate with agent**:
   - timeline streams live steps over SSE
   - 🧠 memory event lists similar incidents, including **INC-0101**
   - recommendation card shows the historical match (Redis pool exhaustion,
     "raise pool size from 10 to 50 + restart workers", "Service recovered")
   - confidence + proposed actions await **engineer approval** — nothing executes itself
4. Resolve with the pre-filled cause → "Retained to organizational memory".

## Free-tier gotchas (mention during the demo)

- **Cold start:** after ~15 min idle the API sleeps; the first request takes ~50s.
  Open the dashboard a minute before presenting to wake it.
- **Postgres expiry:** the free database expires 30 days after creation — create the
  Blueprint close to demo day, or upgrade that one resource if the project lives on.
- **Hindsight ephemerality:** no disk on free, so the API re-seeds memory on boot;
  incidents created live persist in PostgreSQL regardless.
