"""Shared fixtures: temp SQLite DB, seeded demo data, fake memory + fake LLM."""
import os
import re
from pathlib import Path
from types import SimpleNamespace

# Configure env BEFORE importing backend modules (the engine is built at import time).
ROOT = Path(__file__).resolve().parents[1]
TEST_DB = ROOT / "test_incidentmind.db"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ.setdefault("MEMORY_ENABLED", "false")  # tests opt in explicitly per case

import pytest  # noqa: E402

from backend.database import Base, SessionLocal, engine  # noqa: E402
from backend.schemas import MemoryContext, MemoryHit  # noqa: E402
from backend.services.incidents import seed_demo_data  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    seed_demo_data(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


class FakeMemory:
    """MemoryService stand-in: no Hindsight, fully scripted."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.retained: list = []
        self.seeded: list = []
        self.recall_results: list = []
        self.reflect_answer: str | None = None

    async def check_available(self, force: bool = False) -> bool:
        return True

    async def recall(self, query: str, *, max_tokens: int = 2500) -> MemoryContext:
        if not self.enabled:
            return MemoryContext()
        hits = [MemoryHit(text=r["text"], fact_type=r.get("type", "world")) for r in self.recall_results]
        refs: list = []
        for r in self.recall_results:
            refs.extend(re.findall(r"INC-\d{3,}", r["text"]))
        seen: set = set()
        ctx = MemoryContext(hits=hits)
        setattr(ctx, "incident_refs", [x for x in refs if not (x in seen or seen.add(x))])
        return ctx

    async def reflect(self, query: str):
        return self.reflect_answer if self.enabled else None

    async def retain_incident_resolution(self, **kw) -> bool:
        if not self.enabled:
            return False
        self.retained.append(kw)
        return True

    async def seed_historical_incident(self, doc: str, *, ref: str, service: str, started_at) -> bool:
        if not self.enabled:
            return False
        self.seeded.append(ref)
        return True

    async def stats(self) -> dict:
        return {"enabled": self.enabled, "available": True, "entries": len(self.seeded) + len(self.retained)}

    def enable_memory_for(self, incident) -> None:
        """Mark an incident as a memory-assisted run (as the API route would)."""
        incident.memory_used = True


@pytest.fixture()
def fake_memory():
    return FakeMemory(enabled=True)


@pytest.fixture()
def disabled_memory():
    return FakeMemory(enabled=False)


# ------------------------------------------------------------------ fake LLM


def _tool_call(cid: str, name: str, args: dict) -> SimpleNamespace:
    return SimpleNamespace(id=cid, function=SimpleNamespace(name=name, arguments=__import__("json").dumps(args)))


def _response(content=None, tool_calls=None) -> SimpleNamespace:
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


class FakeLLMClient:
    """OpenAI-compatible client stand-in with a scripted sequence of turns."""

    def __init__(self, turns: list):
        self.turns = list(turns)
        self.calls: list = []

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    async def create(self, **kw):
        self.calls.append(kw)
        if not self.turns:
            raise AssertionError("FakeLLM ran out of scripted turns")
        return self.turns.pop(0)


FINAL_JSON = {
    "summary": "Redis connection pool exhaustion on payment-api; matches INC-0101.",
    "likely_root_causes": [{"cause": "Redis pool exhaustion", "confidence": "high", "evidence": "pool timed out in logs"}],
    "historical_match": {"ref": "INC-0101", "why_similar": "same 503 signature", "root_cause": "Redis connection pool exhaustion",
                          "resolution": "Hotfix leak + raise pool + restart workers", "outcome": "Recovered"},
    "applies_to_current_evidence": "Yes — current logs show the same pool timeout signature.",
    "investigation_steps": ["Check pool metrics", "Verify leak fix deployed"],
    "proposed_actions": ["Increase REDIS_POOL_SIZE to 50", "Restart affected workers"],
    "confidence": "high",
}

import json as _json  # noqa: E402

STANDARD_TURNS = [
    _response(tool_calls=[_tool_call("c1", "search_memory", {"query": "payment-api 503"})]),
    _response(tool_calls=[_tool_call("c2", "search_logs", {"query": "pool"})]),
    _response(tool_calls=[_tool_call("c3", "record_step", {"kind": "hypothesis", "summary": "Redis pool exhaustion"})]),
    _response(content=_json.dumps(FINAL_JSON)),
]


@pytest.fixture()
def fake_llm():
    return FakeLLMClient(STANDARD_TURNS)
