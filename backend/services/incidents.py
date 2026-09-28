"""Incident lifecycle logic: creation, resolution + memory retention, demo seeds."""
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..models import Incident, IncidentEvent, LogEntry, Resolution, Runbook, Service
from ..memory.client import MemoryService

logger = logging.getLogger("incidentmind.incidents")

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
HISTORICAL_REF_RE = re.compile(r"^INC-(\d{4})$")
NEXT_DYNAMIC_REF_START = 200  # live incidents start at INC-0200


def next_ref(db: Session) -> str:
    nums = []
    for (ref,) in db.query(Incident.ref).all():
        m = HISTORICAL_REF_RE.match(ref)
        if m:
            nums.append(int(m.group(1)))
    nxt = max(nums + [NEXT_DYNAMIC_REF_START - 1]) + 1
    return f"INC-{nxt:04d}"


def _parse_ts(value: Optional[str]) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_dataset() -> Tuple[List[dict], Dict[str, str], Dict[str, str]]:
    """Read incidents.json + log files + runbooks from /data."""
    import json as _json

    incidents = _json.loads((DATA_DIR / "incidents" / "incidents.json").read_text(encoding="utf-8"))
    logs: Dict[str, str] = {}
    for inc in incidents:
        lf = inc.get("log_file")
        if lf:
            p = DATA_DIR / "logs" / lf
            if p.exists():
                logs[inc["id"]] = p.read_text(encoding="utf-8")
    runbooks: Dict[str, str] = {}
    rb_dir = DATA_DIR / "runbooks"
    for p in sorted(rb_dir.glob("*.md")):
        runbooks[p.stem] = p.read_text(encoding="utf-8")
    return incidents, logs, runbooks


def seed_demo_data(db: Session) -> Dict[str, int]:
    """Idempotently load historical incidents, their logs and runbooks."""
    incidents, logs, runbooks = load_dataset()
    counts = {"incidents": 0, "logs": 0, "runbooks": 0}

    for rb_slug, content in runbooks.items():
        if db.query(Runbook).filter(Runbook.slug == rb_slug).first():
            continue
        first_line = content.splitlines()[0].lstrip("# ").strip() if content else rb_slug
        service = None
        m = re.search(r"\*\*Service:\*\*\s*([a-z0-9-]+)", content)
        if m:
            service = m.group(1)
        db.add(Runbook(slug=rb_slug, title=first_line, service_name=service, content=content))
        counts["runbooks"] += 1

    for svc in sorted({i["service"] for i in incidents}):
        if not db.query(Service).filter(Service.name == svc).first():
            db.add(Service(name=svc, description="seeded from synthetic dataset"))
            counts["incidents"] += 0  # services tracked separately, not counted

    for data in incidents:
        ref = data["id"]
        if db.query(Incident).filter(Incident.ref == ref).first():
            continue
        inc = Incident(
            ref=ref,
            title=data["title"],
            service_name=data["service"],
            environment=data.get("environment", "production"),
            severity=data.get("severity", "medium"),
            status="resolved",
            alert_text=data["alert_text"],
            symptoms=json.dumps(data.get("symptoms", [])),
            root_cause=data.get("root_cause"),
            memory_used=True,
            started_at=_parse_ts(data.get("started_at")),
            resolved_at=_parse_ts(data.get("resolved_at")) if data.get("resolved_at") else None,
            source_ref=ref,
        )
        db.add(inc)
        db.flush()  # assign inc.id
        db.add(Resolution(
            incident_id=inc.id,
            root_cause=data.get("root_cause", ""),
            action_taken=data.get("resolution", ""),
            outcome=data.get("outcome", "resolved"),
            lessons=json.dumps(data.get("lessons", [])),
        ))
        for line in logs.get(ref, "").splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(
                r"(\d{4}-\d{2}-\d{2}T[\d:]+Z)\s+(\w+)\s+([\w-]+)\s+(.*)", line
            )
            ts, level, svc, rest = (
                (m.group(1), m.group(2), m.group(3), m.group(4)) if m else (None, None, None, line)
            )
            db.add(LogEntry(incident_id=inc.id, ts=ts, level=level, service_name=svc, line=line))
            counts["logs"] += 1
        counts["incidents"] += 1

    db.commit()
    return counts


def create_incident_record(
    db: Session, *, service_name: str, alert_text: str, title: Optional[str],
    environment: str = "production", severity: str = "high",
    symptoms: Optional[List[str]] = None,
) -> Incident:
    """Create a live incident (INC-02xx) from an alert."""
    symptoms = symptoms or [
        s.strip() for s in alert_text.replace(";", ",").split(",") if s.strip()
    ][:6]
    inc = Incident(
        ref=next_ref(db),
        title=title or alert_text[:120],
        service_name=service_name,
        environment=environment,
        severity=severity,
        status="investigating",
        alert_text=alert_text,
        symptoms=json.dumps(symptoms),
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return inc


def clear_dynamic_data(db: Session) -> Dict[str, int]:
    """Reset for the demo: drop live incidents (INC-02xx+), keep historical seeds."""
    live = db.query(Incident).filter(Incident.ref >= "INC-0200").all()
    removed = {"incidents": len(live)}
    for inc in live:
        db.delete(inc)  # cascades to events, resolutions, logs
    db.commit()
    return removed


async def seed_memory_from_history(db: Session, memory: MemoryService) -> Dict[str, Any]:
    """Retain all resolved historical incidents into Hindsight (demo step 2)."""
    incidents, _, _ = load_dataset()
    retained, failed = 0, 0
    for data in incidents:
        lessons = data.get("lessons", [])
        content = "\n".join([
            f"Incident {data['id']} on service {data['service']} "
            f"({data.get('environment', 'production')}, severity {data.get('severity', 'medium')}), "
            f"started {data.get('started_at', 'unknown')}.",
            f"Alert: {data['alert_text']}",
            f"Symptoms: {'; '.join(data.get('symptoms', []))}.",
            f"Root cause: {data.get('root_cause', 'unknown')}",
            f"Resolution: {data.get('resolution', 'unknown')}",
            f"Outcome: {data.get('outcome', 'resolved')}",
            *[f"Lesson learned: {lesson}" for lesson in lessons],
        ])
        ok = await memory.seed_historical_incident(
            content,
            ref=data["id"],
            service=data["service"],
            started_at=_parse_ts(data.get("started_at")),
        )
        if ok:
            retained += 1
        else:
            failed += 1
    return {"retained": retained, "failed": failed, "total": len(incidents)}


def resolve_incident(
    db: Session,
    incident: Incident,
    *,
    root_cause: str,
    action_taken: str,
    outcome: str = "resolved",
    lessons: Optional[List[str]] = None,
) -> Resolution:
    """Engineer-approved resolution: persist it. Memory retention is done by the API layer."""
    lessons = lessons or []
    res = Resolution(
        incident_id=incident.id,
        root_cause=root_cause,
        action_taken=action_taken,
        outcome=outcome,
        lessons=json.dumps(lessons),
    )
    db.add(res)
    incident.root_cause = root_cause
    incident.status = "resolved"
    incident.resolved_at = datetime.now(timezone.utc)
    db.add(IncidentEvent(
        incident_id=incident.id,
        seq=_next_event_seq(db, incident.id),
        kind="resolution",
        tool_name="engineer_resolution",
        summary=f"Resolved: {root_cause[:180]}",
        detail=json.dumps({"action_taken": action_taken, "outcome": outcome, "lessons": lessons}),
    ))
    db.commit()
    db.refresh(incident)
    return res


def _next_event_seq(db: Session, incident_id: int) -> int:
    last = (
        db.query(IncidentEvent)
        .filter(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.seq.desc())
        .first()
    )
    return (last.seq + 1) if last else 1


def compute_metrics(db: Session) -> Dict[str, Any]:
    """Investigation effort with vs. without memory — measured, not claimed.

    A metric pair only counts when the SAME alert template has been
    investigated both ways, so the comparison is like-for-like.
    """
    def summarize(incidents: List[Incident]) -> Dict[str, Any]:
        if not incidents:
            return {"runs": 0, "avg_steps": None}
        runs = []
        for inc in incidents:
            steps = (
                db.query(IncidentEvent)
                .filter(IncidentEvent.incident_id == inc.id,
                        IncidentEvent.kind == "tool_call")
                .count()
            )
            runs.append(steps)
        return {
            "runs": len(runs),
            "avg_steps": round(sum(runs) / len(runs), 1),
            "min_steps": min(runs),
            "max_steps": max(runs),
        }

    all_inc = db.query(Incident).filter(Incident.ref >= "INC-0200").all()
    with_m = [i for i in all_inc if i.memory_used]
    without_m = [i for i in all_inc if not i.memory_used]

    with_alerts = {i.alert_text.strip() for i in with_m}
    without_alerts = {i.alert_text.strip() for i in without_m}
    common = with_alerts & without_alerts

    comparable_with = [i for i in with_m if i.alert_text.strip() in common]
    comparable_without = [i for i in without_m if i.alert_text.strip() in common]

    return {
        "with_memory": summarize(comparable_with or with_m),
        "without_memory": summarize(comparable_without or without_m),
        "retention": {
            "resolved_incidents_in_db": db.query(Incident).filter(Incident.status == "resolved").count(),
            "paired_comparisons": len(common),
            "note": "avg_steps = agent tool calls per investigation; paired when the same alert was run both ways",
        },
    }
