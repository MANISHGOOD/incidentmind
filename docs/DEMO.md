# IncidentMind — Judge Demo Script (5 minutes)

**One-line pitch:** an AI incident-response agent that remembers how the company solved
previous incidents and uses that experience to resolve the next one faster.

Setup before the audience: `docker compose up -d` (Hindsight + Postgres), backend on :8000,
frontend on :5173. Click **Reset demo** once so the state is clean, then follow the acts.

---

## Act 1 — The world without memory (60s)

1. Open the dashboard. Click **Reset demo**, then **+ Simulate payment 503**.
   Incident `INC-0200` is created: *"Payment API is returning HTTP 503 on /v1/charges."*
2. Click **Memory: OFF** in the header (A/B switch — say it out loud: "the agent is on its own").
3. Click **Investigate with agent**. Narrate the live timeline: log searches, runbook,
   generic hypotheses — no organizational history anywhere.
4. Note the timeline: it takes **N tool steps** and lands on plausible-but-generic advice.

## Act 2 — Give the company its history (45s)

5. Click **Seed memory**. Explain: "we're loading 15 realistic past incidents — root causes,
   resolutions, outcomes, lessons — into Hindsight, the agent's persistent memory."
6. Show the **Memory** page: bank `incidentmind`, entry count climbing.

## Act 3 — The same incident, with organizational memory (90s)

7. Simulate the **same payment 503** again. Leave **Memory: ON**.
8. Investigate. The timeline now shows the 🧠 memory events:
   recall finds **INC-0101** (Redis connection-pool exhaustion) among similar incidents.
9. Walk through the recommendation card:
   - historical match with past root cause, resolution, outcome
   - the explicit **"applies to current evidence?"** line — the agent checked *today's*
     logs against the historical pattern, not just pattern-matched
   - confidence + proposed actions awaiting engineer approval
10. Resolve with the pre-filled root cause → **"Retained to organizational memory."**
    Say the closing line: *"Every incident makes the organization smarter."*

## Act 4 — The numbers (30s)

11. Open the dashboard: the **measured investigation effort** panel shows average agent
    steps with vs. without memory — computed from recorded tool calls on paired runs of
    the same alert, not claimed statistics.

---

## Backup talking points

- **Why Hindsight and not just Postgres?** App data answers "what happened"; Hindsight
  answers "what does the organization know" — recall fuses semantic, keyword, graph and
  temporal retrieval; observations consolidate recurring patterns; `reflect` gives
  disposition-aware reasoning over the whole bank.
- **Why no framework?** One function-calling loop = every step observable and demoable.
  The LLM is swappable (Groq default, `AGENT_MODEL` env).
- **Safety**: the agent proposes; only the engineer's **Resolve** writes anything — and
  what it writes is exactly what future incidents get to remember.
- If Hindsight is offline: the app still works (memory panel shows offline, agent falls
  back to evidence + runbooks) — resilience, not dependency.
