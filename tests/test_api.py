"""API endpoint tests via TestClient (SQLite, memory disabled in tests)."""
from fastapi.testclient import TestClient

from backend.main import app


def test_incidents_list_and_detail(db):
    client = TestClient(app)
    r = client.get("/api/incidents")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 18
    refs = [i["ref"] for i in items]
    assert "INC-0101" in refs and "INC-0118" in refs

    r = client.get("/api/incidents/INC-0101")
    assert r.status_code == 200
    d = r.json()
    assert d["service_name"] == "payment-api"
    assert any(res["root_cause"] for res in d["resolutions"])
    assert "503" in d["alert_text"]

    assert client.get("/api/incidents/INC-9999").status_code == 404


def test_incident_logs_endpoint(db):
    client = TestClient(app)
    r = client.get("/api/incidents/INC-0101/logs")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] > 5
    assert "pool timed out" in "\n".join(l["line"] for l in body["lines"])

    assert client.get("/api/incidents/INC-9999/logs").status_code == 404


def test_stats_endpoint(db):
    client = TestClient(app)
    r = client.get("/api/stats")
    assert r.status_code == 200
    s = r.json()
    assert s["total_incidents"] == 18
    assert s["resolved_incidents"] == 18
    assert s["active_incidents"] == 0
    assert s["known_patterns"] >= 15
    assert s["runbooks"] == 10
    assert s["memory_available"] is False  # memory disabled in the test env


def test_seed_demo_is_idempotent(db):
    client = TestClient(app)
    r1 = client.post("/api/seed-demo")
    assert r1.status_code == 200
    first = r1.json()
    assert first["state"]["historical_incidents"] == 18

    r2 = client.post("/api/seed-demo")
    assert r2.status_code == 200
    second = r2.json()

    # Re-running inserts nothing new and creates no duplicates.
    assert second["database"]["incidents"] == 0
    assert second["state"]["historical_incidents"] == 18
    assert client.get("/api/incidents").json().__len__() == 18


def test_openapi_includes_new_endpoints():
    client = TestClient(app)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/stats" in paths
    assert "/api/seed-demo" in paths
    assert "/api/incidents/{ref}/logs" in paths
