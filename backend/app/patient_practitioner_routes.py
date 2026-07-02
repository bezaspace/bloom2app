"""Patient-facing routes for browsing practitioners and booking appointments.

These use the patient auth (``get_current_user``) — the same bearer-token
dependency as the rest of the patient app — so the mobile app needs no new
auth plumbing.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.practitioner_db import (
    create_appointment,
    get_appointment,
    get_practitioner_by_id,
    list_active_practitioners,
    list_appointments_for_patient,
    set_appointment_status,
)

router = APIRouter(prefix="/practitioners", tags=["patient-practitioner"])


# ---------------------------------------------------------------------------
# Browse practitioners
# ---------------------------------------------------------------------------
@router.get("")
async def list_practitioners(
    search: str | None = Query(None, description="Search name/specialization/bio"),
    specialization: str | None = Query(None),
    user: str = Depends(get_current_user),
) -> dict:
    """List all active practitioners, optionally filtered by search text or
    specialization. Public fields only (no contact info beyond what the
    practitioner chose to expose)."""
    practitioners = await list_active_practitioners(search, specialization)
    return {"status": "success", "practitioners": practitioners}


@router.get("/{practitioner_id}")
async def get_practitioner(
    practitioner_id: int,
    user: str = Depends(get_current_user),
) -> dict:
    """Get a single practitioner's public profile."""
    p = await get_practitioner_by_id(practitioner_id)
    if not p or not p["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Practitioner not found",
        )
    return {"status": "success", "practitioner": p}


# ---------------------------------------------------------------------------
# Appointment booking
# ---------------------------------------------------------------------------
class BookAppointmentRequest(BaseModel):
    practitioner_id: int
    requested_date: str = Field(..., description="ISO date YYYY-MM-DD")
    requested_time: str | None = Field(
        None, description="HH:MM or null for 'any time'"
    )
    reason: str | None = None
    patient_note: str | None = None


@router.post("/appointments")
async def book_appointment(
    body: BookAppointmentRequest,
    user: str = Depends(get_current_user),
) -> dict:
    """Patient books an appointment request with a practitioner."""
    p = await get_practitioner_by_id(body.practitioner_id)
    if not p or not p["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Practitioner not found",
        )
    appt = await create_appointment(
        {
            "patient_username": user,
            "practitioner_id": body.practitioner_id,
            "requested_date": body.requested_date,
            "requested_time": body.requested_time,
            "reason": body.reason,
            "patient_note": body.patient_note,
        }
    )
    # Attach the practitioner's public profile for the client.
    appt["practitioner"] = p
    return {"status": "success", "appointment": appt}


@router.get("/appointments/mine")
async def my_appointments(
    user: str = Depends(get_current_user),
) -> dict:
    """List all of the current patient's appointments (all statuses), newest
    first, with the practitioner's public profile attached."""
    appts = await list_appointments_for_patient(user)
    # Attach practitioner profiles.
    out = []
    for a in appts:
        p = await get_practitioner_by_id(a["practitioner_id"])
        a["practitioner"] = p
        out.append(a)
    return {"status": "success", "appointments": out}


class CancelRequest(BaseModel):
    reason: str | None = None


@router.post("/appointments/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: int,
    body: CancelRequest | None = None,
    user: str = Depends(get_current_user),
) -> dict:
    """Patient cancels their own appointment. Only allowed if it's still
    pending (accepted appointments can't be patient-cancelled in v1 —
    contact the practitioner)."""
    appt = await get_appointment(appointment_id)
    if not appt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )
    if appt["patient_username"] != user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only cancel your own appointments",
        )
    if appt["status"] not in ("pending",):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only pending appointments can be cancelled",
        )
    note = body.reason if body else None
    updated = await set_appointment_status(
        appointment_id, "cancelled",
        practitioner_note=f"Patient cancelled: {note}" if note else "Patient cancelled",
    )
    return {"status": "success", "appointment": updated}
