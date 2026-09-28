"""Agent tools against the seeded dataset."""
import sqlalchemy as sa

from backend.agents.tools import (
    ToolRegistry,
    compare_with_history,
    get_incident,
    get_runbook,
    record_step,
    search_logs,
)
from backend.models import Incident


def _live_incident(db) -> Incident:
    return db.query(Incident).filter(Incident.ref == "INC-0101").one()


def test_get_incident(db):
    result = get_incident(db, _live_incident(db).id)
    assert result["ref"] == "INC-0101"
    assert result["service"] == "payment-api"
    assert "503" in result["alert_text"]
    assert isinstance(result["symptoms"], list) and result["symptoms"]


def test_search_logs_finds_pool_timeouts(db):
    inc = _live_incident(db)
    result = search_logs(db, inc.id, query="pool timed out")
    assert result["count"] >= 2
    assert all("pool timed out" in row["line"] for row in result["lines"])


def test_search_logs_level_filter(db):
    inc = _live_incident(db)
    result = search_logs(db, inc.id, level="ERROR", limit=50)
    assert result["count"] > 0
    assert all(row["level"] == "ERROR" for row in result["lines"])


def test_compare_with_history(db):
    d = compare_with_history(db, "INC-0101")
    assert d["ref"] == "INC-0101"
    assert "Redis" in d["root_cause"]
    assert d["resolution"] and d["outcome"]


def test_compare_with_history_unknown_ref(db):
    assert "error" in compare_with_history(db, "INC-9999")


def test_get_runbook_matches_service_and_trigger(db):
    rb = get_runbook(db, "payment-api", "503 redis pool timeout")
    assert rb["slug"] == "payment-api-503"
    assert "Redis connection pool exhaustion" in rb["content"]


def test_get_runbook_fallback(db):
    rb = get_runbook(db, "nonexistent-service", "")
    assert "content" in rb  # falls back to any runbook


def test_record_step_appends_timeline(db):
    inc = _live_incident(db)
    r1 = record_step(db, inc.id, "hypothesis", "first hypothesis")
    r2 = record_step(db, inc.id, "note", "second note")
    assert (r1["seq"], r2["seq"]) == (1, 2)
    kinds = db.execute(
        sa.text("SELECT kind FROM incident_events WHERE incident_id=:i ORDER BY seq"),
        {"i": inc.id},
    ).scalars().all()
    assert kinds == ["hypothesis", "note"]


def test_record_step_rejects_unknown_kind(db):
    inc = _live_incident(db)
    r = record_step(db, inc.id, "bogus-kind", "summary")
    assert r["recorded"]


# ------------------------------------------------------------------ registry


def test_registry_executes_and_handles_bad_args(db, fake_memory):
    inc = _live_incident(db)
    reg = ToolRegistry(db, fake_memory, inc)
    out = reg.execute("search_logs", '{"query": "503", "limit": 5}')
    assert out["count"] > 0
    assert "error" in reg.execute("no_such_tool", "{}")
    assert "error" in reg.execute("search_logs", "not-json")


def test_registry_search_memory_disabled(db, disabled_memory):
    inc = _live_incident(db)
    reg = ToolRegistry(db, disabled_memory, inc)
    out = reg.execute("search_memory", '{"query": "payment-api 503"}')
    assert out["memory"] == "disabled"


def test_registry_search_memory_finds_seeded_incident(db, fake_memory):
    fake_memory.recall_results = [
        {"text": "Incident INC-0101 on service payment-api ... Redis connection pool exhaustion ... HTTP 503.", "type": "world"},
    ]
    inc = _live_incident(db)
    reg = ToolRegistry(db, fake_memory, inc)
    out = reg.execute("search_memory", '{"query": "payment-api 503"}')
    assert out["num_similar"] == 1
    match = out["similar_incidents"][0]
    assert match["ref"] == "INC-0101"
    assert "Redis" in match["root_cause"]
    assert match["outcome"]
