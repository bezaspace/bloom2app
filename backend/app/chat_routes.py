"""REST endpoints for chat history, sending (REST fallback), and conversation
listing.

These complement the Socket.io server: REST handles history/pagination and
serves as a send fallback when the socket is disconnected; the socket handles
live delivery. Sending via REST also emits the message over the socket so an
online recipient gets it in real time.

Authorization: a conversation only exists between a patient and a practitioner
with an active ``practitioner_patient_connections`` row.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.chat_db import (
    list_conversations_for_patient,
    list_conversations_for_practitioner,
    list_messages,
    mark_read,
    save_message,
)
from app.chat_socket import sio
from app.practitioner_auth import get_current_practitioner_id
from app.practitioner_db import (
    get_practitioner_by_id,
    has_connection,
)


# Patient-facing routes (bearer auth).
patient_router = APIRouter(prefix="/chat", tags=["chat"])

# Practitioner-facing routes (practitioner bearer auth).
practitioner_router = APIRouter(
    prefix="/practitioner/chat", tags=["practitioner-chat"]
)


def _conversation_id(practitioner_id: int, patient_username: str) -> str:
    return f"{practitioner_id}:{patient_username}"


async def _emit_message(msg: dict, room: str) -> None:
    """Best-effort emit over the socket; never raise (REST send must still
    succeed even if the socket layer has a problem)."""
    try:
        await sio.emit("message", msg, room=room)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Patient-facing
# ---------------------------------------------------------------------------
@patient_router.get("/conversations")
async def list_my_conversations(
    user: str = Depends(get_current_user),
) -> dict:
    """List the patient's chat conversations (one per connected practitioner
    they have exchanged messages with), with last message preview + unread
    count. Practitioner public profiles are attached for display."""
    convs = await list_conversations_for_patient(user)
    for c in convs:
        p = await get_practitioner_by_id(c["practitioner_id"])
        c["practitioner"] = p
    return {"status": "success", "conversations": convs}


@patient_router.get("/conversations/{practitioner_id}/messages")
async def list_messages_with_practitioner(
    practitioner_id: int,
    before: int | None = Query(None, description="Cursor: only messages with id < this"),
    limit: int = Query(50, ge=1, le=200),
    user: str = Depends(get_current_user),
) -> dict:
    """Fetch message history for a conversation, oldest-first. Use ``before``
    for cursor pagination (load older on scroll-up)."""
    if not await has_connection(practitioner_id, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active connection with this practitioner.",
        )
    conv = _conversation_id(practitioner_id, user)
    msgs = await list_messages(conv, before_id=before, limit=limit)
    return {"status": "success", "messages": msgs, "has_more": len(msgs) >= limit}


class PatientSendMessage(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


@patient_router.post("/conversations/{practitioner_id}/messages")
async def patient_send_message(
    practitioner_id: int,
    body: PatientSendMessage,
    user: str = Depends(get_current_user),
) -> dict:
    """Send a message as the patient. Persists and emits over the socket.
    Serves as a REST fallback when the socket is unavailable."""
    if not await has_connection(practitioner_id, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active connection with this practitioner.",
        )
    msg = await save_message(practitioner_id, user, "patient", body.body.strip())
    await _emit_message(msg, _conversation_id(practitioner_id, user))
    return {"status": "success", "message": msg}


@patient_router.post("/conversations/{practitioner_id}/read")
async def patient_mark_read(
    practitioner_id: int,
    user: str = Depends(get_current_user),
) -> dict:
    """Mark all practitioner messages in the conversation as read."""
    if not await has_connection(practitioner_id, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active connection with this practitioner.",
        )
    conv = _conversation_id(practitioner_id, user)
    n = await mark_read(conv, "patient")
    try:
        await sio.emit(
            "read", {"conversation_id": conv, "reader": "patient"}, room=conv
        )
    except Exception:  # noqa: BLE001
        pass
    return {"status": "success", "marked_read": n}


# ---------------------------------------------------------------------------
# Practitioner-facing
# ---------------------------------------------------------------------------
@practitioner_router.get("/conversations")
async def list_my_conversations_practitioner(
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """List the practitioner's chat conversations (one per connected patient
    they have exchanged messages with), with last message preview + unread
    count."""
    convs = await list_conversations_for_practitioner(practitioner_id)
    return {"status": "success", "conversations": convs}


@practitioner_router.get("/conversations/{username}/messages")
async def list_messages_with_patient(
    username: str,
    before: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Fetch message history for a conversation with a patient."""
    if not await has_connection(practitioner_id, username):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active connection to this patient.",
        )
    conv = _conversation_id(practitioner_id, username)
    msgs = await list_messages(conv, before_id=before, limit=limit)
    return {"status": "success", "messages": msgs, "has_more": len(msgs) >= limit}


class PractitionerSendMessage(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


@practitioner_router.post("/conversations/{username}/messages")
async def practitioner_send_message(
    username: str,
    body: PractitionerSendMessage,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Send a message as the practitioner. Persists and emits over the socket."""
    if not await has_connection(practitioner_id, username):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active connection to this patient.",
        )
    msg = await save_message(
        practitioner_id, username, "practitioner", body.body.strip()
    )
    await _emit_message(msg, _conversation_id(practitioner_id, username))
    return {"status": "success", "message": msg}


@practitioner_router.post("/conversations/{username}/read")
async def practitioner_mark_read(
    username: str,
    practitioner_id: int = Depends(get_current_practitioner_id),
) -> dict:
    """Mark all patient messages in the conversation as read."""
    if not await has_connection(practitioner_id, username):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active connection to this patient.",
        )
    conv = _conversation_id(practitioner_id, username)
    n = await mark_read(conv, "practitioner")
    try:
        await sio.emit(
            "read",
            {"conversation_id": conv, "reader": "practitioner"},
            room=conv,
        )
    except Exception:  # noqa: BLE001
        pass
    return {"status": "success", "marked_read": n}
