"""Onboarding tools for the Bloom healthcare voice agent.

These are ADK FunctionTools that the live agent calls during the voice
conversation. ADK's ``run_live()`` executes them automatically when the model
emits a function-call. They read/write the per-user onboarding profile, plan,
and document summary in the SQLite store (durable across sessions/restarts).

The username is injected into the session state as ``"username"`` by the
WebSocket handler in ``main.py`` at session creation time, so the tools can
read it via ``tool_context.state.get("username")``.
"""

import json
import logging

from google.adk.tools import ToolContext

from app.database import get_profile, save_profile

logger = logging.getLogger("bloom2.tools")


async def get_user_profile(tool_context: ToolContext) -> dict:
    """Returns the current user's onboarding status, profile, plan, and document summary.

    Call this at the start of a session to decide whether to run onboarding.
    If ``onboarded`` is false or ``profile`` is null, the user needs onboarding.
    If ``onboarded`` is true, ``profile`` and ``plan`` contain the stored data.

    Returns:
        dict with keys: onboarded (bool), profile (dict|null), plan (dict|null),
        doc_summary (dict|null).
    """
    username = tool_context.state.get("username")
    if not username:
        return {"onboarded": False, "profile": None, "plan": None, "doc_summary": None}

    profile_data = await get_profile(username)
    if not profile_data:
        return {"onboarded": False, "profile": None, "plan": None, "doc_summary": None}
    return profile_data


async def get_document_summary(tool_context: ToolContext) -> dict:
    """Returns the structured summary extracted from the user's uploaded health documents.

    Call this after the user confirms they have uploaded documents (or says they
    want to skip) to incorporate medical context into the 90-day plan. If no
    documents have been uploaded, returns ``{"available": false}``.

    Returns:
        dict with keys: available (bool), summary (dict|null).
    """
    username = tool_context.state.get("username")
    if not username:
        return {"available": False, "summary": None}

    profile_data = await get_profile(username)
    if not profile_data or not profile_data.get("doc_summary"):
        return {"available": False, "summary": None}
    return {"available": True, "summary": profile_data["doc_summary"]}


async def finalize_onboarding(
    profile_json: str,
    plan_json: str,
    tool_context: ToolContext,
) -> dict:
    """Saves the user's onboarding profile and 90-day plan, marking onboarding complete.

    Call this once you have asked all onboarding questions (max 5) and checked
    for any uploaded documents via get_document_summary. The profile and plan
    should be JSON strings. The plan should cover a 90-day period.

    Args:
        profile_json: A JSON string of the user's profile (goal, activity level,
            sleep/stress, conditions/medications, diet/constraints).
        plan_json: A JSON string of the 90-day wellness plan.

    Returns:
        dict with keys: status ("success"|"error"), message (str).
    """
    username = tool_context.state.get("username")
    if not username:
        return {"status": "error", "message": "No authenticated user in session."}

    # Validate that the inputs are valid JSON before storing.
    try:
        json.loads(profile_json)
        json.loads(plan_json)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}

    # Preserve any existing doc_summary when finalizing.
    existing = await get_profile(username)
    doc_summary_json = (
        json.dumps(existing["doc_summary"]) if existing and existing.get("doc_summary") else None
    )

    await save_profile(
        username=username,
        profile_json=profile_json,
        plan_json=plan_json,
        doc_summary_json=doc_summary_json,
        onboarded=True,
    )
    logger.info("Onboarding finalized for user %s", username)
    return {
        "status": "success",
        "message": "Profile and 90-day plan saved successfully.",
    }
