"""Practitioner-facing routes: appointment management, connected patients,
and read access to a connected patient's dashboard data.

Authorization: every ``/practitioner/patients/{username}/*`` endpoint verifies
that an active ``practitioner_patient_connections`` row exists for the current
practitioner and that patient before returning any data.
"""

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.database import (
    get_daily_logs,
    get_daily_schedule,
    get_profile,
    get_recent_daily_logs,
    list_biomarkers,
)
from app.practitioner_auth import (
    get_current_practitioner_id,
    get_current_practitioner_token,
)
from app.practitioner_db import (
    add_note,
    ensure_connection,
    get_appointment,
    get_connection,
    get_practitioner_by_id,
    has_connection,
    list_appointments_for_practitioner,
    list_connections_for_practitioner,
    list_notes,
    save_ai_summary,
    set_appointment_status,
)

router = APIRouter(prefix="/practitioner", tags=["practitioner"])


def _today_iso() -> str:
    return date.today().isoformat()


async def _require_connection(
    practitioner_id: int, patient_username: str
) -> None:
    """403 if the practitioner has no active connection to this patient."""
    if not await has_connection(practitioner_id, patient_username):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active connection to this patient. Accept an appointment "
            "from them first to establish a connection.",
        )


# ---------------------------------------------------------------------------
# Practitioner profile
# ---------------------------------------------------------------------------
@router.get("/me")
async def get_me(
    payload=Depends(get_current_practitioner_token),
) -> dict:
    """Return the current practitioner's full public profile."""
    p = await get_practitioner_by_id(payload.practitioner_id)
    if not p:
        raise HTTPException(status_code=404, detail="Practitioner not found")
    return {"status": "success", "practitioner": p}


# ---------------------------------------------------------------------------
# Appointments management
# ---------------------------------------------------------------------------
@router.get("/appointments")
async def list_my_appointments(
    status_filter: str | None = Query(
        None, alias="status", description="pending|accepted|declined|completed|cancelled"
    ),
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """List all appointments for this practitioner, optionally filtered by
    status. Each appointment includes the patient's username (the practitioner
    sees the patient's Bloom username, not raw credentials)."""
    appts = await list_appointments_for_practitioner(practitioner_id, status_filter)
    return {"status": "success", "appointments": appts}


class DecisionRequest(BaseModel):
    note: str | None = None


@router.post("/appointments/{appointment_id}/accept")
async def accept_appointment(
    appointment_id: int,
    body: DecisionRequest | None = None,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Accept a pending appointment. This also creates (idempotently) a
    practitioner-patient connection so the practitioner can thereafter access
    that patient's dashboard data."""
    appt = await get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["practitioner_id"] != practitioner_id:
        raise HTTPException(status_code=403, detail="Not your appointment")
    if appt["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Appointment is already {appt['status']}, cannot accept",
        )
    note = body.note if body else None
    updated = await set_appointment_status(appointment_id, "accepted", note)
    # Establish the data-sharing connection.
    await ensure_connection(practitioner_id, appt["patient_username"])
    return {"status": "success", "appointment": updated}


@router.post("/appointments/{appointment_id}/decline")
async def decline_appointment(
    appointment_id: int,
    body: DecisionRequest | None = None,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Decline a pending appointment with an optional note."""
    appt = await get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["practitioner_id"] != practitioner_id:
        raise HTTPException(status_code=403, detail="Not your appointment")
    if appt["status"] != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Appointment is already {appt['status']}, cannot decline",
        )
    note = body.note if body else None
    updated = await set_appointment_status(appointment_id, "declined", note)
    return {"status": "success", "appointment": updated}


@router.post("/appointments/{appointment_id}/complete")
async def complete_appointment(
    appointment_id: int,
    body: DecisionRequest | None = None,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Mark an accepted appointment as completed."""
    appt = await get_appointment(appointment_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt["practitioner_id"] != practitioner_id:
        raise HTTPException(status_code=403, detail="Not your appointment")
    if appt["status"] != "accepted":
        raise HTTPException(
            status_code=400,
            detail=f"Only accepted appointments can be completed (this is {appt['status']})",
        )
    note = body.note if body else None
    updated = await set_appointment_status(appointment_id, "completed", note)
    return {"status": "success", "appointment": updated}


# ---------------------------------------------------------------------------
# Connected patients
# ---------------------------------------------------------------------------
@router.get("/patients")
async def list_my_patients(
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """List the practitioner's connected patients with summary stats
    (day-of-plan, onboarding status, biomarker count, last activity)."""
    connections = await list_connections_for_practitioner(practitioner_id)
    out = []
    for c in connections:
        uname = c["patient_username"]
        profile_data = await get_profile(uname)
        onboarded = bool(profile_data and profile_data.get("onboarded"))
        day_of_plan = 0
        phase = ""
        if onboarded and profile_data.get("onboarded_at"):
            from app.dashboard.generator import _compute_day_of_plan
            day_of_plan = _compute_day_of_plan(profile_data["onboarded_at"])
            plan = profile_data.get("plan") or {}
            phases = plan.get("phases", [])
            if phases:
                idx = min(len(phases) - 1, (day_of_plan - 1) // 30)
                phase = phases[idx].get("focus", "")
        biomarkers = await list_biomarkers(uname)
        out.append({
            "username": uname,
            "onboarded": onboarded,
            "day_of_plan": day_of_plan,
            "phase": phase,
            "biomarker_count": len(biomarkers),
            "established_at": c["established_at"],
            "has_ai_summary": bool(c.get("ai_summary")),
        })
    return {"status": "success", "patients": out}


@router.get("/patients/{username}")
async def get_patient_detail(
    username: str,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Full patient view: profile, plan, today's schedule, today's logs,
    biomarker count, and the connection metadata."""
    await _require_connection(practitioner_id, username)

    profile_data = await get_profile(username)
    if not profile_data:
        return {
            "status": "success",
            "username": username,
            "onboarded": False,
            "profile": None,
            "plan": None,
            "schedule": None,
            "logs": {},
            "biomarker_count": 0,
        }

    iso_date = _today_iso()
    schedule = await get_daily_schedule(username, iso_date)
    logs = await get_daily_logs(username, iso_date)
    biomarkers = await list_biomarkers(username)

    return {
        "status": "success",
        "username": username,
        "onboarded": profile_data.get("onboarded", False),
        "onboarded_at": profile_data.get("onboarded_at"),
        "profile": profile_data.get("profile"),
        "plan": profile_data.get("plan"),
        "doc_summary": profile_data.get("doc_summary"),
        "date": iso_date,
        "schedule": schedule,
        "logs": logs,
        "biomarker_count": len(biomarkers),
    }


@router.get("/patients/{username}/logs/recent")
async def get_patient_recent_logs(
    username: str,
    domain: str = Query(...),
    days: int = Query(7, ge=1, le=90),
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Recent logs for a single domain (for 7-day bar charts)."""
    await _require_connection(practitioner_id, username)
    rows = await get_recent_daily_logs(username, domain, days)
    return {"status": "success", "domain": domain, "days": days, "logs": rows}


@router.get("/patients/{username}/biomarkers")
async def get_patient_biomarkers(
    username: str,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """All biomarker readings for the patient, grouped by marker name
    (same shape as the patient-facing endpoint)."""
    await _require_connection(practitioner_id, username)
    rows = await list_biomarkers(username)
    groups: dict[str, dict] = {}
    for r in rows:
        g = groups.setdefault(
            r["name"],
            {
                "name": r["name"],
                "unit": r["unit"],
                "ref_low": None,
                "ref_high": None,
                "optimal_low": None,
                "optimal_high": None,
                "readings": [],
            },
        )
        if g["ref_low"] is None and r["ref_low"] is not None:
            g["ref_low"] = r["ref_low"]
        if g["ref_high"] is None and r["ref_high"] is not None:
            g["ref_high"] = r["ref_high"]
        if g["optimal_low"] is None and r["optimal_low"] is not None:
            g["optimal_low"] = r["optimal_low"]
        if g["optimal_high"] is None and r["optimal_high"] is not None:
            g["optimal_high"] = r["optimal_high"]
        g["readings"].append(r)
    for g in groups.values():
        g["readings"].reverse()
    return {"status": "success", "groups": list(groups.values())}


# ---------------------------------------------------------------------------
# Practitioner notes on patients
# ---------------------------------------------------------------------------
class NoteRequest(BaseModel):
    note_text: str = Field(..., min_length=1)


@router.post("/patients/{username}/notes")
async def create_note(
    username: str,
    body: NoteRequest,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Add a free-text note about a connected patient."""
    await _require_connection(practitioner_id, username)
    note = await add_note(practitioner_id, username, body.note_text)
    return {"status": "success", "note": note}


@router.get("/patients/{username}/notes")
async def list_patient_notes(
    username: str,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """List all notes the current practitioner has written about this patient,
    newest first."""
    await _require_connection(practitioner_id, username)
    notes = await list_notes(practitioner_id, username)
    return {"status": "success", "notes": notes}


# ---------------------------------------------------------------------------
# AI summary + chat (delegated to practitioner_ai module)
# ---------------------------------------------------------------------------
@router.post("/patients/{username}/ai-summary")
async def generate_patient_ai_summary(
    username: str,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Generate (or re-generate) an AI plain-language summary of the patient's
    progress. The result is cached on the connection row."""
    await _require_connection(practitioner_id, username)
    from app.practitioner_ai import generate_patient_summary
    summary = await generate_patient_summary(username)
    await save_ai_summary(practitioner_id, username, json.dumps(summary))
    return {"status": "success", "summary": summary}


@router.get("/patients/{username}/ai-summary")
async def get_cached_ai_summary(
    username: str,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Return the cached AI summary if one exists (without regenerating)."""
    await _require_connection(practitioner_id, username)
    c = await get_connection(practitioner_id, username)
    if not c or not c.get("ai_summary"):
        return {"status": "success", "summary": None}
    return {"status": "success", "summary": json.loads(c["ai_summary"])}


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)


@router.post("/patients/{username}/ai-chat")
async def patient_ai_chat(
    username: str,
    body: ChatRequest,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Answer a practitioner's question about a patient, grounded in that
    patient's current data."""
    await _require_connection(practitioner_id, username)
    from app.practitioner_ai import answer_practitioner_question
    answer = await answer_practitioner_question(username, body.question)
    return {"status": "success", "answer": answer}
