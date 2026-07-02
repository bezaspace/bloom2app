"""AI-generated daily wellness schedule.

On the first request for a given day, ``generate_daily_schedule`` calls
``gemini-3.1-flash-lite`` with the user's profile, 90-day plan, document
summary, current plan phase, and day-of-plan as context, and asks for a
structured ``DailySchedule`` (timed items across the day + aggregate daily
targets + a motivational note). The result is cached in the
``daily_schedules`` SQLite table for the rest of the day.

Regeneration (via ``POST /dashboard/schedule/regenerate``) deletes the cached
row and re-runs generation — useful when the user skipped yesterday or wants
variety.
"""

import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Optional

from google import genai
from google.genai import types

from app.dashboard.schemas import DailySchedule

logger = logging.getLogger("bloom2.generator")

SCHEDULE_MODEL = os.getenv("DOC_MODEL", "gemini-3.1-flash-lite")


def _client() -> genai.Client:
    return genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


def _today_iso() -> str:
    return date.today().isoformat()


def _compute_day_of_plan(onboarded_at: Optional[str]) -> int:
    """Days since onboarding was finalized (1-indexed). Falls back to 1."""
    if not onboarded_at:
        return 1
    try:
        # onboarded_at is a full ISO datetime; parse and take the date part.
        dt = datetime.fromisoformat(onboarded_at.replace("Z", "+00:00"))
        started = dt.date()
    except (ValueError, TypeError):
        return 1
    delta = (date.today() - started).days + 1
    return max(1, min(delta, 90))


def _phase_for_day(day: int, plan: Optional[dict]) -> str:
    """Determine the current phase name from the day-of-plan and the plan."""
    if plan and plan.get("phases"):
        phases = plan["phases"]
        # Phases are typically 3 x 30 days. Pick by index.
        idx = min(len(phases) - 1, (day - 1) // 30)
        return phases[idx].get("name", f"Phase {idx + 1}")
    if day <= 30:
        return "Phase 1: Days 1-30"
    if day <= 60:
        return "Phase 2: Days 31-60"
    return "Phase 3: Days 61-90"


def _phase_focus(day: int, plan: Optional[dict]) -> str:
    """The focus text for the current phase, if available."""
    if plan and plan.get("phases"):
        phases = plan["phases"]
        idx = min(len(phases) - 1, (day - 1) // 30)
        return phases[idx].get("focus", "")
    return ""


async def generate_daily_schedule(
    profile: dict,
    plan: dict,
    doc_summary: Optional[dict],
    onboarded_at: Optional[str],
    target_date: Optional[str] = None,
) -> DailySchedule:
    """Generate (or regenerate) today's schedule via Gemini Flash-Lite.

    Args:
        profile: The user's onboarding profile dict.
        plan: The user's 90-day wellness plan dict.
        doc_summary: Optional structured document summary (conditions, meds, labs).
        onboarded_at: ISO datetime string of when onboarding was finalized.
        target_date: ISO date to generate for (defaults to today).

    Returns:
        A validated :class:`DailySchedule`.
    """
    iso_date = target_date or _today_iso()
    day_of_plan = _compute_day_of_plan(onboarded_at)
    phase = _phase_for_day(day_of_plan, plan)
    phase_focus = _phase_focus(day_of_plan, plan)

    # Build a compact context string for the model.
    context = {
        "date": iso_date,
        "day_of_plan": day_of_plan,
        "phase": phase,
        "phase_focus": phase_focus,
        "profile": profile,
        "plan_summary": plan.get("summary", "") if plan else "",
        "weekly_rhythm": plan.get("weekly_rhythm", "") if plan else "",
        "doc_summary": doc_summary,
    }

    prompt = (
        "You are the scheduling engine for Bloom, an experimental wellness app. "
        "Generate a single day's wellness schedule for the user described in the "
        "JSON context below. The schedule should be realistic, specific, and "
        "tailored to the user's goal, activity level, dietary preferences, "
        "available time, equipment, and any medical context from their uploaded "
        "documents. It must align with the current phase of their 90-day plan.\n\n"
        f"USER CONTEXT (JSON):\n{json.dumps(context, default=str)}\n\n"
        "Produce a schedule with 4-8 timed items spread across the day (morning, "
        "midday, afternoon, evening). Each item has a time (HH:MM 24h), a short "
        "title, a domain (one of: workout, diet, medication, mental_health, "
        "meditation, other), an optional duration in minutes, a one-sentence "
        "detail, and an optional quantitative target. Also provide aggregate "
        "daily_targets (e.g. workout_minutes, meditation_minutes, meals_logged, "
        "meds_taken) and a short motivational_note (1-2 sentences, warm and "
        "encouraging, no medical advice).\n\n"
        "Keep it general-wellness only — no medical prescriptions or diagnoses. "
        "If the user has documented conditions or medications, schedule "
        "medication reminders for any mentioned medications and avoid "
        "recommending activities that would be unsafe for their conditions."
    )

    client = _client()
    try:
        response = await client.aio.models.generate_content(
            model=SCHEDULE_MODEL,
            contents=types.Content(parts=[types.Part(text=prompt)]),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DailySchedule,
                temperature=0.7,
            ),
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Schedule generation failed: %s", e, exc_info=True)
        # Return a minimal fallback schedule so the dashboard still renders.
        return DailySchedule(
            date=iso_date,
            day_of_plan=day_of_plan,
            phase=phase,
            focus_today=phase_focus or "Continue your wellness journey.",
            items=[],
            daily_targets={},
            motivation_note="Have a great day — Bloom is here when you need me.",
        )

    parsed: Optional[DailySchedule] = response.parsed
    if parsed is not None:
        # Ensure the date and day-of-plan match what we computed (the model may
        # echo a different value).
        parsed.date = iso_date
        parsed.day_of_plan = day_of_plan
        parsed.phase = phase
        return parsed

    # Fallback: parse text manually.
    import json as _json

    text = response.text or "{}"
    try:
        data = _json.loads(text)
        data["date"] = iso_date
        data["day_of_plan"] = day_of_plan
        data["phase"] = phase
        return DailySchedule.model_validate(data)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not parse schedule JSON: %s", e)
        return DailySchedule(
            date=iso_date,
            day_of_plan=day_of_plan,
            phase=phase,
            focus_today=phase_focus or "Continue your wellness journey.",
            items=[],
            daily_targets={},
            motivation_note="Have a great day — Bloom is here when you need me.",
        )
