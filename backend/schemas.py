"""Pydantic schemas for API requests and responses."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class IncidentCreate(BaseModel):
    service_name: str
    alert_text: str
    title: Optional[str] = None
    environment: str = "production"
    severity: str = "high"
    symptoms: List[str] = []


class ResolveRequest(BaseModel):
    root_cause: str
    action_taken: str
    outcome: str = "resolved"
    lessons: List[str] = []


class DemoSeedRequest(BaseModel):
    seed_db: bool = True
    seed_memory: bool = True


class IncidentEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    kind: str
    tool_name: Optional[str]
    summary: str
    detail: Optional[str]
    created_at: datetime


class ResolutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    root_cause: str
    action_taken: str
    outcome: str
    lessons: Optional[str]
    created_at: datetime


class IncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ref: str
    title: str
    service_name: str
    environment: str
    severity: str
    status: str
    alert_text: str
    symptoms: str
    root_cause: Optional[str]
    memory_used: bool
    started_at: datetime
    resolved_at: Optional[datetime]
    source_ref: Optional[str]

    @property
    def symptoms_parsed(self) -> List[str]:
        import json

        try:
            return json.loads(self.symptoms) if self.symptoms else []
        except Exception:
            return []


class IncidentDetailOut(IncidentOut):
    events: List[IncidentEventOut] = []
    resolutions: List[ResolutionOut] = []


class MemoryHit(BaseModel):
    """A recalled memory item normalized for the UI and the agent."""

    text: str
    fact_type: str = "world"
    score: Optional[float] = None


class SimilarIncident(BaseModel):
    ref: str
    title: str
    service_name: str
    severity: str
    similarity: str  # textual match justification
    root_cause: Optional[str] = None
    resolution: Optional[str] = None
    outcome: Optional[str] = None


class MemoryContext(BaseModel):
    """What Hindsight gave back for the current incident."""

    hits: List[MemoryHit] = []
    similar_incidents: List[SimilarIncident] = []
    patterns: List[str] = []
    incident_refs: List[str] = []  # deduped incident refs found in hits, relevance-ordered


class Recommendation(BaseModel):
    """Agent output — a proposal for the engineer, never an autonomous action."""

    summary: str
    likely_root_causes: List[Dict[str, Any]] = []
    historical_match: Optional[Dict[str, Any]] = None
    applies_to_current_evidence: Optional[str] = None
    investigation_steps: List[str] = []
    proposed_actions: List[str] = []
    confidence: str = "medium"  # low | medium | high


class MetricSummary(BaseModel):
    with_memory: Dict[str, Any]
    without_memory: Dict[str, Any]
    retention: Dict[str, Any] = {}
