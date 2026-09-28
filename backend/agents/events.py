"""Agent event emitter — bridges the investigation loop to an SSE stream."""
import asyncio
import json
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AgentEvent:
    kind: str  # status | step | memory | recommendation | error | done
    message: str
    data: Optional[dict] = None


class EventEmitter:
    """Collects agent events; an SSE generator drains them live."""

    def __init__(self) -> None:
        self.events: List[AgentEvent] = []
        self._queue: "asyncio.Queue[AgentEvent]" = asyncio.Queue()
        self.closed = False

    def emit(self, kind: str, message: str, data: Optional[dict] = None) -> None:
        ev = AgentEvent(kind=kind, message=message, data=data)
        self.events.append(ev)
        if not self.closed:
            self._queue.put_nowait(ev)

    async def stream(self):
        while True:
            ev = await self._queue.get()
            yield ev
            if ev.kind == "done":
                break

    def close(self) -> None:
        self.closed = True
