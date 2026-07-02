"""AI insight generation (Gemini Flash-Lite): weekly report, trend alerts,
and plan adjustment suggestions.

Builds on ``plan_analytics.py`` output. The LLM receives the computed
numbers + raw context (patient notes, plan rationale, biomarker history)
and generates narrative insights, clinical reasoning, and plan adjustment
suggestions. The LLM never does the math.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta
from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.database import get_profile, list_biomarkers
from app.plan_analytics import (
    compute_adherence_summary,
    compute_biomarker_progress,
    compute_correlations,
    compute_trends,
)
from app.plan_db import (
    add_plan_suggestion,
    get_active_plan,
)

logger = logging.getLogger("bloom2.plan_insights")

AI_MODEL = os.getenv("PRACTITIONER_AI_MODEL", "gemini-3.1-flash-lite")


def _client() -> genai.Client:
    return genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


async def _collect_analytics_bundle(username: str) -> dict:
    """Gather the computed analytics + raw context for the AI prompt."""
    plan = await get_active_plan(username)
    profile_data = await get_profile(username)
    biomarkers = await list_biomarkers(username)
    adherence = await compute_adherence_summary(username, days=7)
    trends = await compute_trends(username, days=14)
    correlations = await compute_correlations(username, days=30)
    outcomes = await compute_biomarker_progress(username)
    return {
        "username": username,
        "plan_title": plan.get("title") if plan else None,
        "plan_rationale": plan.get("rationale") if plan else None,
        "plan_metrics": plan.get("metrics") if plan else [],
        "plan_phases": plan.get("phases") if plan else [],
        "profile": profile_data.get("profile") if profile_data else None,
        "doc_summary": profile_data.get("doc_summary") if profile_data else None,
        "biomarkers": biomarkers,
        "adherence_7day": adherence,
        "trends_14day": trends,
        "correlations_30day": correlations,
        "outcome_progress": outcomes,
    }


def _compact(data: dict) -> str:
    return json.dumps(data, default=str)[:16000]


# ---------------------------------------------------------------------------
# Weekly report
# ---------------------------------------------------------------------------
class WeeklyReport(BaseModel):
    narrative: str = Field(..., description="4-7 sentence narrative summary of the week.")
    highlights: list[str] = Field(default_factory=list, description="2-5 notable items.")
    concerns: list[str] = Field(default_factory=list, description="0-3 items needing attention.")


async def generate_weekly_report(username: str) -> dict:
    """Generate an AI weekly narrative report grounded in computed analytics."""
    data = await _collect_analytics_bundle(username)
    if not data["plan_metrics"]:
        return {
            "narrative": "No active plan yet — no weekly report to generate.",
            "highlights": [],
            "concerns": [],
            "generated_for_week": date.today().isoformat(),
        }
    prompt = (
        "You are an AI assistant helping a healthcare practitioner understand "
        "a patient's wellness week. Below is the patient's computed analytics "
        "(adherence, trends, correlations, outcome progress) plus their plan "
        "and profile as JSON. Write a concise (4-7 sentence) narrative summary "
        "of the week: overall adherence, which metrics are on track, which are "
        "slipping, any notable trends or correlations, and outcome progress. "
        "Then list 2-5 'highlights' (positive observations) and 0-3 'concerns' "
        "(items needing attention). Be factual — only reference data present in "
        "the JSON. Do not give medical diagnoses or prescribing advice.\n\n"
        f"Patient analytics:\n{_compact(data)}"
    )
    client = _client()
    try:
        response = await client.aio.models.generate_content(
            model=AI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=WeeklyReport,
                temperature=0.3,
            ),
        )
        parsed = response.parsed
        if isinstance(parsed, WeeklyReport):
            return {
                "narrative": parsed.narrative,
                "highlights": parsed.highlights,
                "concerns": parsed.concerns,
                "generated_for_week": date.today().isoformat(),
            }
        try:
            obj = json.loads(response.text or "{}")
            return {
                "narrative": obj.get("narrative", ""),
                "highlights": obj.get("highlights", []),
                "concerns": obj.get("concerns", []),
                "generated_for_week": date.today().isoformat(),
            }
        except json.JSONDecodeError:
            return {
                "narrative": response.text or "",
                "highlights": [],
                "concerns": [],
                "generated_for_week": date.today().isoformat(),
            }
    except Exception as e:  # noqa: BLE001
        logger.error("Weekly report generation failed: %s", e, exc_info=True)
        return {
            "narrative": f"Could not generate weekly report: {e}",
            "highlights": [],
            "concerns": [],
            "generated_for_week": date.today().isoformat(),
        }


# ---------------------------------------------------------------------------
# Trend alerts
# ---------------------------------------------------------------------------
class TrendAlert(BaseModel):
    metric: str
    severity: str = Field(..., description="info | warning | critical")
    message: str


class TrendAlertsResult(BaseModel):
    alerts: list[TrendAlert]


async def generate_trend_alerts(username: str) -> list[dict]:
    """AI-flagged notable trends requiring attention."""
    data = await _collect_analytics_bundle(username)
    if not data["plan_metrics"]:
        return []
    prompt = (
        "You are an AI assistant monitoring a patient's wellness metrics for "
        "notable trends that may require attention. Below is the patient's "
        "computed analytics (trends, adherence, correlations, outcomes) as JSON. "
        "Identify 0-5 'trend alerts' — specific, actionable observations about "
        "metrics that are consistently missing targets, declining sharply, or "
        "showing concerning correlations. For each, set severity: 'info' (worth "
        "noting), 'warning' (should discuss with patient), or 'critical' (act "
        "soon). Be factual — only reference data present in the JSON. Do not "
        "give medical diagnoses.\n\n"
        f"Patient analytics:\n{_compact(data)}"
    )
    client = _client()
    try:
        response = await client.aio.models.generate_content(
            model=AI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=TrendAlertsResult,
                temperature=0.2,
            ),
        )
        parsed = response.parsed
        if isinstance(parsed, TrendAlertsResult):
            return [a.model_dump() for a in parsed.alerts]
        try:
            obj = json.loads(response.text or "{}")
            return obj.get("alerts", [])
        except json.JSONDecodeError:
            return []
    except Exception as e:  # noqa: BLE001
        logger.error("Trend alerts generation failed: %s", e, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Plan adjustment suggestions
# ---------------------------------------------------------------------------
class PlanSuggestionChange(BaseModel):
    metric_label: str
    change: str = Field(..., description="e.g., 'lower target from 7hrs to 6.5hrs'")
    rationale: str


class PlanSuggestion(BaseModel):
    summary: str
    changes: list[PlanSuggestionChange]
    expected_effect: str


async def generate_plan_suggestion(
    username: str, reason: str | None = None
) -> dict:
    """Generate an AI plan adjustment suggestion. The suggestion is stored
    in the plan_suggestions table (pending) for the practitioner to approve
    or dismiss. Not auto-applied."""
    data = await _collect_analytics_bundle(username)
    if not data["plan_metrics"]:
        return {"summary": "No active plan to adjust.", "changes": [], "expected_effect": ""}
    prompt = (
        "You are an AI assistant helping a healthcare practitioner optimize a "
        "patient's tracking plan. Below is the patient's computed analytics "
        "(adherence, trends, correlations, outcomes) plus the current plan as "
        "JSON. Propose 0-3 specific plan adjustments that would help the "
        "patient succeed — e.g., lowering a target that's consistently missed, "
        "adding a metric that would clarify a correlation, or emphasizing a "
        "lever that's driving an outcome. For each change, explain the "
        "rationale grounded in the data. Do not give medical diagnoses or "
        "prescribing advice.\n\n"
        + (f"Practitioner's reason for requesting: {reason}\n\n" if reason else "")
        + f"Patient analytics + plan:\n{_compact(data)}"
    )
    client = _client()
    try:
        response = await client.aio.models.generate_content(
            model=AI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PlanSuggestion,
                temperature=0.3,
            ),
        )
        parsed = response.parsed
        if isinstance(parsed, PlanSuggestion):
            suggestion = {
                "summary": parsed.summary,
                "changes": [c.model_dump() for c in parsed.changes],
                "expected_effect": parsed.expected_effect,
            }
        else:
            try:
                suggestion = json.loads(response.text or "{}")
            except json.JSONDecodeError:
                suggestion = {"summary": response.text or "", "changes": [], "expected_effect": ""}
    except Exception as e:  # noqa: BLE001
        logger.error("Plan suggestion generation failed: %s", e, exc_info=True)
        suggestion = {"summary": f"Could not generate suggestion: {e}", "changes": [], "expected_effect": ""}
    # Persist as a pending suggestion.
    await add_plan_suggestion(username, None, "ai", suggestion)
    return suggestion


async def apply_suggestion_to_plan(
    username: str, practitioner_id: int, suggestion: dict
) -> dict:
    """Apply an approved suggestion to the plan by creating a new version.

    The suggestion's `changes` are interpreted as best-effort edits to the
    current plan's metrics (matching by label). The AI's narrative is added
    to the rationale.
    """
    from app.plan_db import create_plan
    plan = await get_active_plan(username)
    if not plan:
        raise ValueError("No active plan to apply suggestion to.")
    # Build the new plan from the current one, applying changes by label match.
    changes_by_label: dict[str, dict] = {}
    for c in suggestion.get("changes", []):
        label = c.get("metric_label") or c.get("label")
        if label:
            changes_by_label[label] = c
    new_metrics = []
    for m in plan["metrics"]:
        nm = dict(m)
        change = changes_by_label.get(m["label"])
        if change:
            # Best-effort: parse a new target value from the change string if
            # it contains "to <number>". This is intentionally simple — the
            # practitioner can refine via the manual editor afterward.
            text = change.get("change", "")
            import re
            match = re.search(r"to\s+(\d+\.?\d*)", text)
            if match:
                nm["target_value"] = float(match.group(1))
        nm.pop("id", None)
        nm.pop("plan_id", None)
        new_metrics.append(nm)
    new_outcomes = []
    for o in plan["outcomes"]:
        no = dict(o)
        no.pop("id", None)
        no.pop("plan_id", None)
        new_outcomes.append(no)
    new_phases = []
    for p in plan["phases"]:
        np_ = dict(p)
        np_.pop("id", None)
        np_.pop("plan_id", None)
        new_phases.append(np_)
    new_rationale = (plan.get("rationale") or "") + "\n\n[AI suggestion applied]: " + suggestion.get("summary", "")
    new_plan = await create_plan(
        username, practitioner_id, plan.get("title"), new_rationale,
        new_outcomes, new_metrics, new_phases,
    )
    return new_plan
