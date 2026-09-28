"""Application data model (PostgreSQL = application data, Hindsight = agent memory)."""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    team: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    ref: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # e.g. INC-0246
    title: Mapped[str] = mapped_column(String(300))
    service_name: Mapped[str] = mapped_column(String(100), index=True)
    environment: Mapped[str] = mapped_column(String(20), default="production")
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="investigating", index=True)
    alert_text: Mapped[str] = mapped_column(Text)
    symptoms: Mapped[str] = mapped_column(Text, default="")  # JSON list
    # Set when the engineer confirms the root cause / resolution.
    root_cause: Mapped[Optional[str]] = mapped_column(Text)
    memory_used: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    source_ref: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # historical seed ref

    events: Mapped[List["IncidentEvent"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", order_by="IncidentEvent.id"
    )
    resolutions: Mapped[List["Resolution"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )

    @property
    def symptoms_list(self) -> List[str]:
        import json

        return json.loads(self.symptoms) if self.symptoms else []


class IncidentEvent(Base):
    """One step of an investigation — the timeline and the step-count metric."""

    __tablename__ = "incident_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))  # tool_call | memory_hit | hypothesis | recommendation | note
    tool_name: Mapped[Optional[str]] = mapped_column(String(60))
    summary: Mapped[str] = mapped_column(Text)  # short human-readable line
    detail: Mapped[Optional[str]] = mapped_column(Text)  # full payload (JSON or text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="events")


class Resolution(Base):
    __tablename__ = "resolutions"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    root_cause: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(Text, default="resolved")
    lessons: Mapped[Optional[str]] = mapped_column(Text)  # JSON list
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    incident: Mapped[Incident] = relationship(back_populates="resolutions")


class LogEntry(Base):
    """One parsed log line attached to an incident (current or historical)."""

    __tablename__ = "log_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), index=True)
    ts: Mapped[Optional[str]] = mapped_column(String(40))
    level: Mapped[Optional[str]] = mapped_column(String(10))
    service_name: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    line: Mapped[str] = mapped_column(Text)


class Runbook(Base):
    __tablename__ = "runbooks"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    service_name: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    trigger: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)  # markdown
