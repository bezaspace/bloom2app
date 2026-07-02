"""Socket.io server for real-time patient <-> practitioner text chat.

Mounted on the FastAPI app at ``/ws/socketio`` via ``socketio.ASGIApp``.

Authentication
--------------
Both clients pass a token in the socket handshake ``auth`` payload:

  - **Patient mobile app**: its long-lived bearer token (same one used for the
    REST API and the voice WebSocket). Resolved via ``get_user_by_token``.
  - **Practitioner web app**: a short-lived, single-use WS token minted by the
    Next.js BFF (``POST /api/auth/ws-token`` -> ``POST /practitioner/ws-token``).
    The long-lived bearer token never reaches the browser. Resolved via
    ``consume_ws_token`` (which marks it used and enforces a 60s TTL).

Rooms
-----
Each conversation has one room named with the deterministic
``conversation_id`` (``f"{practitioner_id}:{patient_username}"``). On connect,
the socket joins every room for which the authenticated user has an active
``practitioner_patient_connections`` row.

Events
------
  - ``message``  (client -> server): { practitioner_id, patient_username, body }
        Persists the message and emits ``message`` back to the whole room.
  - ``typing``   (client -> server): { conversation_id, is_typing }
        Broadcast to the room (not persisted).
  - ``message_read`` (client -> server): { conversation_id }
        Marks the other party's messages as read and emits ``read`` to the room.
  - ``message``  (server -> client): the saved message dict.
  - ``typing``   (server -> client): { conversation_id, sender, is_typing }.
  - ``read``     (server -> client): { conversation_id, reader }.
"""

import logging
import os

import socketio

from app.chat_db import (
    consume_ws_token,
    list_conversations_for_practitioner,
    list_conversations_for_patient,
    mark_read,
    save_message,
)
from app.database import get_user_by_token
from app.practitioner_db import has_connection

logger = logging.getLogger("bloom2.chat_socket")

# Origins allowed to connect. In development the patient app (Expo web on
# :8081) and the practitioner app (Next.js on :3000) both talk to FastAPI on
# :8000. We default to permissive CORS for local dev; tighten via env for prod.
_CLIENT_ORIGINS = os.getenv("CHAT_SOCKET_CORS_ORIGINS", "*")
if _CLIENT_ORIGINS == "*":
    _CORS = "*"
else:
    _CORS = [o.strip() for o in _CLIENT_ORIGINS.split(",") if o.strip()]

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=_CORS,
    # The server is mounted on FastAPI at /chat-ws. Starlette's Mount does NOT
    # strip the mount prefix from scope['path'], so the socketio_path must
    # include the prefix for the ASGIApp's path check to match. Clients connect
    # with path "/chat-ws/socket.io".
    socketio_path="chat-ws/socket.io",
)


def _conversation_id(practitioner_id: int, patient_username: str) -> str:
    return f"{practitioner_id}:{patient_username}"


async def _resolve_identity(auth: dict | None) -> dict | None:
    """Resolve the connecting client's identity from the handshake auth.

    Returns ``{role, ...}`` or None. Tries patient token first, then a
    practitioner WS token."""
    if not auth or not isinstance(auth, dict):
        return None
    token = auth.get("token")
    if not token or not isinstance(token, str):
        return None

    # Patient bearer token.
    username = await get_user_by_token(token)
    if username:
        return {"role": "patient", "username": username}

    # Practitioner short-lived WS token.
    pid = await consume_ws_token(token)
    if pid is not None:
        return {"role": "practitioner", "practitioner_id": pid}

    return None


async def _rooms_for_identity(identity: dict) -> list[str]:
    """Return the conversation rooms this user should join."""
    if identity["role"] == "patient":
        convs = await list_conversations_for_patient(identity["username"])
        return [c["conversation_id"] for c in convs]
    else:
        convs = await list_conversations_for_practitioner(
            identity["practitioner_id"]
        )
        return [c["conversation_id"] for c in convs]


@sio.event
async def connect(sid, environ, auth):  # noqa: ARG001
    identity = await _resolve_identity(auth)
    if identity is None:
        logger.warning("Socket %s rejected: invalid auth", sid)
        await sio.disconnect(sid)
        return False

    await sio.save_session(sid, identity)
    rooms = await _rooms_for_identity(identity)
    for room in rooms:
        await sio.enter_room(sid, room)
    logger.info(
        "Socket %s connected as %s, joined %d room(s)",
        sid, identity, len(rooms),
    )


@sio.event
async def disconnect(sid):
    logger.info("Socket %s disconnected", sid)


@sio.on("message")
async def on_message(sid, data):
    """Persist + broadcast a chat message.

    Expected payload: { practitioner_id: int, patient_username: str, body: str }
    The sender is inferred from the socket's identity so a client cannot spoof
    the other party.
    """
    identity = await sio.get_session(sid)
    if identity is None:
        return

    if not isinstance(data, dict):
        return
    pid = data.get("practitioner_id")
    uname = data.get("patient_username")
    body = data.get("body")
    if not isinstance(pid, int) or not isinstance(uname, str) or not isinstance(body, str):
        return
    body = body.strip()
    if not body:
        return

    # Authorization: an active connection must exist.
    if not await has_connection(pid, uname):
        logger.warning(
            "Socket %s: no active connection for practitioner %s / patient %s",
            sid, pid, uname,
        )
        return

    # Sender role must match identity.
    if identity["role"] == "patient":
        if identity["username"] != uname:
            return
        sender = "patient"
    else:
        if identity["practitioner_id"] != pid:
            return
        sender = "practitioner"

    msg = await save_message(pid, uname, sender, body)
    room = _conversation_id(pid, uname)
    await sio.emit("message", msg, room=room)


@sio.on("typing")
async def on_typing(sid, data):
    """Broadcast a typing indicator to the conversation room.

    Expected payload: { practitioner_id, patient_username, is_typing }
    """
    identity = await sio.get_session(sid)
    if identity is None or not isinstance(data, dict):
        return
    pid = data.get("practitioner_id")
    uname = data.get("patient_username")
    is_typing = bool(data.get("is_typing"))
    if not isinstance(pid, int) or not isinstance(uname, str):
        return
    if identity["role"] == "patient" and identity["username"] != uname:
        return
    if identity["role"] == "practitioner" and identity["practitioner_id"] != pid:
        return
    room = _conversation_id(pid, uname)
    await sio.emit(
        "typing",
        {"conversation_id": room, "sender": identity["role"], "is_typing": is_typing},
        room=room,
        skip_sid=sid,
    )


@sio.on("message_read")
async def on_message_read(sid, data):
    """Mark the other party's messages in a conversation as read and notify
    the room.

    Expected payload: { practitioner_id, patient_username }
    """
    identity = await sio.get_session(sid)
    if identity is None or not isinstance(data, dict):
        return
    pid = data.get("practitioner_id")
    uname = data.get("patient_username")
    if not isinstance(pid, int) or not isinstance(uname, str):
        return
    if identity["role"] == "patient" and identity["username"] != uname:
        return
    if identity["role"] == "practitioner" and identity["practitioner_id"] != pid:
        return
    room = _conversation_id(pid, uname)
    await mark_read(room, identity["role"])
    await sio.emit(
        "read",
        {"conversation_id": room, "reader": identity["role"]},
        room=room,
        skip_sid=sid,
    )


def make_socketio_app() -> socketio.ASGIApp:
    """Return the ASGI app that mounts the Socket.io server. Mount this on the
    FastAPI app at ``/chat-ws``."""
    return socketio.ASGIApp(sio, socketio_path="chat-ws/socket.io")
