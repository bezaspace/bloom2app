"""Runner bridge between the FastAPI plan design endpoints and the ADK Runner.

The plan design agent runs via ADK's ``Runner`` in text (non-live) mode. The
bridge:

1. ``start_session(patient_username, practitioner_id)`` — creates a new ADK
   Runner session, creates a draft if none exists, returns ``session_id``.
2. ``send_message(session_id, message, ...)`` — sends the practitioner's text
   to the Runner via ``runner.run_async()``, streams events back as a list of
   dicts (text + tool-call events).
3. ``get_history(session_id)`` — returns the conversation history for session
   restore.

The events are consumed by the web app's ``PlanDesignChat`` client component
and rendered as SSE.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import AsyncGenerator

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.plan_db import create_draft, get_unpublished_draft
from app.plan_design_agent.agent import plan_design_agent

logger = logging.getLogger("bloom2.plan_design_agent.runner")

APP_NAME = "bloom2_plan_designer"

# Shared session service + runner (lazily initialized).
_session_service = InMemorySessionService()
_runner: Runner | None = None


def _get_runner() -> Runner:
    global _runner
    if _runner is None:
        _runner = Runner(
            app_name=APP_NAME,
            agent=plan_design_agent,
            session_service=_session_service,
        )
    return _runner


# Track which session belongs to which patient/practitioner (for auth checks).
_session_meta: dict[str, dict] = {}


async def start_session(
    patient_username: str,
    practitioner_id: int,
    seed_from_active: bool = False,
) -> str:
    """Create a new ADK Runner session, create a draft if none exists, and
    return the session_id."""
    session_id = f"plan-design-{uuid.uuid4().hex[:12]}"
    await _session_service.create_session(
        app_name=APP_NAME,
        user_id=patient_username,
        session_id=session_id,
        state={
            "patient_username": patient_username,
            "practitioner_id": practitioner_id,
        },
    )
    _session_meta[session_id] = {
        "patient_username": patient_username,
        "practitioner_id": practitioner_id,
    }
    # Ensure a draft exists.
    draft = await get_unpublished_draft(patient_username)
    if not draft:
        await create_draft(patient_username, practitioner_id)
    return session_id


async def send_message(
    session_id: str,
    message: str,
    patient_username: str,
    practitioner_id: int,
) -> AsyncGenerator[dict, None]:
    """Send the practitioner's message to the plan design agent and yield
    events as dicts:
      {"type": "text", "content": "..."}
      {"type": "tool_call", "tool": "add_metric_to_draft", "args": {...}, "result": {...}}
    """
    meta = _session_meta.get(session_id)
    if not meta or meta["patient_username"] != patient_username:
        yield {"type": "error", "message": "Session not found or not authorized for this patient."}
        return
    runner = _get_runner()
    content = types.Content(
        role="user",
        parts=[types.Part(text=message)],
    )
    try:
        async for event in runner.run_async(
            user_id=patient_username,
            session_id=session_id,
            new_message=content,
        ):
            # Text response from the agent.
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        yield {"type": "text", "content": part.text}
                    if part.function_call:
                        yield {
                            "type": "tool_call",
                            "tool": part.function_call.name,
                            "args": dict(part.function_call.args or {}),
                        }
                    if part.function_response:
                        yield {
                            "type": "tool_result",
                            "tool": part.function_response.name,
                            "result": dict(part.function_response.response or {}),
                        }
            # If the event marks the final response, we're done.
            if event.is_final_response():
                break
    except Exception as e:  # noqa: BLE001
        logger.error("Plan design agent error: %s", e, exc_info=True)
        yield {"type": "error", "message": f"Agent error: {e}"}


async def get_history(session_id: str) -> list[dict]:
    """Return the conversation history for a design session (for re-loading
    the chat UI after a page refresh)."""
    meta = _session_meta.get(session_id)
    if not meta:
        return []
    session = await _session_service.get_session(
        app_name=APP_NAME,
        user_id=meta["patient_username"],
        session_id=session_id,
    )
    if not session:
        return []
    out = []
    for event in session.events:
        if not event.content or not event.content.parts:
            continue
        author = event.author or "agent"
        text_parts = [p.text for p in event.content.parts if p.text]
        if text_parts:
            out.append({
                "role": "user" if author == "user" else "agent",
                "text": " ".join(text_parts),
            })
    return out
