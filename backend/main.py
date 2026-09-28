"""IncidentMind FastAPI application."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from .agents.agent import run_investigation
from .agents.events import EventEmitter
from .agents.llm import LLMNotConfiguredError
from .config import get_settings
from .database import get_db, init_db
from .memory.client import get_memory
from .models import Incident, IncidentEvent, LogEntry, Runbook, Service
from .schemas import (
    DemoSeedRequest,
    IncidentCreate,
    IncidentDetailOut,
    IncidentOut,
    ResolveRequest,
)
from .services.incidents import (
    clear_dynamic_data,
    compute_metrics,
    create_incident_record,
    load_dataset,
    resolve_incident,
    seed_demo_data,
    seed_memory_from_history,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("incidentmind.api")


async def _auto_restore_memory() -> None:
    """Rebuild organizational memory in the background after boot.

    Free-tier Hindsight is ephemeral (Render disks are paid-only), so memory
    is re-retained on every fresh container: idempotent by document id
    (incident refs). Skipped when the bank already has entries.
    """
    memory = get_memory()
    if not (memory.enabled and await memory.check_available(force=True)):
        logger.info("Hindsight not reachable — organizational memory self-heal skipped this boot")
        return
    try:
        mem_stats = await memory.stats()
        if mem_stats.get("entries"):
            logger.info("Organizational memory already populated (%s entries)", mem_stats["entries"])
            return
        db = next(get_db())
        try:
            mem_counts = await seed_memory_from_history(db, memory)
            logger.info("Organizational memory restored: %s", mem_counts)
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("Memory auto-seed skipped: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    db = next(get_db())
    try:
        counts = seed_demo_data(db)
        logger.info("Demo data ready: %s", counts)
    except Exception as e:  # noqa: BLE001
        logger.warning("Demo data seeding skipped: %s", e)
    finally:
        db.close()

    memory = get_memory()
    logger.info(
        "IncidentMind up — model=%s memory=%s@%s (enabled=%s)",
        settings.agent_model,
        settings.hindsight_bank_id,
        settings.hindsight_url,
        memory.enabled,
    )
    # Non-blocking: don't hold the health check hostage while memory restores.
    asyncio.create_task(_auto_restore_memory())
    yield


app = FastAPI(title="IncidentMind API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    return {"status": "ok", "service": "incidentmind-api"}


# ------------------------------------------------------------------ overview


@app.get("/api/overview")
def overview(db: Session = Depends(get_db)) -> dict:
    active = db.query(Incident).filter(Incident.status != "resolved").count()
    resolved = db.query(Incident).filter(Incident.status == "resolved").count()
    return {"active_incidents": active, "resolved_incidents": resolved}


@app.get("/api/stats")
async def stats(db: Session = Depends(get_db)) -> dict:
    """Dashboard statistics: incidents, memory entries, known patterns."""
    total = db.query(Incident).count()
    active = db.query(Incident).filter(Incident.status != "resolved").count()
    resolved = db.query(Incident).filter(Incident.status == "resolved").count()
    # "Known patterns" = distinct root causes in resolved incidents — the
    # organization's accumulated remediation knowledge.
    known_patterns = (
        db.query(func.count(func.distinct(Incident.root_cause)))
        .filter(Incident.root_cause.isnot(None), Incident.root_cause != "")
        .scalar()
        or 0
    )
    services = db.query(func.count(func.distinct(Incident.service_name))).scalar() or 0
    runbooks = db.query(Runbook).count()
    mem = await get_memory().stats()
    return {
        "total_incidents": total,
        "active_incidents": active,
        "resolved_incidents": resolved,
        "memory_entries": mem.get("entries"),
        "memory_available": mem.get("available", False),
        "known_patterns": known_patterns,
        "services": services,
        "runbooks": runbooks,
    }


@app.get("/api/memory/stats")
async def memory_stats() -> dict:
    """Hindsight availability + entry counts for the memory panel."""
    return await get_memory().stats()


@app.post("/api/memory/toggle")
async def memory_toggle(body: dict) -> dict:
    """Per-run A/B switch: enable/disable the memory layer at runtime."""
    memory = get_memory()
    memory.set_runtime_enabled(bool(body.get("enabled", True)))
    return {"memory_enabled": memory.enabled}


# ------------------------------------------------------------------ incidents


@app.get("/api/incidents")
def list_incidents(status: Optional[str] = None, db: Session = Depends(get_db)) -> List[IncidentOut]:
    q = db.query(Incident).order_by(Incident.started_at.desc())
    if status:
        q = q.filter(Incident.status == status)
    return q.limit(100).all()


@app.get("/api/incidents/{ref}")
def get_incident(ref: str, db: Session = Depends(get_db)) -> IncidentDetailOut:
    inc = (
        db.query(Incident)
        .options(selectinload(Incident.events), selectinload(Incident.resolutions))
        .filter(Incident.ref == ref)
        .first()
    )
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    return inc


@app.get("/api/incidents/{ref}/logs")
def get_incident_logs(ref: str, limit: int = 50, db: Session = Depends(get_db)) -> dict:
    """Evidence: the incident's captured log lines."""
    inc = db.query(Incident).filter(Incident.ref == ref).first()
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    rows = (
        db.query(LogEntry)
        .filter(LogEntry.incident_id == inc.id)
        .order_by(LogEntry.id)
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return {
        "ref": ref,
        "count": len(rows),
        "lines": [
            {"ts": r.ts, "level": r.level, "service": r.service_name, "line": r.line}
            for r in rows
        ],
    }


@app.post("/api/incidents", status_code=201)
def create_incident(body: IncidentCreate, db: Session = Depends(get_db)) -> IncidentOut:
    return create_incident_record(
        db,
        service_name=body.service_name,
        alert_text=body.alert_text,
        title=body.title,
        environment=body.environment,
        severity=body.severity,
        symptoms=body.symptoms,
    )


@app.post("/api/incidents/{ref}/investigate")
async def investigate(ref: str, db: Session = Depends(get_db)) -> StreamingResponse:
    """Run the agent investigation, streaming the timeline via SSE."""
    inc = (
        db.query(Incident)
        .options(selectinload(Incident.resolutions))
        .filter(Incident.ref == ref)
        .first()
    )
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")

    memory = get_memory()
    emitter = EventEmitter()

    async def run() -> None:
        own_db = next(get_db())
        try:
            fresh_inc = own_db.get(Incident, inc.id)  # rebind to this session
            await run_investigation(own_db, fresh_inc, memory, emitter)
        except Exception as e:  # noqa: BLE001
            logger.exception("investigation crashed")
            emitter.emit("error", f"Investigation crashed: {e}")
            emitter.emit("done", "Investigation ended with error")
        finally:
            own_db.close()

    async def sse() -> AsyncIterator[str]:
        task = asyncio.create_task(run())
        try:
            async for ev in emitter.stream():
                payload = {"kind": ev.kind, "message": ev.message}
                if ev.data is not None:
                    payload["data"] = ev.data
                yield f"data: {json.dumps(payload, default=str)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/incidents/{ref}/resolve")
async def resolve(ref: str, body: ResolveRequest, db: Session = Depends(get_db)) -> dict:
    """Engineer-approved resolution: persists it, then retains to Hindsight."""
    inc = db.query(Incident).filter(Incident.ref == ref).first()
    if inc is None:
        raise HTTPException(status_code=404, detail="incident not found")
    resolve_incident(
        db, inc,
        root_cause=body.root_cause,
        action_taken=body.action_taken,
        outcome=body.outcome,
        lessons=body.lessons,
    )
    memory = get_memory()
    retained = await memory.retain_incident_resolution(
        ref=inc.ref,
        service=inc.service_name,
        environment=inc.environment,
        severity=inc.severity,
        started_at=inc.started_at,
        alert_text=inc.alert_text,
        symptoms=inc.symptoms_list,
        root_cause=body.root_cause,
        action_taken=body.action_taken,
        outcome=body.outcome,
        lessons=body.lessons,
    )
    return {"resolved": True, "memory_retained": retained}


# ------------------------------------------------------------------ runbooks


@app.get("/api/runbooks")
def list_runbooks(db: Session = Depends(get_db)) -> List[dict]:
    rows = db.query(Runbook).order_by(Runbook.slug).all()
    return [
        {"slug": r.slug, "title": r.title, "service_name": r.service_name, "content": r.content}
        for r in rows
    ]


# ------------------------------------------------------------------ demo controls


@app.post("/api/demo/reset")
def demo_reset(db: Session = Depends(get_db)) -> dict:
    """Demo step 1: drop live incidents so only historical seeds remain."""
    removed = clear_dynamic_data(db)
    return {"cleared": removed, "state": "fresh — historical incidents only"}


@app.post("/api/demo/seed-memory")
async def demo_seed_memory(body: Optional[DemoSeedRequest] = None) -> dict:
    """Demo step 2: load historical incidents into organizational memory."""
    if body is None:
        body = DemoSeedRequest()
    memory = get_memory()
    if not memory.enabled:
        raise HTTPException(status_code=400, detail="memory is disabled — enable it first")
    db = next(get_db())
    try:
        return await seed_memory_from_history(db, memory)
    finally:
        db.close()


@app.post("/api/seed-demo")
async def seed_demo() -> dict:
    """Idempotent demo seeding: PostgreSQL application data + Hindsight memory.

    Safe to call repeatedly — incidents are keyed by deterministic refs
    (INC-01xx) so re-running inserts nothing new; memory retain uses the same
    document ids so Hindsight re-anchors rather than duplicates.
    """
    db = next(get_db())
    try:
        db_counts = seed_demo_data(db)
        memory = get_memory()
        if memory.enabled and await memory.check_available():
            mem_result = await seed_memory_from_history(db, memory)
        else:
            dataset, _, _ = load_dataset()
            mem_result = {
                "skipped": True,
                "reason": "hindsight unavailable or memory disabled",
                "total": len(dataset),
            }
        state = {
            "live_incidents": db.query(Incident).filter(Incident.ref >= "INC-0200").count(),
            "historical_incidents": db.query(Incident).filter(Incident.ref < "INC-0200").count(),
        }
        return {"database": db_counts, "memory": mem_result, "state": state}
    finally:
        db.close()


@app.get("/api/demo/state")
def demo_state(db: Session = Depends(get_db)) -> dict:
    live = db.query(Incident).filter(Incident.ref >= "INC-0200").count()
    hist = db.query(Incident).filter(Incident.ref < "INC-0200").count()
    return {"live_incidents": live, "historical_incidents": hist}


@app.get("/api/metrics")
def metrics(db: Session = Depends(get_db)) -> dict:
    return compute_metrics(db)
