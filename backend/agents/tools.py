"""Agent tools — the LLM's hands. Every tool is synchronous, DB-backed and logged
as an IncidentEvent so the UI timeline and the step-count metric are exact.
"""
import json
import re
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from ..models import Incident, IncidentEvent, LogEntry, Runbook
from ..memory.client import MemoryService
from ..schemas import SimilarIncident

# ---------------------------------------------------------------- helpers


def _parse_symptoms(incident: Incident) -> List[str]:
    try:
        return json.loads(incident.symptoms) if incident.symptoms else []
    except Exception:
        return []


def _historical_to_similar(inc: Incident, similarity: str) -> SimilarIncident:
    latest_resolution = inc.resolutions[-1] if inc.resolutions else None
    return SimilarIncident(
        ref=inc.ref,
        title=inc.title,
        service_name=inc.service_name,
        severity=inc.severity,
        similarity=similarity,
        root_cause=inc.root_cause or (latest_resolution.root_cause if latest_resolution else None),
        resolution=latest_resolution.action_taken if latest_resolution else None,
        outcome=latest_resolution.outcome if latest_resolution else None,
    )


def _memory_refs(ctx: Any) -> List[str]:
    return list(getattr(ctx, "incident_refs", []) or [])


# ---------------------------------------------------------------- tool defs


def get_incident(db: Session, incident_id: int) -> Dict[str, Any]:
    inc = db.get(Incident, incident_id)
    if inc is None:
        return {"error": "incident not found"}
    return {
        "ref": inc.ref,
        "title": inc.title,
        "service": inc.service_name,
        "environment": inc.environment,
        "severity": inc.severity,
        "status": inc.status,
        "alert_text": inc.alert_text,
        "symptoms": _parse_symptoms(inc),
        "started_at": inc.started_at.isoformat() if inc.started_at else None,
    }


def search_logs(db: Session, incident_id: int, query: str = "",
                level: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """Grep the current incident's log lines."""
    q = db.query(LogEntry).filter(LogEntry.incident_id == incident_id)
    if level:
        q = q.filter(LogEntry.level == level.upper())
    if query:
        like = f"%{query}%"
        q = q.filter(LogEntry.line.ilike(like))
    rows = q.order_by(LogEntry.id).limit(max(1, min(limit, 50))).all()
    return {
        "count": len(rows),
        "lines": [
            {"ts": r.ts, "level": r.level, "service": r.service_name, "line": r.line}
            for r in rows
        ],
    }


async def search_memory(memory: MemoryService, query: str,
                        incident: Incident, db: Session) -> Dict[str, Any]:
    """Recall similar past incidents from Hindsight, enriched from the app DB."""
    if not memory.enabled:
        return {"memory": "disabled", "note": "organizational memory is OFF for this run"}
    ctx = await memory.recall(query)
    refs = _memory_refs(ctx)

    similar: List[SimilarIncident] = []
    if refs:
        hist = (
            db.query(Incident)
            .options(selectinload(Incident.resolutions))
            .filter(Incident.ref.in_(refs), Incident.status == "resolved")
            .all()
        )
        by_ref = {h.ref: h for h in hist}
        for ref in refs:  # preserve recall relevance order
            if ref in by_ref:
                inc = by_ref[ref]
                similar.append(_historical_to_similar(inc, similarity="recalled from memory"))

    # Keep recall hits (raw memory text) AND enriched matches.
    return {
        "memory_hits": [{"text": h.text, "type": h.fact_type} for h in ctx.hits[:10]],
        "similar_incidents": [s.model_dump() for s in similar],
        "matched_refs": refs,
        "num_similar": len(similar),
    }


def compare_with_history(db: Session, ref: str) -> Dict[str, Any]:
    """Full record of a historical incident for comparison."""
    inc = (
        db.query(Incident)
        .options(selectinload(Incident.resolutions))
        .filter(Incident.ref == ref, Incident.status == "resolved")
        .first()
    )
    if inc is None:
        return {"error": f"no resolved incident {ref} in application database"}
    s = _historical_to_similar(inc, similarity="explicit comparison")
    d = s.model_dump()
    d["started_at"] = inc.started_at.isoformat() if inc.started_at else None
    d["environment"] = inc.environment
    return d


async def reflect_patterns(memory: MemoryService, service: str) -> Dict[str, Any]:
    """Ask organizational memory for recurring patterns (Hindsight reflect)."""
    if not memory.enabled:
        return {"memory": "disabled", "patterns": None}
    answer = await memory.reflect(
        f"For service '{service}' and the organization overall: which recurring problems, "
        "known dependencies and remediation patterns exist, and what worked before?"
    )
    return {"memory": "ok", "patterns": answer}


def get_runbook(db: Session, service: str, trigger: str = "") -> Dict[str, Any]:
    """Fetch the most relevant runbook, optionally filtered by trigger keywords."""
    q = db.query(Runbook).filter(Runbook.service_name == service)
    rows = q.all()
    if not rows:
        rows = db.query(Runbook).all()
    if not rows:
        return {"error": "no runbooks available"}

    def score(r: Runbook) -> int:
        text = f"{r.trigger or ''} {r.title}".lower()
        terms = [t for t in re.findall(r"[a-z0-9]+", trigger.lower()) if len(t) > 3]
        return sum(1 for t in terms if t in text)

    best = max(rows, key=score)
    return {
        "slug": best.slug,
        "title": best.title,
        "content": best.content,
    }


def record_step(db: Session, incident_id: int, kind: str, summary: str,
                detail: str = "", tool_name: str = "record_step") -> Dict[str, Any]:
    """Record a hypothesis/finding on the incident timeline."""
    if kind not in {"hypothesis", "note", "recommendation"}:
        kind = "note"
    seq = _next_seq(db, incident_id)
    ev = IncidentEvent(incident_id=incident_id, seq=seq, kind=kind,
                       tool_name=tool_name, summary=summary[:500],
                       detail=detail or None)
    db.add(ev)
    db.commit()
    return {"recorded": True, "seq": seq}


def _next_seq(db: Session, incident_id: int) -> int:
    last = (
        db.query(IncidentEvent)
        .filter(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.seq.desc())
        .first()
    )
    return (last.seq + 1) if last else 1


# ---------------------------------------------------------------- registry


class ToolRegistry:
    """Maps OpenAI-style tool names to callables + JSON schemas."""

    def __init__(self, db: Session, memory: MemoryService, incident: Incident):
        self.db = db
        self.memory = memory
        self.incident = incident
        self._impls: Dict[str, Callable[..., Any]] = {
            "get_incident": lambda **kw: get_incident(self.db, self.incident.id),
            "search_logs": lambda **kw: search_logs(
                self.db, self.incident.id,
                query=kw.get("query", ""), level=kw.get("level"),
                limit=kw.get("limit", 20),
            ),
            "search_memory": lambda **kw: _run_async(search_memory(
                self.memory, kw.get("query", ""),
                self.incident, self.db,
            )),
            "compare_with_history": lambda **kw: compare_with_history(
                self.db, kw.get("ref", "")
            ),
            "reflect_patterns": lambda **kw: _run_async(reflect_patterns(
                self.memory, kw.get("service", self.incident.service_name),
            )),
            "get_runbook": lambda **kw: get_runbook(
                self.db, kw.get("service", self.incident.service_name),
                kw.get("trigger", ""),
            ),
            "record_step": lambda **kw: record_step(
                self.db, self.incident.id, kw.get("kind", "note"),
                kw.get("summary", ""), kw.get("detail", ""),
            ),
        }

    def schemas(self) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_incident",
                    "description": "Get the current incident record: service, alert text, symptoms, severity.",
                    "parameters": {"type": "object", "properties": {}, "required": []},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_logs",
                    "description": (
                        "Grep the CURRENT incident's log lines for evidence. Try error signatures, "
                        "resource names (pool, connection, memory), status codes, provider errors."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "substring to search for"},
                            "level": {"type": "string", "enum": ["INFO", "WARN", "ERROR"]},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_memory",
                    "description": (
                        "Recall similar past incidents from organizational memory (Hindsight): "
                        "previous root causes, resolutions, outcomes. Use EARLY in every investigation."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "natural-language description of the incident: service, error signature, symptoms",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "compare_with_history",
                    "description": "Fetch the full record of a historical incident (by ref like INC-0101) to compare with current evidence.",
                    "parameters": {
                        "type": "object",
                        "properties": {"ref": {"type": "string"}},
                        "required": ["ref"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "reflect_patterns",
                    "description": "Ask organizational memory for recurring problems, dependencies and remediation patterns for this service.",
                    "parameters": {
                        "type": "object",
                        "properties": {"service": {"type": "string"}},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_runbook",
                    "description": "Fetch the operational runbook for a service/trigger.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service": {"type": "string"},
                            "trigger": {"type": "string", "description": "symptoms/keywords to pick the runbook"},
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "record_step",
                    "description": "Record a hypothesis, finding or note on the incident timeline.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string", "enum": ["hypothesis", "note", "recommendation"]},
                            "summary": {"type": "string"},
                            "detail": {"type": "string"},
                        },
                        "required": ["summary"],
                    },
                },
            },
        ]

    def execute(self, name: str, args_json: str) -> Dict[str, Any]:
        fn = self._impls.get(name)
        if fn is None:
            return {"error": f"unknown tool: {name}"}
        try:
            args = json.loads(args_json or "{}")
        except (json.JSONDecodeError, TypeError):
            # Feed the failure back so the model can correct its call format.
            return {"error": "invalid tool arguments: expected a JSON object"}
        if not isinstance(args, dict):
            return {"error": "invalid tool arguments: expected a JSON object"}
        return fn(**args)


def _run_async(coro: Any) -> Any:
    """Run an async tool impl from the (sync) tool registry."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # We're inside the server's event loop thread; run in a fresh loop thread.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(asyncio.run, coro).result(timeout=120)
    return asyncio.run(coro)
