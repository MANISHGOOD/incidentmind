"""One-shot production verification for the deployed IncidentMind backend.

Usage:
    python scripts/verify_prod.py https://incidentmind-api-xxxx.onrender.com

Checks (in order):
 1. /health responds OK
 2. /api/incidents returns the seeded historical dataset (>= 18)
 3. /api/stats returns dashboard KPIs
 4. /api/incidents/INC-0101 carries the core-demo resolution
 5. CORS: a preflight from the Netlify origin is accepted
 6. Full demo flow: create -> investigate (SSE) -> resolve -> verify retention
    (investigation requires GROQ_API_KEY on the api service; everything else
    is verifiable without it)
"""
import json
import sys
import urllib.error
import urllib.request

NETLIFY_ORIGIN = "https://monumental-khapse-b6b78e.netlify.app"


class HTTP:
    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def request(self, path: str, method: str = "GET", body: dict | None = None,
                headers: dict | None = None, timeout: int = 120):
        req = urllib.request.Request(
            self.base + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode()

    def get_json(self, path: str, timeout: int = 120):
        status, _, body = self.request(path, timeout=timeout)
        return status, json.loads(body)

    def post_json(self, path: str, body: dict | None = None, timeout: int = 180):
        status, _, body = self.request(path, method="POST", body=body or {}, timeout=timeout)
        return status, json.loads(body)

    def sse_events(self, path: str, timeout: int = 240):
        """POST an SSE endpoint and return the parsed event list."""
        status, _, body = self.request(path, method="POST", timeout=timeout)
        events = []
        for frame in body.split("\n\n"):
            for line in frame.split("\n"):
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass
        return status, events


def check(results: list, name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    http = HTTP(sys.argv[1])
    results: list = []
    print(f"Verifying production backend: {http.base}\n")

    # 1. health
    try:
        status, body = http.get_json("/health")
        check(results, "GET /health", status == 200 and body.get("status") == "ok", str(body))
    except Exception as e:  # noqa: BLE001
        check(results, "GET /health", False, str(e))
        return report(results)

    # 2. incidents list
    try:
        status, items = http.get_json("/api/incidents")
        refs = [i["ref"] for i in items]
        check(results, "GET /api/incidents (>= 18 seeded)", status == 200 and len(items) >= 18,
              f"{len(items)} incidents, INC-0101 present: {'INC-0101' in refs}")
    except Exception as e:  # noqa: BLE001
        check(results, "GET /api/incidents", False, str(e))

    # 3. stats
    try:
        status, stats = http.get_json("/api/stats")
        check(results, "GET /api/stats",
              status == 200 and stats.get("total_incidents", 0) >= 18,
              f"total={stats.get('total_incidents')} patterns={stats.get('known_patterns')} "
              f"memory={stats.get('memory_entries')} available={stats.get('memory_available')}")
    except Exception as e:  # noqa: BLE001
        check(results, "GET /api/stats", False, str(e))

    # 4. core demo historical incident
    try:
        status, detail = http.get_json("/api/incidents/INC-0101")
        res = (detail.get("resolutions") or [{}])[0]
        ok = (detail.get("service_name") == "payment-api"
              and "Redis" in (res.get("root_cause") or "")
              and "pool size from 10 to 50" in (res.get("action_taken") or ""))
        check(results, "GET /api/incidents/INC-0101 (core demo data)", status == 200 and ok)
    except Exception as e:  # noqa: BLE001
        check(results, "GET /api/incidents/INC-0101", False, str(e))

    # 5. CORS preflight from the Netlify origin
    try:
        status, headers, _ = http.request(
            "/api/incidents", method="OPTIONS", headers={
                "Origin": NETLIFY_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            })
        allow = headers.get("Access-Control-Allow-Origin", "")
        check(results, "CORS preflight from Netlify origin",
              status in (200, 204) and NETLIFY_ORIGIN in allow,
              f"allow-origin={allow or '(missing)'}")
    except Exception as e:  # noqa: BLE001
        check(results, "CORS preflight", False, str(e))

    # 6. live demo flow
    ref = None
    try:
        status, inc = http.post_json("/api/incidents", {
            "service_name": "payment-api",
            "alert_text": "Payment API is returning HTTP 503 errors. Workers cannot obtain Redis connections.",
        })
        ref = inc.get("ref")
        check(results, "POST /api/incidents (create live incident)", status == 201 and bool(ref),
              f"created {ref}")
    except Exception as e:  # noqa: BLE001
        check(results, "POST /api/incidents", False, str(e))

    if ref:
        try:
            status, events = http.sse_events(f"/api/incidents/{ref}/investigate")
            kinds = [e.get("kind") for e in events]
            got_mem = any(e.get("kind") == "memory" for e in events)
            got_rec = any(e.get("kind") == "recommendation" for e in events)
            errs = [e.get("message") for e in events if e.get("kind") == "error"]
            detail = f"events={len(events)} memory={got_mem} recommendation={got_rec}"
            ok = status == 200 and got_rec and not errs
            if errs:
                detail += f" | error: {errs[0][:120]}"
            if not ok and errs and "LLM" in (errs[0] or ""):
                detail += " | hint: set GROQ_API_KEY on incidentmind-api in Render"
            check(results, "POST investigate (SSE agent run)", ok, detail)
            if got_rec:
                rec = next(e["data"] for e in events if e["kind"] == "recommendation")
                match = rec.get("historical_match") or {}
                check(results, "  historical match surfaced (INC-0101)",
                      match.get("ref") == "INC-0101",
                      f"match={match.get('ref') or '(none)'} confidence={rec.get('confidence')}")
        except Exception as e:  # noqa: BLE001
            check(results, "POST investigate (SSE agent run)", False, str(e))

        try:
            status, res = http.post_json(f"/api/incidents/{ref}/resolve", {
                "root_cause": "Redis connection pool exhaustion (production verification)",
                "action_taken": "Increase pool size and restart affected workers",
                "lessons": ["verify_prod: retention path exercised"],
            })
            check(results, "POST resolve (engineer approval -> memory)",
                  status == 200 and res.get("resolved") is True,
                  f"memory_retained={res.get('memory_retained')}")
            if not res.get("memory_retained"):
                print("         (retention false -> check Gemini keys on incidentmind-hindsight)")
        except Exception as e:  # noqa: BLE001
            check(results, "POST resolve", False, str(e))

        try:
            status, stats = http.get_json("/api/stats")
            check(results, "GET /api/stats after resolve (memory grew)",
                  (stats.get("memory_entries") or 0) > 0,
                  f"memory_entries={stats.get('memory_entries')}")
        except Exception as e:  # noqa: BLE001
            check(results, "GET /api/stats after resolve", False, str(e))

    return report(results)


def report(results: list) -> int:
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("FAILED:")
        for name, _, detail in failed:
            print(f"  - {name}" + (f" ({detail})" if detail else ""))
        print("\nMost likely fixes: cold start (retry in ~60s), GROQ_API_KEY on the api")
        print("service, Gemini (AIza) keys on incidentmind-hindsight, then re-run this script.")
    else:
        print("PRODUCTION BACKEND FULLY OPERATIONAL")
        print("Next: set VITE_API_URL to this URL in Netlify and trigger a deploy.")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
