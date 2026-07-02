"""Practitioner- and patient-facing API routes for tracking plans.

Plan management (practitioner-facing, requires connection to patient):
  GET  /practitioner/patients/{username}/plan
  GET  /metric-templates

Plan draft management (practitioner-facing):
  GET    /practitioner/patients/{username}/plan/draft
  POST   /practitioner/patients/{username}/plan/draft
  PUT    /practitioner/patients/{username}/plan/draft
  POST   /practitioner/patients/{username}/plan/draft/publish
  DELETE /practitioner/patients/{username}/plan/draft

Plan design agent (practitioner-facing, SSE):
  POST /practitioner/patients/{username}/plan/design/start
  POST /practitioner/patients/{username}/plan/design/send
  GET  /practitioner/patients/{username}/plan/design/history

Patient-facing plan + logging:
  GET  /plan
  POST /logs
  GET  /logs/today
  GET  /logs/recent

Analytics + insights (both patient and practitioner):
  GET  /analytics/adherence
  GET  /analytics/trends
  GET  /analytics/correlations
  GET  /analytics/biomarker-progress
  GET  /insights/weekly-report
  GET  /insights/trend-alerts
  POST /insights/plan-suggestion
  GET  /practitioner/patients/{username}/plan/suggestions
  POST /practitioner/patients/{username}/plan/suggestions/{id}/decide
"""

from __future__ import annotations

import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.metric_templates import templates_as_dicts, template_exists, get_template
from app.plan_analytics import (
    compute_adherence_for_date,
    compute_adherence_summary,
    compute_biomarker_progress,
    compute_correlations,
    compute_trends,
)
from app.plan_db import (
    add_plan_suggestion,
    create_draft,
    delete_draft,
    get_active_plan,
    get_metric,
    get_unpublished_draft,
    list_plan_suggestions,
    publish_draft,
    save_metric_log,
    set_suggestion_status,
    update_draft,
)
from app.practitioner_auth import get_current_practitioner_id, get_current_practitioner_token
from app.practitioner_db import has_connection


router = APIRouter(tags=["plans"])


def _today_iso() -> str:
    return date.today().isoformat()


async def _require_connection(practitioner_id: int, patient_username: str) -> None:
    if not await has_connection(practitioner_id, patient_username):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active connection to this patient.",
        )


# ---------------------------------------------------------------------------
# Metric templates
# ---------------------------------------------------------------------------
@router.get("/metric-templates")
async def list_metric_templates() -> dict:
    """List all available metric templates (for the plan builder UI)."""
    return {"status": "success", "templates": templates_as_dicts()}


# ---------------------------------------------------------------------------
# Plan management (practitioner-facing)
# ---------------------------------------------------------------------------
@router.get("/practitioner/patients/{username}/plan")
async def get_patient_plan(
    username: str,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Get the patient's active plan (metrics, outcomes, phases)."""
    await _require_connection(practitioner_id, username)
    plan = await get_active_plan(username)
    if not plan:
        return {"status": "success", "plan": None}
    return {"status": "success", "plan": plan}


# ---------------------------------------------------------------------------
# Plan draft management (practitioner-facing)
# ---------------------------------------------------------------------------
class CreateDraftRequest(BaseModel):
    title: str | None = None
    rationale: str | None = None
    seed_from_active: bool = False


class UpdateDraftRequest(BaseModel):
    title: str | None = None
    rationale: str | None = None
    outcomes: list[dict] | None = None
    metrics: list[dict] | None = None
    phases: list[dict] | None = None


@router.get("/practitioner/patients/{username}/plan/draft")
async def get_draft(
    username: str,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Get the current unpublished draft (or null if none)."""
    await _require_connection(practitioner_id, username)
    draft = await get_unpublished_draft(username)
    return {"status": "success", "draft": draft}


@router.post("/practitioner/patients/{username}/plan/draft")
async def create_draft_endpoint(
    username: str,
    body: CreateDraftRequest,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Create a new draft. If an unpublished draft already exists, it's
    replaced. Optionally seed from the current active plan."""
    await _require_connection(practitioner_id, username)
    outcomes: list[dict] = []
    metrics: list[dict] = []
    phases: list[dict] = []
    title = body.title
    rationale = body.rationale
    if body.seed_from_active:
        active = await get_active_plan(username)
        if active:
            title = title or active.get("title")
            rationale = rationale or active.get("rationale")
            outcomes = [
                {
                    "biomarker_name": o["biomarker_name"],
                    "target_value": o["target_value"],
                    "target_direction": o["target_direction"],
                    "target_high": o.get("target_high"),
                    "unit": o["unit"],
                    "target_date": o.get("target_date"),
                    "current_value": o.get("current_value"),
                    "current_as_of": o.get("current_as_of"),
                }
                for o in active["outcomes"]
            ]
            metrics = [
                {
                    "temp_id": f"m{i+1}",
                    "template_id": m["template_id"],
                    "label": m["label"],
                    "unit": m["unit"],
                    "frequency": m["frequency"],
                    "time_of_day": m.get("time_of_day"),
                    "target_type": m["target_type"],
                    "target_value": m.get("target_value"),
                    "target_high": m.get("target_high"),
                    "is_active": m.get("is_active", True),
                    "phase": m.get("phase"),
                    "sort_order": m.get("sort_order", i),
                }
                for i, m in enumerate(active["metrics"])
            ]
            phases = [
                {
                    "phase_number": p["phase_number"],
                    "name": p["name"],
                    "focus": p.get("focus", ""),
                    "actions": p.get("actions", []),
                    "day_start": p["day_start"],
                    "day_end": p["day_end"],
                }
                for p in active["phases"]
            ]
    draft = await create_draft(
        username, practitioner_id, title, rationale, outcomes, metrics, phases
    )
    return {"status": "success", "draft": draft}


@router.put("/practitioner/patients/{username}/plan/draft")
async def update_draft_endpoint(
    username: str,
    body: UpdateDraftRequest,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Update the draft's fields (used by the manual mode form on every save)."""
    await _require_connection(practitioner_id, username)
    draft = await update_draft(
        username,
        title=body.title,
        rationale=body.rationale,
        outcomes=body.outcomes,
        metrics=body.metrics,
        phases=body.phases,
    )
    if not draft:
        raise HTTPException(status_code=404, detail="No unpublished draft found.")
    return {"status": "success", "draft": draft}


@router.post("/practitioner/patients/{username}/plan/draft/publish")
async def publish_draft_endpoint(
    username: str,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Publish the draft: creates a new active plan (new version) from the
    draft's JSON, marks the draft as published, archives the previous active
    plan."""
    await _require_connection(practitioner_id, username)
    plan = await publish_draft(username)
    if not plan:
        raise HTTPException(status_code=404, detail="No unpublished draft found.")
    return {"status": "success", "plan": plan}


@router.delete("/practitioner/patients/{username}/plan/draft")
async def discard_draft_endpoint(
    username: str,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Discard the draft without publishing."""
    await _require_connection(practitioner_id, username)
    deleted = await delete_draft(username)
    return {"status": "success" if deleted else "noop", "deleted": deleted}


# ---------------------------------------------------------------------------
# Plan design agent (practitioner-facing, SSE)
# ---------------------------------------------------------------------------
class DesignStartRequest(BaseModel):
    seed_from_active: bool = False


class DesignSendRequest(BaseModel):
    session_id: str
    message: str


@router.post("/practitioner/patients/{username}/plan/design/start")
async def plan_design_start(
    username: str,
    body: DesignStartRequest | None = None,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Start a new plan design conversation. Creates a draft if none exists.
    Returns a session_id for the ADK Runner session."""
    await _require_connection(practitioner_id, username)
    from app.plan_design_agent.runner import start_session
    seed = body.seed_from_active if body else False
    session_id = await start_session(username, practitioner_id, seed_from_active=seed)
    return {"status": "success", "session_id": session_id}


@router.post("/practitioner/patients/{username}/plan/design/send")
async def plan_design_send(
    username: str,
    body: DesignSendRequest,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> StreamingResponse:
    """Send a practitioner message to the plan design agent. Returns an SSE
    stream of agent responses (text + tool-call events)."""
    await _require_connection(practitioner_id, username)
    from app.plan_design_agent.runner import send_message

    async def event_stream():
        async for event in send_message(body.session_id, body.message, username, practitioner_id):
            yield f"data: {json.dumps(event)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/practitioner/patients/{username}/plan/design/history")
async def plan_design_history(
    username: str,
    session_id: str = Query(...),
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Get the conversation history for a design session."""
    await _require_connection(practitioner_id, username)
    from app.plan_design_agent.runner import get_history
    history = await get_history(session_id)
    return {"status": "success", "history": history}


# ---------------------------------------------------------------------------
# Patient-facing plan view
# ---------------------------------------------------------------------------
@router.get("/plan")
async def get_my_plan(user: str = Depends(get_current_user)) -> dict:
    """Get the current user's active plan (metrics, outcomes, phases,
    practitioner rationale)."""
    plan = await get_active_plan(user)
    if not plan:
        return {"status": "success", "plan": None}
    return {"status": "success", "plan": plan}


# ---------------------------------------------------------------------------
# Logging (patient-facing, replaces /dashboard/log)
# ---------------------------------------------------------------------------
class LogMetricRequest(BaseModel):
    metric_id: int
    value: float | None = None
    date: str = Field(default_factory=_today_iso)
    note: str | None = None
    completed: bool = True
    key: str | None = None


@router.post("/logs")
async def log_metric(
    body: LogMetricRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Log a metric value. Appends an entry to the metric's log for the date."""
    metric = await get_metric(body.metric_id)
    if not metric:
        return {"status": "error", "message": f"Metric {body.metric_id} not found."}
    # Read existing entries so we append rather than wipe.
    from app.plan_db import get_metric_logs
    all_logs = await get_metric_logs(user, body.date)
    existing = list(all_logs.get(body.metric_id, []))
    import time
    entry = {
        "key": body.key or f"log_{int(time.time() * 1000)}",
        "completed": body.completed,
        "value": body.value,
        "note": body.note,
    }
    existing.append(entry)
    await save_metric_log(user, body.date, body.metric_id, json.dumps(existing))
    return {"status": "success"}


@router.get("/logs/today")
async def logs_today(user: str = Depends(get_current_user)) -> dict:
    """Get today's logs for all active metrics."""
    from app.plan_db import get_metric_logs
    iso_date = _today_iso()
    logs = await get_metric_logs(user, iso_date)
    return {"status": "success", "date": iso_date, "logs": {str(k): v for k, v in logs.items()}}


@router.get("/logs/recent")
async def logs_recent(
    metric_id: int = Query(...),
    days: int = Query(7, ge=1, le=90),
    user: str = Depends(get_current_user),
) -> dict:
    """Recent logs for a single metric."""
    from app.plan_db import get_recent_metric_logs
    rows = await get_recent_metric_logs(user, metric_id, days)
    return {"status": "success", "metric_id": metric_id, "days": days, "logs": rows}


# ---------------------------------------------------------------------------
# Analytics (both patient and practitioner can access)
# ---------------------------------------------------------------------------
@router.get("/analytics/adherence")
async def analytics_adherence(
    date: str | None = Query(None),
    days: int = Query(0, ge=0, le=90),
    user: str = Depends(get_current_user),
) -> dict:
    """Per-metric adherence % for a given date, or a summary over N days."""
    if days > 0:
        result = await compute_adherence_summary(user, days)
        return {"status": "success", **result}
    iso_date = date or _today_iso()
    result = await compute_adherence_for_date(user, iso_date)
    return {"status": "success", **result}


@router.get("/analytics/trends")
async def analytics_trends(
    days: int = Query(14, ge=2, le=90),
    user: str = Depends(get_current_user),
) -> dict:
    result = await compute_trends(user, days)
    return {"status": "success", **result}


@router.get("/analytics/correlations")
async def analytics_correlations(
    days: int = Query(30, ge=7, le=180),
    user: str = Depends(get_current_user),
) -> dict:
    result = await compute_correlations(user, days)
    return {"status": "success", **result}


@router.get("/analytics/biomarker-progress")
async def analytics_biomarker_progress(
    user: str = Depends(get_current_user),
) -> dict:
    result = await compute_biomarker_progress(user)
    return {"status": "success", **result}


# ---------------------------------------------------------------------------
# Insights (AI-generated, on-demand with caching)
# ---------------------------------------------------------------------------
@router.get("/insights/weekly-report")
async def insights_weekly_report(user: str = Depends(get_current_user)) -> dict:
    """AI-generated weekly narrative report (cached for the week)."""
    from app.plan_insights import generate_weekly_report
    report = await generate_weekly_report(user)
    return {"status": "success", "report": report}


@router.get("/insights/trend-alerts")
async def insights_trend_alerts(user: str = Depends(get_current_user)) -> dict:
    """AI-flagged notable trends requiring attention."""
    from app.plan_insights import generate_trend_alerts
    alerts = await generate_trend_alerts(user)
    return {"status": "success", "alerts": alerts}


class PlanSuggestionRequest(BaseModel):
    reason: str | None = None


@router.post("/insights/plan-suggestion")
async def insights_plan_suggestion(
    body: PlanSuggestionRequest | None = None,
    user: str = Depends(get_current_user),
) -> dict:
    """AI-generated plan adjustment suggestion (returned to practitioner for
    approval; not auto-applied)."""
    from app.plan_insights import generate_plan_suggestion
    suggestion = await generate_plan_suggestion(user, body.reason if body else None)
    return {"status": "success", "suggestion": suggestion}


# ---------------------------------------------------------------------------
# Plan suggestions management (practitioner-facing)
# ---------------------------------------------------------------------------
@router.get("/practitioner/patients/{username}/plan/suggestions")
async def list_suggestions(
    username: str,
    status_filter: str | None = Query(None, alias="status"),
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """List plan suggestions for a patient (optionally filtered by status)."""
    await _require_connection(practitioner_id, username)
    suggestions = await list_plan_suggestions(username, status_filter)
    return {"status": "success", "suggestions": suggestions}


class SuggestionDecisionRequest(BaseModel):
    decision: str = Field(..., description="approve | dismiss")


@router.post("/practitioner/patients/{username}/plan/suggestions/{suggestion_id}/decide")
async def decide_suggestion(
    username: str,
    suggestion_id: int,
    body: SuggestionDecisionRequest,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Approve or dismiss a plan suggestion. Approving applies the suggested
    changes to the plan (creates a new version)."""
    await _require_connection(practitioner_id, username)
    if body.decision not in ("approve", "dismiss"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'dismiss'")
    if body.decision == "dismiss":
        updated = await set_suggestion_status(suggestion_id, "dismissed", practitioner_id)
        if not updated:
            raise HTTPException(status_code=404, detail="Suggestion not found.")
        return {"status": "success", "suggestion": updated}
    # Approve: apply the suggestion to the plan.
    from app.plan_insights import apply_suggestion_to_plan
    suggestions = await list_plan_suggestions(username, "pending")
    target = next((s for s in suggestions if s["id"] == suggestion_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Pending suggestion not found.")
    new_plan = await apply_suggestion_to_plan(username, practitioner_id, target)
    await set_suggestion_status(suggestion_id, "approved", practitioner_id)
    return {"status": "success", "plan": new_plan, "suggestion_id": suggestion_id}


@router.post("/practitioner/patients/{username}/plan/suggestions/generate")
async def generate_suggestion(
    username: str,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Generate an AI plan adjustment suggestion for this patient based on
    their recent adherence trends and biomarker progress. Stores the suggestion
    in plan_suggestions (status=pending) and returns it for practitioner review.
    """
    await _require_connection(practitioner_id, username)
    from app.plan_insights import generate_plan_suggestion
    from app.plan_db import add_plan_suggestion
    suggestion = await generate_plan_suggestion(username)
    stored = await add_plan_suggestion(username, practitioner_id, "ai_insight", suggestion)
    return {"status": "success", "suggestion": stored}
