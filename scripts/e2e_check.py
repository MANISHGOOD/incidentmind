"""One-shot end-to-end probe: boots nothing itself — expects the API on :8012.

Run:  python scripts/e2e_check.py
"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8012"


def call(path, method="GET", body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main() -> int:
    ok = True

    status, health = call("/health")
    print(f"health: {status} {health}")
    ok &= status == 200

    status, inc = call("/api/incidents", "POST", {
        "service_name": "payment-api",
        "alert_text": "Payment API is returning HTTP 503 on /v1/charges (e2e smoke).",
    })
    print(f"create: {status} {inc.get('ref')}")
    ok &= status == 201
    ref = inc["ref"]

    status, detail = call(f"/api/incidents/{ref}")
    print(f"detail: {status} status={detail.get('status')} events={len(detail.get('events', []))}")
    ok &= status == 200 and detail.get("status") == "investigating"

    status, res = call(f"/api/incidents/{ref}/resolve", "POST", {
        "root_cause": "e2e smoke cause",
        "action_taken": "e2e smoke fix",
        "lessons": ["smoke lesson"],
    })
    print(f"resolve: {status} {res} (memory_retained false is expected without Hindsight)")
    ok &= status == 200 and res.get("resolved") is True

    status, detail = call(f"/api/incidents/{ref}")
    print(f"after resolve: status={detail.get('status')} resolutions={len(detail.get('resolutions', []))}")
    ok &= detail.get("status") == "resolved" and len(detail.get("resolutions", [])) == 1

    status, metrics = call("/api/metrics")
    print(f"metrics: {status} with={metrics['with_memory']} without={metrics['without_memory']}")
    ok &= status == 200

    status, state = call("/api/demo/state")
    print(f"demo state: {status} {state}")
    ok &= status == 200

    status, rb = call("/api/runbooks")
    print(f"runbooks: {status} count={len(rb)}")
    ok &= status == 200 and len(rb) >= 8

    print("E2E:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
