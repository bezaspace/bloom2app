"""Tools for the Plan Designer ADK agent.

Two groups:

1. **Read tools** (no side effects) — read the patient's profile, biomarkers,
   doc summary, current plan, current draft, metric templates, and adherence
   summary.
2. **Write tools** (modify the draft in the DB) — add/remove metrics, set
   targets, add/remove outcomes, add/update phases, set title/rationale,
   validate the draft.

The patient_username and practitioner_id are injected into the session state
by the runner bridge (``runner.py``) at session creation time, so the tools
can read them via ``tool_context.state.get("patient_username")`` and
``tool_context.state.get("practitioner_id")``.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from google.adk.tools import ToolContext

from app.database import get_profile, list_biomarkers
from app.metric_templates import template_exists, get_template, templates_as_dicts
from app.plan_db import (
    create_draft,
    get_active_plan,
    get_unpublished_draft,
    update_draft,
)
from app.plan_analytics import compute_adherence_summary

logger = logging.getLogger("bloom2.plan_design_agent.tools")


def _get_state(tool_context: ToolContext) -> tuple[str, int]:
    """Return (patient_username, practitioner_id) from session state."""
    username = tool_context.state.get("patient_username")
    practitioner_id = tool_context.state.get("practitioner_id")
    if not username or practitioner_id is None:
        raise ValueError("patient_username and practitioner_id must be set in session state")
    return username, int(practitioner_id)


def _ensure_draft(username: str, practitioner_id: int) -> dict:
    """Get the current unpublished draft, or create an empty one if none."""
    draft = _get_unpublished_draft_sync(username)
    if draft:
        return draft
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        create_draft(username, practitioner_id)
    ) if False else _create_draft_sync(username, practitioner_id)


def _get_unpublished_draft_sync(username: str) -> dict | None:
    """Synchronous draft fetch (the async wrapper is in plan_db)."""
    from app.plan_db import _get_unpublished_draft_sync as _g
    return _g(username)


def _create_draft_sync(username: str, practitioner_id: int) -> dict:
    """Synchronous draft creation."""
    from app.plan_db import _create_draft_sync as _c
    return _c(username, practitioner_id)


def _update_draft_sync(username: str, **kwargs) -> dict | None:
    """Synchronous draft update."""
    from app.plan_db import _update_draft_sync as _u
    return _u(username, **kwargs)


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------
async def get_patient_profile(tool_context: ToolContext) -> dict:
    """Returns the patient's onboarding profile (age, conditions, goals, etc.).

    Returns:
        dict with: available (bool), profile (dict|null).
    """
    username, _ = _get_state(tool_context)
    profile_data = await get_profile(username)
    if not profile_data or not profile_data.get("profile"):
        return {"available": False, "profile": None}
    return {"available": True, "profile": profile_data["profile"]}


async def get_patient_biomarkers(tool_context: ToolContext) -> dict:
    """Returns the patient's latest biomarker readings + history (for setting
    outcome targets).

    Returns:
        dict with: available (bool), biomarkers (list).
    """
    username, _ = _get_state(tool_context)
    rows = await list_biomarkers(username)
    if not rows:
        return {"available": False, "biomarkers": []}
    return {"available": True, "biomarkers": rows}


async def get_patient_doc_summary(tool_context: ToolContext) -> dict:
    """Returns the extracted conditions, medications, allergies from the
    patient's uploaded health docs.

    Returns:
        dict with: available (bool), summary (dict|null).
    """
    username, _ = _get_state(tool_context)
    profile_data = await get_profile(username)
    if not profile_data or not profile_data.get("doc_summary"):
        return {"available": False, "summary": None}
    return {"available": True, "summary": profile_data["doc_summary"]}


async def get_current_plan(tool_context: ToolContext) -> dict:
    """Returns the current active plan (if any) — metrics, outcomes, phases.

    Returns:
        dict with: available (bool), plan (dict|null).
    """
    username, _ = _get_state(tool_context)
    plan = await get_active_plan(username)
    if not plan:
        return {"available": False, "plan": None}
    return {"available": True, "plan": plan}


async def get_draft(tool_context: ToolContext) -> dict:
    """Returns the current unpublished draft (outcomes, metrics, phases as JSON).

    Returns:
        dict with: available (bool), draft (dict|null).
    """
    username, practitioner_id = _get_state(tool_context)
    draft = await get_unpublished_draft(username)
    if not draft:
        return {"available": False, "draft": None}
    return {"available": True, "draft": draft}


async def get_metric_templates(tool_context: ToolContext) -> dict:
    """Returns all available metric templates (key, label, unit, target type,
    description). Use this to pick metrics when building the plan.

    Returns:
        dict with: templates (list).
    """
    return {"templates": templates_as_dicts()}


async def get_adherence_summary(tool_context: ToolContext, days: int = 7) -> dict:
    """Returns per-metric adherence % for the last N days (for edit-existing
    scenarios — to understand what's working and what isn't).

    Args:
        days: Number of days to average over (default 7).

    Returns:
        dict with: days, metrics (list), overall (float|null).
    """
    username, _ = _get_state(tool_context)
    return await compute_adherence_summary(username, days)


# ---------------------------------------------------------------------------
# Write tools (modify the draft in the DB)
# ---------------------------------------------------------------------------
async def add_metric_to_draft(
    template_id: str,
    target_value: float | None = None,
    target_high: float | None = None,
    frequency: str | None = None,
    time_of_day: str | None = None,
    phase: int | None = None,
    label: str | None = None,
    ai_reasoning: str | None = None,
    tool_context: ToolContext = None,
) -> dict:
    """Appends a metric to the draft's metrics list. Validates template_id exists.

    Args:
        template_id: The template key (e.g., "fasting_glucose", "steps"). Must
            be one returned by get_metric_templates.
        target_value: The target value for this metric. If None, uses the
            template's default_target.
        target_high: Upper bound when target_type is "range". If None, uses
            the template's default_target_high.
        frequency: One of the template's frequency_options. If None, uses the
            first option.
        time_of_day: "morning" | "afternoon" | "evening" | "night" | None.
        phase: Which plan phase (1, 2, 3) this metric is emphasized in. None = all.
        label: Override the display label. If None, uses the template's label.
        ai_reasoning: Optional reasoning for why this metric was added (shown
            to the practitioner).

    Returns:
        dict with: status, draft (the updated draft), added_metric.
    """
    username, practitioner_id = _get_state(tool_context)
    if not template_exists(template_id):
        return {"status": "error", "message": f"Unknown template_id: {template_id}"}
    t = get_template(template_id)
    draft = await get_unpublished_draft(username)
    if not draft:
        draft = await create_draft(username, practitioner_id)
    metrics = list(draft.get("metrics_json") or [])
    temp_id = f"m{len(metrics) + 1}_{uuid.uuid4().hex[:4]}"
    metric = {
        "temp_id": temp_id,
        "template_id": template_id,
        "label": label or t.label,
        "unit": t.unit,
        "frequency": frequency or t.frequency_options[0],
        "time_of_day": time_of_day,
        "target_type": t.target_type,
        "target_value": target_value if target_value is not None else t.default_target,
        "target_high": target_high if target_high is not None else t.default_target_high,
        "is_active": True,
        "phase": phase,
        "sort_order": len(metrics),
        "ai_reasoning": ai_reasoning,
    }
    metrics.append(metric)
    updated = await update_draft(username, metrics=metrics)
    return {"status": "success", "draft": updated, "added_metric": metric}


async def remove_metric_from_draft(
    temp_id: str,
    tool_context: ToolContext = None,
) -> dict:
    """Removes a metric from the draft by its temp_id.

    Args:
        temp_id: The temp_id of the metric to remove (from get_draft).

    Returns:
        dict with: status, draft (the updated draft).
    """
    username, _ = _get_state(tool_context)
    draft = await get_unpublished_draft(username)
    if not draft:
        return {"status": "error", "message": "No draft found."}
    metrics = list(draft.get("metrics_json") or [])
    new_metrics = [m for m in metrics if m.get("temp_id") != temp_id]
    if len(new_metrics) == len(metrics):
        return {"status": "error", "message": f"No metric with temp_id {temp_id}."}
    updated = await update_draft(username, metrics=new_metrics)
    return {"status": "success", "draft": updated}


async def set_metric_target(
    temp_id: str,
    target_value: float | None = None,
    target_high: float | None = None,
    tool_context: ToolContext = None,
) -> dict:
    """Updates a metric's target in the draft.

    Args:
        temp_id: The temp_id of the metric to update.
        target_value: The new target value (or None to leave unchanged).
        target_high: The new upper bound (or None to leave unchanged).

    Returns:
        dict with: status, draft (the updated draft).
    """
    username, _ = _get_state(tool_context)
    draft = await get_unpublished_draft(username)
    if not draft:
        return {"status": "error", "message": "No draft found."}
    metrics = list(draft.get("metrics_json") or [])
    found = False
    for m in metrics:
        if m.get("temp_id") == temp_id:
            if target_value is not None:
                m["target_value"] = target_value
            if target_high is not None:
                m["target_high"] = target_high
            found = True
            break
    if not found:
        return {"status": "error", "message": f"No metric with temp_id {temp_id}."}
    updated = await update_draft(username, metrics=metrics)
    return {"status": "success", "draft": updated}


async def add_outcome_to_draft(
    biomarker_name: str,
    target_value: float,
    target_direction: str,
    target_high: float | None = None,
    unit: str = "",
    target_date: str | None = None,
    tool_context: ToolContext = None,
) -> dict:
    """Appends an outcome target to the draft's outcomes list. Auto-fills
    current_value from the biomarkers table if a matching reading exists.

    Args:
        biomarker_name: e.g., "HbA1c", "LDL Cholesterol".
        target_value: The target value (e.g., 6.0 for HbA1c).
        target_direction: "below" | "above" | "range".
        target_high: Upper bound when direction = "range".
        unit: e.g., "%", "mg/dL".
        target_date: ISO date by which to achieve it (e.g., "2026-10-02").

    Returns:
        dict with: status, draft (the updated draft), added_outcome.
    """
    username, practitioner_id = _get_state(tool_context)
    draft = await get_unpublished_draft(username)
    if not draft:
        draft = await create_draft(username, practitioner_id)
    outcomes = list(draft.get("outcomes_json") or [])
    # Auto-fill current_value from biomarkers.
    current_value = None
    current_as_of = None
    rows = await list_biomarkers(username)
    matching = [r for r in rows if r["name"].lower() == biomarker_name.lower()]
    if matching:
        latest = matching[0]
        current_value = latest["value"]
        current_as_of = latest.get("measured_at")
        if not unit:
            unit = latest["unit"]
    outcome = {
        "biomarker_name": biomarker_name,
        "target_value": target_value,
        "target_direction": target_direction,
        "target_high": target_high,
        "unit": unit,
        "target_date": target_date,
        "current_value": current_value,
        "current_as_of": current_as_of,
    }
    outcomes.append(outcome)
    updated = await update_draft(username, outcomes=outcomes)
    return {"status": "success", "draft": updated, "added_outcome": outcome}


async def remove_outcome_from_draft(
    index: int,
    tool_context: ToolContext = None,
) -> dict:
    """Removes an outcome from the draft by its index (0-based).

    Args:
        index: The 0-based index of the outcome to remove.

    Returns:
        dict with: status, draft (the updated draft).
    """
    username, _ = _get_state(tool_context)
    draft = await get_unpublished_draft(username)
    if not draft:
        return {"status": "error", "message": "No draft found."}
    outcomes = list(draft.get("outcomes_json") or [])
    if index < 0 or index >= len(outcomes):
        return {"status": "error", "message": f"Index {index} out of range (have {len(outcomes)} outcomes)."}
    outcomes.pop(index)
    updated = await update_draft(username, outcomes=outcomes)
    return {"status": "success", "draft": updated}


async def add_phase_to_draft(
    name: str,
    focus: str,
    actions: list[str] | None = None,
    day_start: int = 1,
    day_end: int = 30,
    tool_context: ToolContext = None,
) -> dict:
    """Appends a phase to the draft's phases list.

    Args:
        name: e.g., "Phase 1: Days 1-30".
        focus: What to focus on in this phase.
        actions: List of action strings.
        day_start: First day of the phase (e.g., 1).
        day_end: Last day of the phase (e.g., 30).

    Returns:
        dict with: status, draft (the updated draft), added_phase.
    """
    username, practitioner_id = _get_state(tool_context)
    draft = await get_unpublished_draft(username)
    if not draft:
        draft = await create_draft(username, practitioner_id)
    phases = list(draft.get("phases_json") or [])
    phase_number = len(phases) + 1
    phase = {
        "phase_number": phase_number,
        "name": name,
        "focus": focus,
        "actions": actions or [],
        "day_start": day_start,
        "day_end": day_end,
    }
    phases.append(phase)
    updated = await update_draft(username, phases=phases)
    return {"status": "success", "draft": updated, "added_phase": phase}


async def update_phase(
    phase_number: int,
    name: str | None = None,
    focus: str | None = None,
    actions: list[str] | None = None,
    day_start: int | None = None,
    day_end: int | None = None,
    tool_context: ToolContext = None,
) -> dict:
    """Updates an existing phase in the draft.

    Args:
        phase_number: The 1-based phase number to update.
        name, focus, actions, day_start, day_end: New values (None = unchanged).

    Returns:
        dict with: status, draft (the updated draft).
    """
    username, _ = _get_state(tool_context)
    draft = await get_unpublished_draft(username)
    if not draft:
        return {"status": "error", "message": "No draft found."}
    phases = list(draft.get("phases_json") or [])
    found = False
    for p in phases:
        if p.get("phase_number") == phase_number:
            if name is not None:
                p["name"] = name
            if focus is not None:
                p["focus"] = focus
            if actions is not None:
                p["actions"] = actions
            if day_start is not None:
                p["day_start"] = day_start
            if day_end is not None:
                p["day_end"] = day_end
            found = True
            break
    if not found:
        return {"status": "error", "message": f"No phase {phase_number}."}
    updated = await update_draft(username, phases=phases)
    return {"status": "success", "draft": updated}


async def set_draft_title(
    title: str,
    tool_context: ToolContext = None,
) -> dict:
    """Sets the draft's title.

    Args:
        title: The plan title (e.g., "Prediabetes reversal — 90 days").

    Returns:
        dict with: status, draft (the updated draft).
    """
    username, _ = _get_state(tool_context)
    updated = await update_draft(username, title=title)
    if not updated:
        return {"status": "error", "message": "No draft found."}
    return {"status": "success", "draft": updated}


async def set_draft_rationale(
    rationale: str,
    tool_context: ToolContext = None,
) -> dict:
    """Sets the draft's rationale text (visible to patient + AI).

    Args:
        rationale: Free-text explaining the plan's reasoning.

    Returns:
        dict with: status, draft (the updated draft).
    """
    username, _ = _get_state(tool_context)
    updated = await update_draft(username, rationale=rationale)
    if not updated:
        return {"status": "error", "message": "No draft found."}
    return {"status": "success", "draft": updated}


async def validate_draft(tool_context: ToolContext) -> dict:
    """Returns warnings/errors about the current draft (e.g., "7 daily metrics
    — at soft cap", "no outcome targets set", "phase 2 has no metrics assigned").
    Does not block; just reports.

    Returns:
        dict with: valid (bool), warnings (list[str]), errors (list[str]),
        summary (str).
    """
    username, _ = _get_state(tool_context)
    draft = await get_unpublished_draft(username)
    if not draft:
        return {"valid": False, "warnings": [], "errors": ["No draft found."], "summary": "No draft."}
    metrics = draft.get("metrics_json") or []
    outcomes = draft.get("outcomes_json") or []
    phases = draft.get("phases_json") or []
    warnings: list[str] = []
    errors: list[str] = []
    daily_count = sum(1 for m in metrics if m.get("frequency") == "daily")
    if daily_count > 7:
        warnings.append(f"{daily_count} daily metrics — exceeds the soft cap of 7. The plan may be too demanding.")
    if not metrics:
        errors.append("No tracked metrics defined.")
    if not outcomes:
        warnings.append("No outcome targets set — the plan has no biomarker goals.")
    if not phases:
        warnings.append("No phases defined — consider adding 1-3 phases to structure the plan.")
    else:
        for p in phases:
            pn = p.get("phase_number")
            assigned = [m for m in metrics if m.get("phase") == pn]
            if not assigned and len(phases) > 1:
                warnings.append(f"Phase {pn} has no metrics explicitly assigned to it.")
    valid = len(errors) == 0
    bits = []
    if errors:
        bits.append(f"{len(errors)} error(s)")
    if warnings:
        bits.append(f"{len(warnings)} warning(s)")
    summary = f"Draft has {len(metrics)} metrics, {len(outcomes)} outcomes, {len(phases)} phases. " + (", ".join(bits) if bits else "looks good.")
    return {"valid": valid, "warnings": warnings, "errors": errors, "summary": summary, "draft": draft}
