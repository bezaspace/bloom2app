"""AI features for practitioners: patient progress summaries and per-patient
question-answering, both grounded in the patient's live data.

Uses ``gemini-3.1-flash-lite`` (the same model as document processing) via
``google-genai``. Both functions pull the patient's current data through the
existing DB functions and feed it to the model as context — no new data
plumbing, no training, no persistence of the chat (stateless per question).
"""

import json
import logging
import os

from google import genai
from google.genai import types

from app.database import (
    get_daily_logs,
    get_daily_schedule,
    get_profile,
    get_recent_daily_logs,
    list_biomarkers,
)

logger = logging.getLogger("bloom2.practitioner_ai")

AI_MODEL = os.getenv("PRACTITIONER_AI_MODEL", "gemini-3.1-flash-lite")


def _client() -> genai.Client:
    return genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


async def _collect_patient_data(username: str) -> dict:
    """Gather the patient's current data bundle for AI context."""
    from datetime import date, timedelta

    profile_data = await get_profile(username)
    iso_today = date.today().isoformat()
    schedule = await get_daily_schedule(username, iso_today)
    logs = await get_daily_logs(username, iso_today)
    biomarkers = await list_biomarkers(username)

    # Last 7 days of logs per domain for trend context.
    recent: dict[str, list] = {}
    for domain in ("workout", "diet", "meditation", "medication", "mental_health"):
        rows = await get_recent_daily_logs(username, domain, 7)
        recent[domain] = rows

    return {
        "username": username,
        "onboarded": bool(profile_data and profile_data.get("onboarded")),
        "onboarded_at": profile_data.get("onboarded_at") if profile_data else None,
        "profile": profile_data.get("profile") if profile_data else None,
        "plan": profile_data.get("plan") if profile_data else None,
        "doc_summary": profile_data.get("doc_summary") if profile_data else None,
        "today_date": iso_today,
        "today_schedule": schedule,
        "today_logs": logs,
        "recent_7day_logs": recent,
        "biomarkers": biomarkers,
    }


def _compact_data(data: dict) -> str:
    """Serialize the patient data bundle into a compact JSON string for the
    model prompt. Trims large nested structures to keep the prompt bounded."""
    return json.dumps(data, default=str)[:12000]


async def generate_patient_summary(username: str) -> dict:
    """Generate a plain-language summary of the patient's progress plus a
    short list of notable items (e.g. declining HbA1c, missed medications).

    Returns:
        dict with: summary (str), notable_items (list[str]),
        generated_for_date (str).
    """
    data = await _collect_patient_data(username)
    if not data["onboarded"]:
        return {
            "summary": "This patient has not completed onboarding yet.",
            "notable_items": [],
            "generated_for_date": data["today_date"],
        }

    prompt = (
        "You are an AI assistant helping a healthcare practitioner quickly "
        "understand a patient's wellness progress. Below is the patient's "
        "current data as JSON. Write a concise (4-6 sentence) plain-language "
        "summary of their progress: where they are in their plan, how they've "
        "been doing over the past week, adherence trends, and any notable "
        "biomarker changes. Then list 2-5 'notable items' — specific, "
        "actionable observations (e.g. 'HbA1c down 0.3 points since last "
        "reading', '5-day meditation streak', 'Missed medication on 2 of last "
        "7 days'). Be factual — only reference data present in the JSON. Do "
        "not give medical diagnoses or prescribing advice.\n\n"
        f"Patient data:\n{_compact_data(data)}"
    )

    # Use structured output for a consistent shape.
    from pydantic import BaseModel, Field

    class AISummary(BaseModel):
        summary: str = Field(..., description="4-6 sentence plain-language progress summary.")
        notable_items: list[str] = Field(
            default_factory=list,
            description="2-5 specific, actionable observations.",
        )

    client = _client()
    response = await client.aio.models.generate_content(
        model=AI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AISummary,
            temperature=0.3,
        ),
    )
    parsed = response.parsed
    if isinstance(parsed, AISummary):
        return {
            "summary": parsed.summary,
            "notable_items": parsed.notable_items,
            "generated_for_date": data["today_date"],
        }
    # Fallback: parse text.
    import json as _json
    try:
        obj = _json.loads(response.text or "{}")
        return {
            "summary": obj.get("summary", ""),
            "notable_items": obj.get("notable_items", []),
            "generated_for_date": data["today_date"],
        }
    except _json.JSONDecodeError:
        return {
            "summary": response.text or "",
            "notable_items": [],
            "generated_for_date": data["today_date"],
        }


async def answer_practitioner_question(
    username: str, question: str
) -> str:
    """Answer a practitioner's free-text question about a patient, grounded
    in that patient's current data. Stateless (no multi-turn memory)."""
    data = await _collect_patient_data(username)
    if not data["onboarded"]:
        return "This patient has not completed onboarding yet, so there is no progress data to answer from."

    prompt = (
        "You are an AI assistant helping a healthcare practitioner. Answer the "
        "practitioner's question about their patient, using ONLY the patient's "
        "current data provided below as JSON. Be concise (2-4 sentences). If "
        "the answer cannot be determined from the data, say so explicitly — do "
        "not fabricate. Do not provide medical diagnoses or prescribing advice; "
        "if asked for that, redirect to clinical judgement.\n\n"
        f"Patient data:\n{_compact_data(data)}\n\n"
        f"Practitioner's question: {question}"
    )

    client = _client()
    response = await client.aio.models.generate_content(
        model=AI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2),
    )
    return response.text or ""
