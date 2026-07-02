"""PostgreSQL-backed store for patient <-> practitioner text chat messages.

Uses ``psycopg3`` (async) via the shared connection pool in ``app.db``.
Replaces the old SQLite + threading.Lock pattern.

Tables (created by the migration runner in ``app.db``):
  - chat_messages  — one row per message in every 1:1 conversation
  - ws_tokens      — short-lived, single-use tokens that let the practitioner
                     web app's browser authenticate a Socket.io connection
                     without exposing the long-lived bearer token

A conversation is identified by a deterministic ``conversation_id`` of the form
``f"{practitioner_id}:{patient_username}"``. A conversation only exists between
a patient and a practitioner with an active
``practitioner_patient_connections`` row — enforced by the routes/socket, not
by this module.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from app.db import execute, fetchall, fetchone, get_conn, now


# Short-lived WS token validity, in seconds.
WS_TOKEN_TTL = 60


def _conversation_id(practitioner_id: int, patient_username: str) -> str:
    return f"{practitioner_id}:{patient_username}"


# ---------------------------------------------------------------------------
# Message row helper
# ---------------------------------------------------------------------------
_MSG_COLS = (
    "id", "conversation_id", "practitioner_id", "patient_username",
    "sender", "body", "created_at", "read_at",
)


def _msg_row_to_dict(row: dict) -> dict:
    return {col: row.get(col) for col in _MSG_COLS}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
async def save_message(
    practitioner_id: int,
    patient_username: str,
    sender: str,
    body: str,
) -> dict:
    conv = _conversation_id(practitioner_id, patient_username)
    row = await fetchone(
        """
        INSERT INTO chat_messages
            (conversation_id, practitioner_id, patient_username,
             sender, body, created_at, read_at)
        VALUES (%s, %s, %s, %s, %s, %s, NULL)
        RETURNING id, conversation_id, practitioner_id, patient_username,
            sender, body, created_at, read_at
        """,
        (conv, practitioner_id, patient_username, sender, body, now()),
    )
    return _msg_row_to_dict(row)


async def list_messages(
    conversation_id: str,
    before_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return messages oldest-first for a conversation, optionally limited to
    those with id < before_id (cursor pagination for "load older")."""
    limit = max(1, min(limit, 200))
    cols = ", ".join(_MSG_COLS)
    if before_id is not None:
        rows = await fetchall(
            f"SELECT {cols} FROM chat_messages "
            "WHERE conversation_id = %s AND id < %s "
            "ORDER BY id DESC LIMIT %s",
            (conversation_id, before_id, limit),
        )
    else:
        rows = await fetchall(
            f"SELECT {cols} FROM chat_messages "
            "WHERE conversation_id = %s "
            "ORDER BY id DESC LIMIT %s",
            (conversation_id, limit),
        )
    # rows come newest-first; reverse for chronological display.
    return [_msg_row_to_dict(r) for r in reversed(rows)]


async def mark_read(
    conversation_id: str, reader: str
) -> int:
    """Mark all messages in the conversation sent by the *other* party as read.
    ``reader`` is "patient" or "practitioner". Returns the number of rows
    updated."""
    other = "practitioner" if reader == "patient" else "patient"
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE chat_messages SET read_at = %s "
                "WHERE conversation_id = %s AND sender = %s AND read_at IS NULL",
                (now(), conversation_id, other),
            )
            return cur.rowcount


async def unread_count(
    conversation_id: str, reader: str
) -> int:
    """Count messages from the other party that are unread by ``reader``."""
    other = "practitioner" if reader == "patient" else "patient"
    row = await fetchone(
        "SELECT COUNT(*) AS cnt FROM chat_messages "
        "WHERE conversation_id = %s AND sender = %s AND read_at IS NULL",
        (conversation_id, other),
    )
    return row["cnt"] if row else 0


async def list_conversations_for_practitioner(
    practitioner_id: int,
) -> list[dict]:
    """One row per patient the practitioner has chatted with, with the latest
    message preview and an unread count for the practitioner."""
    cols = ", ".join(_MSG_COLS)
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT DISTINCT patient_username FROM chat_messages "
                "WHERE practitioner_id = %s",
                (practitioner_id,),
            )
            rows = await cur.fetchall()
            out = []
            for row in rows:
                uname = row["patient_username"]
                conv = _conversation_id(practitioner_id, uname)
                await cur.execute(
                    f"SELECT {cols} FROM chat_messages "
                    "WHERE conversation_id = %s ORDER BY id DESC LIMIT 1",
                    (conv,),
                )
                last = await cur.fetchone()
                await cur.execute(
                    "SELECT COUNT(*) AS cnt FROM chat_messages "
                    "WHERE conversation_id = %s AND sender = 'patient' "
                    "AND read_at IS NULL",
                    (conv,),
                )
                unread_row = await cur.fetchone()
                out.append({
                    "patient_username": uname,
                    "practitioner_id": practitioner_id,
                    "conversation_id": conv,
                    "last_message": _msg_row_to_dict(last) if last else None,
                    "unread_count": unread_row["cnt"] if unread_row else 0,
                })
    return out


async def list_conversations_for_patient(
    patient_username: str,
) -> list[dict]:
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT DISTINCT practitioner_id FROM chat_messages "
                "WHERE patient_username = %s",
                (patient_username,),
            )
            rows = await cur.fetchall()
            out = []
            for row in rows:
                pid = row["practitioner_id"]
                conv = _conversation_id(pid, patient_username)
                await cur.execute(
                    f"SELECT {', '.join(_MSG_COLS)} FROM chat_messages "
                    "WHERE conversation_id = %s ORDER BY id DESC LIMIT 1",
                    (conv,),
                )
                last = await cur.fetchone()
                await cur.execute(
                    "SELECT COUNT(*) AS cnt FROM chat_messages "
                    "WHERE conversation_id = %s AND sender = 'practitioner' "
                    "AND read_at IS NULL",
                    (conv,),
                )
                unread_row = await cur.fetchone()
                out.append({
                    "patient_username": patient_username,
                    "practitioner_id": pid,
                    "conversation_id": conv,
                    "last_message": _msg_row_to_dict(last) if last else None,
                    "unread_count": unread_row["cnt"] if unread_row else 0,
                })
    return out


# ---------------------------------------------------------------------------
# Short-lived WebSocket tokens (practitioner browser -> FastAPI socket)
# ---------------------------------------------------------------------------
async def create_ws_token(practitioner_id: int) -> tuple[str, int]:
    """Mint a single-use WS token for a practitioner. Returns (token, ttl)."""
    token = secrets.token_urlsafe(32)
    await execute(
        "INSERT INTO ws_tokens (token, practitioner_id, created_at, used) "
        "VALUES (%s, %s, %s, FALSE)",
        (token, practitioner_id, now()),
    )
    return token, WS_TOKEN_TTL


async def consume_ws_token(token: str) -> int | None:
    """Verify the token is valid, unused, and within TTL. If so, mark it used
    and return the practitioner_id; otherwise return None."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT practitioner_id, created_at, used FROM ws_tokens "
                "WHERE token = %s",
                (token,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            pid = row["practitioner_id"]
            created_at = row["created_at"]
            used = row["used"]
            if used:
                return None
            # TTL check. created_at is a timezone-aware datetime from
            # TIMESTAMPTZ; if it's somehow a string, parse it.
            if isinstance(created_at, str):
                try:
                    created_dt = datetime.fromisoformat(created_at)
                except (ValueError, TypeError):
                    return None
            else:
                created_dt = created_at
            # Ensure timezone-aware for comparison.
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - created_dt).total_seconds()
            if age > WS_TOKEN_TTL:
                await cur.execute("DELETE FROM ws_tokens WHERE token = %s", (token,))
                return None
            await cur.execute(
                "UPDATE ws_tokens SET used = TRUE WHERE token = %s", (token,)
            )
            return pid
