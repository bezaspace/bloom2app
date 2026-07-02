"""SQLite-backed store for patient <-> practitioner text chat messages.

Mirrors the sync-function + async-wrapper pattern used in ``database.py`` and
``practitioner_db.py``. Shares the same ``auth.db`` file and the same ``_lock``
so writes are serialized across all stores.

Tables (created in ``_init_chat_db_sync``, called from
``database._init_db_sync``):
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

import asyncio
import secrets
import sqlite3
from datetime import datetime, timezone

from app.database import DB_PATH, _lock, _now


# Short-lived WS token validity, in seconds.
WS_TOKEN_TTL = 60


def _conversation_id(practitioner_id: int, patient_username: str) -> str:
    return f"{practitioner_id}:{patient_username}"


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------
def _init_chat_db_sync() -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                practitioner_id INTEGER NOT NULL,
                patient_username TEXT NOT NULL,
                sender TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                read_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_conv_id "
            "ON chat_messages (conversation_id, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_practitioner "
            "ON chat_messages (practitioner_id, patient_username, id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_patient "
            "ON chat_messages (patient_username, id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ws_tokens (
                token TEXT PRIMARY KEY,
                practitioner_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                used INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Message row helper
# ---------------------------------------------------------------------------
_MSG_COLS = (
    "id", "conversation_id", "practitioner_id", "patient_username",
    "sender", "body", "created_at", "read_at",
)


def _msg_row_to_dict(row: tuple) -> dict:
    d = dict(zip(_MSG_COLS, row))
    return d


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------
def _save_message_sync(
    practitioner_id: int,
    patient_username: str,
    sender: str,
    body: str,
) -> dict:
    conv = _conversation_id(practitioner_id, patient_username)
    now = _now()
    with _lock, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO chat_messages
                (conversation_id, practitioner_id, patient_username,
                 sender, body, created_at, read_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL)
            """,
            (conv, practitioner_id, patient_username, sender, body, now),
        )
        conn.commit()
        mid = cur.lastrowid
        row = conn.execute(
            f"SELECT {', '.join(_MSG_COLS)} FROM chat_messages WHERE id = ?",
            (mid,),
        ).fetchone()
    return _msg_row_to_dict(row)


def _list_messages_sync(
    conversation_id: str,
    before_id: int | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return messages oldest-first for a conversation, optionally limited to
    those with id < before_id (cursor pagination for "load older")."""
    limit = max(1, min(limit, 200))
    if before_id is not None:
        query = (
            f"SELECT {', '.join(_MSG_COLS)} FROM chat_messages "
            "WHERE conversation_id = ? AND id < ? "
            "ORDER BY id DESC LIMIT ?"
        )
        params: tuple = (conversation_id, before_id, limit)
    else:
        query = (
            f"SELECT {', '.join(_MSG_COLS)} FROM chat_messages "
            "WHERE conversation_id = ? "
            "ORDER BY id DESC LIMIT ?"
        )
        params = (conversation_id, limit)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(query, params).fetchall()
    # rows come newest-first; reverse for chronological display.
    return [_msg_row_to_dict(r) for r in reversed(rows)]


def _mark_read_sync(
    conversation_id: str, reader: str
) -> int:
    """Mark all messages in the conversation sent by the *other* party as read.
    ``reader`` is "patient" or "practitioner". Returns the number of rows
    updated."""
    other = "practitioner" if reader == "patient" else "patient"
    now = _now()
    with _lock, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "UPDATE chat_messages SET read_at = ? "
            "WHERE conversation_id = ? AND sender = ? AND read_at IS NULL",
            (now, conversation_id, other),
        )
        conn.commit()
        return cur.rowcount


def _unread_count_sync(
    conversation_id: str, reader: str
) -> int:
    """Count messages from the other party that are unread by ``reader``."""
    other = "practitioner" if reader == "patient" else "patient"
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM chat_messages "
            "WHERE conversation_id = ? AND sender = ? AND read_at IS NULL",
            (conversation_id, other),
        ).fetchone()
    return row[0] if row else 0


def _list_conversations_for_practitioner_sync(
    practitioner_id: int,
) -> list[dict]:
    """One row per patient the practitioner has chatted with, with the latest
    message preview and an unread count for the practitioner."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        # Distinct patients in this practitioner's conversations.
        rows = conn.execute(
            "SELECT DISTINCT patient_username FROM chat_messages "
            "WHERE practitioner_id = ?",
            (practitioner_id,),
        ).fetchall()
        out = []
        for (uname,) in rows:
            conv = _conversation_id(practitioner_id, uname)
            last = conn.execute(
                f"SELECT {', '.join(_MSG_COLS)} FROM chat_messages "
                "WHERE conversation_id = ? ORDER BY id DESC LIMIT 1",
                (conv,),
            ).fetchone()
            unread = conn.execute(
                "SELECT COUNT(*) FROM chat_messages "
                "WHERE conversation_id = ? AND sender = 'patient' "
                "AND read_at IS NULL",
                (conv,),
            ).fetchone()[0]
            out.append({
                "patient_username": uname,
                "practitioner_id": practitioner_id,
                "conversation_id": conv,
                "last_message": _msg_row_to_dict(last) if last else None,
                "unread_count": unread,
            })
    return out


def _list_conversations_for_patient_sync(
    patient_username: str,
) -> list[dict]:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT DISTINCT practitioner_id FROM chat_messages "
            "WHERE patient_username = ?",
            (patient_username,),
        ).fetchall()
        out = []
        for (pid,) in rows:
            conv = _conversation_id(pid, patient_username)
            last = conn.execute(
                f"SELECT {', '.join(_MSG_COLS)} FROM chat_messages "
                "WHERE conversation_id = ? ORDER BY id DESC LIMIT 1",
                (conv,),
            ).fetchone()
            unread = conn.execute(
                "SELECT COUNT(*) FROM chat_messages "
                "WHERE conversation_id = ? AND sender = 'practitioner' "
                "AND read_at IS NULL",
                (conv,),
            ).fetchone()[0]
            out.append({
                "patient_username": patient_username,
                "practitioner_id": pid,
                "conversation_id": conv,
                "last_message": _msg_row_to_dict(last) if last else None,
                "unread_count": unread,
            })
    return out


# ---------------------------------------------------------------------------
# Short-lived WebSocket tokens (practitioner browser -> FastAPI socket)
# ---------------------------------------------------------------------------
def _create_ws_token_sync(practitioner_id: int) -> tuple[str, int]:
    """Mint a single-use WS token for a practitioner. Returns (token, ttl)."""
    token = secrets.token_urlsafe(32)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO ws_tokens (token, practitioner_id, created_at, used) "
            "VALUES (?, ?, ?, 0)",
            (token, practitioner_id, _now()),
        )
        conn.commit()
    return token, WS_TOKEN_TTL


def _consume_ws_token_sync(token: str) -> int | None:
    """Verify the token is valid, unused, and within TTL. If so, mark it used
    and return the practitioner_id; otherwise return None."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT practitioner_id, created_at, used FROM ws_tokens "
            "WHERE token = ?",
            (token,),
        ).fetchone()
        if not row:
            return None
        pid, created_at, used = row
        if used:
            return None
        # TTL check.
        try:
            created_dt = datetime.fromisoformat(created_at)
            age = (datetime.now(timezone.utc) - created_dt).total_seconds()
        except (ValueError, TypeError):
            return None
        if age > WS_TOKEN_TTL:
            conn.execute("DELETE FROM ws_tokens WHERE token = ?", (token,))
            conn.commit()
            return None
        conn.execute(
            "UPDATE ws_tokens SET used = 1 WHERE token = ?", (token,)
        )
        conn.commit()
        return pid


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------
async def save_message(
    practitioner_id: int, patient_username: str, sender: str, body: str
) -> dict:
    return await asyncio.to_thread(
        _save_message_sync, practitioner_id, patient_username, sender, body
    )


async def list_messages(
    conversation_id: str, before_id: int | None = None, limit: int = 50
) -> list[dict]:
    return await asyncio.to_thread(
        _list_messages_sync, conversation_id, before_id, limit
    )


async def mark_read(conversation_id: str, reader: str) -> int:
    return await asyncio.to_thread(_mark_read_sync, conversation_id, reader)


async def unread_count(conversation_id: str, reader: str) -> int:
    return await asyncio.to_thread(_unread_count_sync, conversation_id, reader)


async def list_conversations_for_practitioner(
    practitioner_id: int,
) -> list[dict]:
    return await asyncio.to_thread(
        _list_conversations_for_practitioner_sync, practitioner_id
    )


async def list_conversations_for_patient(
    patient_username: str,
) -> list[dict]:
    return await asyncio.to_thread(
        _list_conversations_for_patient_sync, patient_username
    )


async def create_ws_token(practitioner_id: int) -> tuple[str, int]:
    return await asyncio.to_thread(_create_ws_token_sync, practitioner_id)


async def consume_ws_token(token: str) -> int | None:
    return await asyncio.to_thread(_consume_ws_token_sync, token)
