"""Hindsight-backed organizational memory.

Hindsight = the agent's persistent memory (facts, experiences, observations).
This wrapper is the ONLY place that talks to Hindsight, so the rest of the
app stays memory-agnostic and the demo A/B toggle lives in one flag.

Graceful degradation: if the Hindsight server is unreachable the app keeps
working with empty memory (the dashboard shows availability status).
"""
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Callable, List, Optional

from hindsight_client import Hindsight

from ..config import Settings, get_settings
from ..schemas import MemoryContext, MemoryHit

logger = logging.getLogger("incidentmind.memory")

_INCIDENT_REF_RE = re.compile(r"INC-\d{3,}")


class MemoryUnavailableError(RuntimeError):
    pass


class MemoryService:
    """Thin async wrapper over the hindsight-client SDK."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._client: Optional[Hindsight] = None
        self._runtime_bank_id: Optional[str] = None  # demo reset swaps banks
        self._runtime_enabled: Optional[bool] = None  # per-run A/B override
        self._available: Optional[bool] = None
        self._checked_at: float = 0.0

    # ---- lifecycle -------------------------------------------------------

    @property
    def bank_id(self) -> str:
        return self._runtime_bank_id or self.settings.hindsight_bank_id

    def set_runtime_bank(self, bank_id: str) -> None:
        self._runtime_bank_id = bank_id
        self._available = None

    @property
    def enabled(self) -> bool:
        """Per-run override (demo A/B toggle) wins over the global setting."""
        if self._runtime_enabled is not None:
            return self._runtime_enabled
        return self.settings.memory_enabled

    def set_runtime_enabled(self, value: bool) -> None:
        self._runtime_enabled = value

    @property
    def client(self) -> Hindsight:
        if self._client is None:
            self._client = Hindsight(
                base_url=self.settings.hindsight_base_url,
                api_key=self.settings.hindsight_api_key or None,
                timeout=60.0,
            )
        return self._client

    async def check_available(self, force: bool = False) -> bool:
        """Cheap availability probe, cached for 30s."""
        import time

        now = time.monotonic()
        if not force and self._available is not None and now - self._checked_at < 30:
            return self._available
        try:
            await asyncio.wait_for(self.client.aget_version(), timeout=5)
            self._available = True
        except Exception as e:  # noqa: BLE001 — any failure means "no memory"
            logger.warning("Hindsight unavailable at %s: %s", self.settings.hindsight_base_url, e)
            self._available = False
        self._checked_at = now
        return self._available

    # ---- retain ----------------------------------------------------------

    def _resolution_document(self, *, ref: str, service: str, environment: str,
                             severity: str, started_at: str, alert_text: str,
                             symptoms: List[str], root_cause: str, action_taken: str,
                             outcome: str, lessons: List[str]) -> str:
        lines = [
            f"Incident {ref} on service {service} ({environment}, severity {severity}), started {started_at}.",
            f"Alert: {alert_text}",
            f"Symptoms: {'; '.join(symptoms) if symptoms else 'not recorded'}.",
            f"Root cause: {root_cause}",
            f"Resolution: {action_taken}",
            f"Outcome: {outcome}",
        ]
        for lesson in lessons:
            lines.append(f"Lesson learned: {lesson}")
        return "\n".join(lines)

    async def retain_incident_resolution(self, *, ref: str, service: str,
                                         environment: str, severity: str,
                                         started_at: datetime, alert_text: str,
                                         symptoms: List[str], root_cause: str,
                                         action_taken: str, outcome: str,
                                         lessons: List[str]) -> bool:
        """Store a resolved incident as organizational memory. Returns success."""
        if not self.enabled:
            return False
        if not await self.check_available():
            return False
        content = self._resolution_document(
            ref=ref, service=service, environment=environment, severity=severity,
            started_at=started_at.isoformat(), alert_text=alert_text,
            symptoms=symptoms, root_cause=root_cause, action_taken=action_taken,
            outcome=outcome, lessons=lessons,
        )
        try:
            await self.client.aretain(
                bank_id=self.bank_id,
                content=content,
                context=f"production incident resolution for {service}",
                timestamp=started_at.astimezone(timezone.utc),
                document_id=ref,
                metadata={"incident_ref": ref, "service": service, "environment": environment},
                retain_async=False,
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to retain %s to memory: %s", ref, e)
            return False

    async def seed_historical_incident(self, doc: str, *, ref: str, service: str,
                                       started_at: datetime) -> bool:
        """Bulk-seed one historical incident document (demo step 2)."""
        if not self.enabled or not await self.check_available():
            return False
        try:
            await self.client.aretain(
                bank_id=self.bank_id,
                content=doc,
                context=f"historical production incident on {service}",
                timestamp=started_at.astimezone(timezone.utc),
                document_id=ref,
                metadata={"incident_ref": ref, "service": service, "seed": "true"},
                retain_async=False,
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to seed %s into memory: %s", ref, e)
            return False

    # ---- recall / reflect ------------------------------------------------

    async def recall(self, query: str, *, max_tokens: int = 2500) -> MemoryContext:
        """Recall memories relevant to the current incident."""
        if not self.enabled or not await self.check_available():
            return MemoryContext()
        try:
            response = await self.client.arecall(
                bank_id=self.bank_id,
                query=query,
                budget="mid",
                max_tokens=max_tokens,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Recall failed: %s", e)
            return MemoryContext()

        hits: List[MemoryHit] = []
        refs: List[str] = []
        for r in (response.results or []):
            text = getattr(r, "text", "") or ""
            if not text:
                continue
            hits.append(MemoryHit(
                text=text,
                fact_type=getattr(r, "type", "world") or "world",
                score=getattr(r, "score", None),
            ))
            refs.extend(_INCIDENT_REF_RE.findall(text))

        seen: set = set()
        ctx = MemoryContext(hits=hits, incident_refs=[r for r in refs if not (r in seen or seen.add(r))])
        return ctx

    async def reflect(self, query: str) -> Optional[str]:
        """Ask Hindsight to reason over accumulated memory (organizational patterns)."""
        if not self.enabled or not await self.check_available():
            return None
        try:
            answer = await self.client.areflect(
                bank_id=self.bank_id,
                query=query,
                budget="low",
            )
            return answer.text
        except Exception as e:  # noqa: BLE001
            logger.error("Reflect failed: %s", e)
            return None

    async def stats(self) -> dict:
        """Entry counts for the dashboard memory panel."""
        base = {"enabled": self.enabled, "bank_id": self.bank_id, "available": False, "entries": None}
        if not self.enabled:
            return base
        if not await self.check_available():
            return base
        base["available"] = True
        try:
            memories = await asyncio.to_thread(
                self.client.list_memories, bank_id=self.bank_id, limit=1000
            )
            items = getattr(memories, "memories", None) or getattr(memories, "items", None) or []
            base["entries"] = len(items)
            breakdown: dict = {}
            for m in items:
                t = getattr(m, "type", None) or getattr(m, "fact_type", None) or "unknown"
                breakdown[t] = breakdown.get(t, 0) + 1
            base["breakdown"] = breakdown
        except Exception as e:  # noqa: BLE001
            logger.warning("list_memories failed: %s", e)
        return base


_memory_service: Optional[MemoryService] = None


def get_memory() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service
