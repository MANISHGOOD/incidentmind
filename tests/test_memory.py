"""Memory layer: recall parsing, retain payloads, disabled mode."""
from types import SimpleNamespace

import pytest

from backend.memory.client import MemoryService


@pytest.fixture
def ms() -> MemoryService:
    svc = MemoryService()
    svc.set_runtime_enabled(True)  # tests opt in explicitly (env defaults to off)
    return svc


def test_enabled_defaults_to_settings(ms):
    assert isinstance(ms.enabled, bool)


def test_runtime_toggle_overrides_settings(ms):
    ms.set_runtime_enabled(False)
    assert ms.enabled is False
    ms.set_runtime_enabled(True)
    assert ms.enabled is True


def _fake_recall_response(texts):
    return SimpleNamespace(results=[SimpleNamespace(text=t, type="world", score=0.9) for t in texts])


async def _available(force=False):
    return True


def test_recall_extracts_incident_refs(ms, monkeypatch):
    async def fake_arecall(**kw):
        return _fake_recall_response([
            "Incident INC-0101 on service payment-api: Redis connection pool exhaustion.",
            "Incident INC-0107 on service payment-api: missing index caused latency spike.",
            "Incident INC-0101 mentioned again with more detail.",
        ])

    monkeypatch.setattr(ms.client, "arecall", fake_arecall)
    monkeypatch.setattr(ms, "check_available", _available)
    ctx = run(ms.recall("payment-api 503"))
    assert ctx.incident_refs == ["INC-0101", "INC-0107"]  # deduped, relevance order kept
    assert len(ctx.hits) == 3


def test_recall_unavailable_returns_empty(ms, monkeypatch):
    async def fail_arecall(**kw):
        raise RuntimeError("connection refused")

    async def unavailable(force=False):
        return False

    monkeypatch.setattr(ms.client, "arecall", fail_arecall)
    monkeypatch.setattr(ms, "check_available", unavailable)
    ctx = run(ms.recall("anything"))
    assert ctx.hits == [] and ctx.incident_refs == []


def test_recall_disabled_returns_empty(ms):
    ms.set_runtime_enabled(False)
    ctx = run(ms.recall("anything"))
    assert ctx.hits == [] and not ctx.incident_refs


def test_reflect_returns_text(ms, monkeypatch):
    async def fake_areflect(**kw):
        return SimpleNamespace(text="Redis exhaustion recurs on payment-api; pool sizing fixed it twice.")

    monkeypatch.setattr(ms.client, "areflect", fake_areflect)
    monkeypatch.setattr(ms, "check_available", _available)
    assert "Redis exhaustion" in run(ms.reflect("patterns?"))


def test_retain_builds_resolution_document(ms):
    doc = ms._resolution_document(
        ref="INC-0201", service="payment-api", environment="production", severity="high",
        started_at="2026-09-28T10:00:00+00:00", alert_text="Payment API 503",
        symptoms=["HTTP 503"], root_cause="pool exhaustion", action_taken="raise pool",
        outcome="resolved", lessons=["check pools first"],
    )
    assert "INC-0201" in doc
    assert "pool exhaustion" in doc
    assert "Lesson learned: check pools first" in doc


def run(coro):
    import asyncio
    return asyncio.run(coro)
