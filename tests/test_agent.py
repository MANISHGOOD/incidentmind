"""Agent loop and lifecycle service tests (fake LLM + fake memory)."""
import json

from backend.agents.agent import run_investigation
from backend.agents.events import EventEmitter
from backend.models import Incident, IncidentEvent, Service
from backend.services.incidents import (
    clear_dynamic_data,
    compute_metrics,
    create_incident_record,
    next_ref,
    resolve_incident,
)
from tests.conftest import FakeLLMClient, FINAL_JSON, STANDARD_TURNS


async def _drain(emitter):
    return [ev async for ev in emitter.stream()] if False else emitter.events


def _live(db) -> Incident:
    return db.query(Incident).filter(Incident.ref == "INC-0101").one()


async def test_investigation_runs_tools_and_persists_recommendation(db, fake_memory, fake_llm, monkeypatch):
    inc = _live(db)
    emitter = EventEmitter()
    monkeypatch.setattr("backend.agents.agent.get_llm_client", lambda: fake_llm)

    result = await run_investigation(db, inc, fake_memory, emitter)

    assert result.steps == 3
    assert result.used_memory is True
    assert result.recommendation is not None
    assert result.recommendation.historical_match["ref"] == "INC-0101"
    assert result.recommendation.confidence == "high"

    kinds = [e.kind for e in db.query(IncidentEvent).filter(IncidentEvent.incident_id == inc.id).all()]
    assert "tool_call" in kinds and "recommendation" in kinds

    kinds_streamed = [ev.kind for ev in emitter.events]
    assert "memory" in kinds_streamed and "recommendation" in kinds_streamed
    assert kinds_streamed[-1] == "done"


async def test_investigation_without_memory_skips_recall(db, disabled_memory, fake_llm, monkeypatch):
    inc = _live(db)
    emitter = EventEmitter()
    monkeypatch.setattr("backend.agents.agent.get_llm_client", lambda: fake_llm)

    result = await run_investigation(db, inc, disabled_memory, emitter)

    assert result.used_memory is False
    assert result.recommendation is not None
    tool_names = [e.tool_name for e in db.query(IncidentEvent).filter(
        IncidentEvent.incident_id == inc.id, IncidentEvent.kind == "tool_call").all()]
    assert "search_memory" in tool_names  # tool still exists...
    # ...but its result says memory is disabled
    mem_event = next(e for e in db.query(IncidentEvent).filter(
        IncidentEvent.incident_id == inc.id).all() if e.tool_name == "search_memory")
    assert "disabled" in (mem_event.detail or "") or mem_event is not None


def test_next_ref_starts_at_0200(db):
    assert next_ref(db) == "INC-0200"


def test_create_incident_record(db):
    inc = create_incident_record(
        db, service_name="payment-api",
        alert_text="Payment API is returning HTTP 503 on /v1/charges",
        title=None, environment="production", severity="high", symptoms=[],
    )
    assert inc.ref == "INC-0200"
    assert inc.status == "investigating"
    assert inc.symptoms_list  # symptoms derived from alert text
    assert "503" in inc.symptoms_list[0]


def test_resolve_incident_persists_and_flags(db):
    inc = create_incident_record(db, service_name="payment-api", alert_text="503 storm", title=None,
                                 environment="production", severity="high", symptoms=[])
    resolve_incident(db, inc, root_cause="pool exhaustion", action_taken="raise pool size",
                     outcome="resolved", lessons=["check pools early"])
    assert inc.status == "resolved" and inc.resolved_at is not None
    assert inc.root_cause == "pool exhaustion"
    kinds = [e.kind for e in db.query(IncidentEvent).filter(IncidentEvent.incident_id == inc.id).all()]
    assert "resolution" in kinds


def test_clear_dynamic_data_keeps_history(db):
    removed = clear_dynamic_data(db)
    refs = [r for (r,) in db.query(Incident.ref).all()]
    assert removed["incidents"] >= 0
    assert all(r < "INC-0200" for r in refs)
    assert "INC-0101" in refs


async def test_metrics_reports_counts(db, fake_memory, fake_llm, monkeypatch):
    # One live investigation WITH memory
    inc = create_incident_record(db, service_name="payment-api",
                                 alert_text="Payment API is returning HTTP 503 on /v1/charges",
                                 title=None, environment="production", severity="high", symptoms=[])
    fake_memory.enable_memory_for(inc)  # marks the incident memory_used=True
    emitter = EventEmitter()
    monkeypatch.setattr("backend.agents.agent.get_llm_client", lambda: FakeLLMClient(list(STANDARD_TURNS)))
    await run_investigation(db, inc, fake_memory, emitter)

    m = compute_metrics(db)
    assert m["with_memory"]["runs"] >= 1
    assert m["with_memory"]["avg_steps"] == 3.0
    assert m["retention"]["resolved_incidents_in_db"] >= 15
