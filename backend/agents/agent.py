"""The IncidentMind investigation agent.

A plain function-calling loop against an OpenAI-compatible LLM (Groq default):
no framework, every step observable, every tool call persisted to the
incident timeline. Memory (Hindsight recall/reflect) is just another tool —
which is exactly what makes the A/B demo possible.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models import Incident, IncidentEvent
from ..memory.client import MemoryService
from ..schemas import Recommendation
from .events import EventEmitter
from .llm import LLMNotConfiguredError, get_llm_client, model_name
from .prompts import MEMORY_OFF_NOTE, MEMORY_ON_NOTE, SYSTEM_PROMPT
from .tools import ToolRegistry, _next_seq

logger = logging.getLogger("incidentmind.agent")

MAX_ITERATIONS = 14


class AgentResult:
    def __init__(self) -> None:
        self.recommendation: Optional[Recommendation] = None
        self.steps: int = 0  # tool calls made by the agent
        self.used_memory: bool = False
        self.raw_text: str = ""


def _persist_event(db: Session, incident_id: int, kind: str, tool_name: Optional[str],
                   summary: str, detail: str = "") -> None:
    db.add(IncidentEvent(
        incident_id=incident_id,
        seq=_next_seq(db, incident_id),
        kind=kind,
        tool_name=tool_name,
        summary=summary[:500],
        detail=detail or None,
    ))
    db.commit()


def _summarize_tool_result(name: str, result: Dict[str, Any]) -> str:
    """One human-readable line per tool call, for the timeline."""
    if name == "search_memory":
        n = result.get("num_similar", 0)
        refs = result.get("matched_refs", [])
        return f"Memory recall: {n} similar incident(s) found" + (f" — {', '.join(refs)}" if refs else "")
    if name == "search_logs":
        return f"Log search ({result.get('count', 0)} matching lines)"
    if name == "compare_with_history":
        return f"Compared with {result.get('ref', 'history')}: {result.get('title', '')}"
    if name == "reflect_patterns":
        return "Reflected on organizational patterns from memory"
    if name == "get_runbook":
        return f"Runbook: {result.get('title', result.get('error', 'none'))}"
    if name == "record_step":
        return f"Recorded: {result.get('recorded', '')}"
    return f"Called {name}"


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull the final JSON recommendation out of the model's last message."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    # Fall back to the first {...} block.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(stripped[start:end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return None
    return None


async def run_investigation(
    db: Session,
    incident: Incident,
    memory: MemoryService,
    emitter: EventEmitter,
) -> AgentResult:
    """Investigate one incident end-to-end, streaming events as it goes."""
    result = AgentResult()
    registry = ToolRegistry(db, memory, incident)
    memory_on = memory.enabled

    try:
        client = get_llm_client()
    except LLMNotConfiguredError as e:
        emitter.emit("error", str(e))
        emitter.emit("done", "Investigation aborted: LLM not configured")
        return result

    system = SYSTEM_PROMPT.format(
        memory_mode="ON — organizational memory available" if memory_on
        else "OFF — no memory for this run (A/B comparison)",
        memory_note=MEMORY_ON_NOTE if memory_on else MEMORY_OFF_NOTE,
    )
    user_msg = (
        f"Investigate incident {incident.ref}.\n"
        f"Service: {incident.service_name}\n"
        f"Severity: {incident.severity}\n"
        f"Alert: {incident.alert_text}\n"
        f"Reported symptoms: {', '.join(incident.symptoms_list) or 'none recorded'}\n"
        "Follow the investigation protocol. Produce the final JSON recommendation."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_msg},
    ]

    emitter.emit("status", f"Investigating {incident.ref} — memory {'ON' if memory_on else 'OFF'}")

    try:
        for _ in range(MAX_ITERATIONS):
            response = await client.chat.completions.create(
                model=model_name(),
                messages=messages,
                tools=registry.schemas(),
                temperature=0.2,
            )
            choice = response.choices[0]
            message = choice.message
            tool_calls = list(getattr(message, "tool_calls", None) or [])

            if not tool_calls:
                # Final answer expected.
                obj = _extract_json(message.content or "")
                if obj is not None:
                    result.recommendation = Recommendation(
                        summary=str(obj.get("summary", "")),
                        likely_root_causes=list(obj.get("likely_root_causes") or []),
                        historical_match=obj.get("historical_match"),
                        applies_to_current_evidence=obj.get("applies_to_current_evidence"),
                        investigation_steps=[str(s) for s in (obj.get("investigation_steps") or [])],
                        proposed_actions=[str(s) for s in (obj.get("proposed_actions") or [])],
                        confidence=str(obj.get("confidence", "medium")),
                    )
                    _persist_event(
                        db, incident.id, "recommendation", "final_recommendation",
                        result.recommendation.summary,
                        result.recommendation.model_dump_json(),
                    )
                    emitter.emit("recommendation", "Recommendation ready",
                                 data=result.recommendation.model_dump())
                else:
                    result.raw_text = message.content or ""
                    _persist_event(db, incident.id, "note", "agent",
                                   result.raw_text[:500], result.raw_text)
                    emitter.emit("status", "Agent produced a non-JSON answer",
                                 data={"text": result.raw_text})
                break

            # Execute tool calls in order, persist each as a timeline event.
            messages.append({
                "role": "assistant",
                "content": message.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                name = tc.function.name
                args_str = tc.function.arguments or "{}"
                result.steps += 1
                tool_result = registry.execute(name, args_str)

                detail = json.dumps({"tool": name, "arguments": args_str, "result": tool_result})[:4000]
                _persist_event(db, incident.id, "tool_call", name,
                               _summarize_tool_result(name, tool_result), detail)

                if name == "search_memory":
                    if tool_result.get("memory") != "disabled":
                        result.used_memory = True
                    n = tool_result.get("num_similar", 0)
                    refs = tool_result.get("matched_refs", [])
                    emitter.emit("memory",
                                 f"Memory recall: {n} similar incident(s)" +
                                 (f" — {', '.join(refs)}" if refs else ""),
                                 data=tool_result)
                emitter.emit("step", _summarize_tool_result(name, tool_result),
                             data={"tool": name, "seq": len(emitter.events)})

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result)[:4000],
                })
        else:
            emitter.emit("status", "Reached iteration limit before a final answer")
    except Exception as e:  # noqa: BLE001
        logger.exception("Investigation failed for %s", incident.ref)
        emitter.emit("error", f"Agent error: {e}")

    emitter.emit("done", f"Investigation finished — {result.steps} tool step(s)")
    return result
