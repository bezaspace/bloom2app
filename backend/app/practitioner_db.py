"""SQLite-backed store for practitioner accounts, appointments, and connections.

Mirrors the sync-function + async-wrapper pattern used in ``database.py``.
Shares the same ``auth.db`` file and the same ``_lock`` so writes are
serialized across the patient and practitioner stores.

Tables (created in ``_init_practitioner_db_sync``, called from
``database._init_db_sync``):
  - practitioners
  - practitioner_tokens
  - appointments
  - practitioner_patient_connections
  - practitioner_notes
"""

import asyncio
import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timezone

from app.database import DB_PATH, _lock, _now


# ---------------------------------------------------------------------------
# Password hashing (same scheme as patient auth)
# ---------------------------------------------------------------------------
def _make_salt() -> bytes:
    return os.urandom(32)


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000).hex()


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------
def _init_practitioner_db_sync() -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS practitioners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                full_name TEXT NOT NULL,
                title TEXT,
                specialization TEXT,
                bio TEXT,
                email TEXT,
                phone TEXT,
                years_experience INTEGER,
                consultation_fee REAL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS practitioner_tokens (
                token TEXT PRIMARY KEY,
                practitioner_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_username TEXT NOT NULL,
                practitioner_id INTEGER NOT NULL,
                requested_date TEXT NOT NULL,
                requested_time TEXT,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                patient_note TEXT,
                practitioner_note TEXT,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                completed_at TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_appointments_patient "
            "ON appointments (patient_username, status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_appointments_practitioner "
            "ON appointments (practitioner_id, status)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS practitioner_patient_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                practitioner_id INTEGER NOT NULL,
                patient_username TEXT NOT NULL,
                established_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                ai_summary TEXT,
                ai_summary_generated_at TEXT,
                UNIQUE(practitioner_id, patient_username)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS practitioner_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                practitioner_id INTEGER NOT NULL,
                patient_username TEXT NOT NULL,
                note_text TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_practitioner_notes "
            "ON practitioner_notes (practitioner_id, patient_username, created_at)"
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Practitioner accounts
# ---------------------------------------------------------------------------
def _practitioner_row_to_dict(row: sqlite3.Row | tuple) -> dict:
    cols = (
        "id", "username", "password_hash", "salt", "full_name", "title",
        "specialization", "bio", "email", "phone", "years_experience",
        "consultation_fee", "is_active", "created_at",
    )
    return dict(zip(cols, row))


def _public_practitioner(p: dict) -> dict:
    """Strip sensitive fields for API responses."""
    return {
        "id": p["id"],
        "username": p["username"],
        "full_name": p["full_name"],
        "title": p["title"],
        "specialization": p["specialization"],
        "bio": p["bio"],
        "email": p["email"],
        "phone": p["phone"],
        "years_experience": p["years_experience"],
        "consultation_fee": p["consultation_fee"],
        "is_active": bool(p["is_active"]),
        "created_at": p["created_at"],
    }


def _register_practitioner_sync(data: dict) -> dict | None:
    """Insert a practitioner. Returns the new row (without secrets) or None
    if the username is taken."""
    salt = _make_salt()
    password_hash = _hash_password(data["password"], salt)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO practitioners
                    (username, password_hash, salt, full_name, title,
                     specialization, bio, email, phone, years_experience,
                     consultation_fee, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    data["username"],
                    password_hash,
                    salt.hex(),
                    data["full_name"],
                    data.get("title"),
                    data.get("specialization"),
                    data.get("bio"),
                    data.get("email"),
                    data.get("phone"),
                    data.get("years_experience"),
                    data.get("consultation_fee"),
                    _now(),
                ),
            )
            conn.commit()
            pid = cur.lastrowid
        except sqlite3.IntegrityError:
            return None
    return _public_practitioner(_get_practitioner_by_id_sync(pid))


def _verify_practitioner_sync(username: str, password: str) -> dict | None:
    """Return the practitioner dict (with id) if credentials match, else None."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, salt, is_active "
            "FROM practitioners WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    pid, uname, stored_hash, salt_hex, is_active = row
    if not bool(is_active):
        return None
    if stored_hash != _hash_password(password, bytes.fromhex(salt_hex)):
        return None
    return {"id": pid, "username": uname}


def _get_practitioner_by_id_sync(pid: int) -> dict | None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, salt, full_name, title, "
            "specialization, bio, email, phone, years_experience, "
            "consultation_fee, is_active, created_at "
            "FROM practitioners WHERE id = ?",
            (pid,),
        ).fetchone()
    if not row:
        return None
    return _practitioner_row_to_dict(row)


def _get_practitioner_by_username_sync(username: str) -> dict | None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, salt, full_name, title, "
            "specialization, bio, email, phone, years_experience, "
            "consultation_fee, is_active, created_at "
            "FROM practitioners WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    return _practitioner_row_to_dict(row)


def _list_active_practitioners_sync(
    search: str | None = None, specialization: str | None = None
) -> list[dict]:
    """Return all active practitioners, optionally filtered. Public view."""
    clauses = ["is_active = 1"]
    params: list = []
    if search:
        clauses.append(
            "(full_name LIKE ? OR specialization LIKE ? OR bio LIKE ?)"
        )
        like = f"%{search}%"
        params.extend([like, like, like])
    if specialization:
        clauses.append("specialization LIKE ?")
        params.append(f"%{specialization}%")
    where = " AND ".join(clauses)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            f"SELECT id, username, password_hash, salt, full_name, title, "
            f"specialization, bio, email, phone, years_experience, "
            f"consultation_fee, is_active, created_at "
            f"FROM practitioners WHERE {where} "
            f"ORDER BY full_name ASC",
            params,
        ).fetchall()
    return [_public_practitioner(_practitioner_row_to_dict(r)) for r in rows]


def _update_practitioner_profile_sync(pid: int, updates: dict) -> dict | None:
    """Update editable profile fields. Returns the updated public dict."""
    allowed = (
        "full_name", "title", "specialization", "bio", "email", "phone",
        "years_experience", "consultation_fee",
    )
    sets = []
    params: list = []
    for k in allowed:
        if k in updates:
            sets.append(f"{k} = ?")
            params.append(updates[k])
    if not sets:
        return _public_practitioner(_get_practitioner_by_id_sync(pid))
    params.append(pid)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            f"UPDATE practitioners SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        conn.commit()
    return _public_practitioner(_get_practitioner_by_id_sync(pid))


# ---------------------------------------------------------------------------
# Practitioner tokens
# ---------------------------------------------------------------------------
def _create_practitioner_token_sync(pid: int) -> str:
    token = secrets.token_urlsafe(32)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO practitioner_tokens (token, practitioner_id, created_at) "
            "VALUES (?, ?, ?)",
            (token, pid, _now()),
        )
        conn.commit()
    return token


def _get_practitioner_by_token_sync(token: str) -> dict | None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT p.id, p.username, p.password_hash, p.salt, p.full_name, "
            "p.title, p.specialization, p.bio, p.email, p.phone, "
            "p.years_experience, p.consultation_fee, p.is_active, p.created_at "
            "FROM practitioner_tokens t JOIN practitioners p "
            "ON t.practitioner_id = p.id WHERE t.token = ?",
            (token,),
        ).fetchone()
    if not row:
        return None
    p = _practitioner_row_to_dict(row)
    if not p["is_active"]:
        return None
    return p


def _delete_practitioner_token_sync(token: str) -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM practitioner_tokens WHERE token = ?", (token,))
        conn.commit()


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------
def _appointment_row_to_dict(row: tuple) -> dict:
    cols = (
        "id", "patient_username", "practitioner_id", "requested_date",
        "requested_time", "reason", "status", "patient_note",
        "practitioner_note", "created_at", "decided_at", "completed_at",
    )
    return dict(zip(cols, row))


def _create_appointment_sync(data: dict) -> dict:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """
            INSERT INTO appointments
                (patient_username, practitioner_id, requested_date,
                 requested_time, reason, status, patient_note, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
            """,
            (
                data["patient_username"],
                data["practitioner_id"],
                data["requested_date"],
                data.get("requested_time"),
                data.get("reason"),
                data.get("patient_note"),
                _now(),
            ),
        )
        conn.commit()
        aid = cur.lastrowid
        row = conn.execute(
            "SELECT id, patient_username, practitioner_id, requested_date, "
            "requested_time, reason, status, patient_note, practitioner_note, "
            "created_at, decided_at, completed_at FROM appointments WHERE id = ?",
            (aid,),
        ).fetchone()
    return _appointment_row_to_dict(row)


def _get_appointment_sync(aid: int) -> dict | None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, patient_username, practitioner_id, requested_date, "
            "requested_time, reason, status, patient_note, practitioner_note, "
            "created_at, decided_at, completed_at FROM appointments WHERE id = ?",
            (aid,),
        ).fetchone()
    return _appointment_row_to_dict(row) if row else None


def _list_appointments_for_patient_sync(username: str) -> list[dict]:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, patient_username, practitioner_id, requested_date, "
            "requested_time, reason, status, patient_note, practitioner_note, "
            "created_at, decided_at, completed_at FROM appointments "
            "WHERE patient_username = ? ORDER BY created_at DESC",
            (username,),
        ).fetchall()
    return [_appointment_row_to_dict(r) for r in rows]


def _list_appointments_for_practitioner_sync(
    pid: int, status: str | None = None
) -> list[dict]:
    if status:
        query = (
            "SELECT id, patient_username, practitioner_id, requested_date, "
            "requested_time, reason, status, patient_note, practitioner_note, "
            "created_at, decided_at, completed_at FROM appointments "
            "WHERE practitioner_id = ? AND status = ? ORDER BY created_at DESC"
        )
        params: tuple = (pid, status)
    else:
        query = (
            "SELECT id, patient_username, practitioner_id, requested_date, "
            "requested_time, reason, status, patient_note, practitioner_note, "
            "created_at, decided_at, completed_at FROM appointments "
            "WHERE practitioner_id = ? ORDER BY created_at DESC"
        )
        params = (pid,)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_appointment_row_to_dict(r) for r in rows]


def _set_appointment_status_sync(
    aid: int, status: str, practitioner_note: str | None = None
) -> dict | None:
    """Transition an appointment to a new status. Sets decided_at for
    accept/decline and completed_at for complete. Returns the updated row."""
    appt = _get_appointment_sync(aid)
    if not appt:
        return None
    now = _now()
    sets = ["status = ?"]
    params: list = [status]
    if status in ("accepted", "declined"):
        sets.append("decided_at = ?")
        params.append(now)
    if status == "completed":
        sets.append("completed_at = ?")
        params.append(now)
    if practitioner_note is not None:
        sets.append("practitioner_note = ?")
        params.append(practitioner_note)
    params.append(aid)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            f"UPDATE appointments SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        conn.commit()
    return _get_appointment_sync(aid)


# ---------------------------------------------------------------------------
# Practitioner-patient connections
# ---------------------------------------------------------------------------
def _ensure_connection_sync(pid: int, patient_username: str) -> None:
    """Create a connection if it doesn't already exist (idempotent)."""
    now = _now()
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO practitioner_patient_connections
                (practitioner_id, patient_username, established_at, status)
            VALUES (?, ?, ?, 'active')
            ON CONFLICT(practitioner_id, patient_username) DO UPDATE SET
                status = 'active'
            """,
            (pid, patient_username, now),
        )
        conn.commit()


def _has_connection_sync(pid: int, patient_username: str) -> bool:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM practitioner_patient_connections "
            "WHERE practitioner_id = ? AND patient_username = ? AND status = 'active'",
            (pid, patient_username),
        ).fetchone()
    return row is not None


def _list_connections_for_practitioner_sync(pid: int) -> list[dict]:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, practitioner_id, patient_username, established_at, "
            "status, ai_summary, ai_summary_generated_at "
            "FROM practitioner_patient_connections "
            "WHERE practitioner_id = ? AND status = 'active' "
            "ORDER BY established_at DESC",
            (pid,),
        ).fetchall()
    cols = (
        "id", "practitioner_id", "patient_username", "established_at",
        "status", "ai_summary", "ai_summary_generated_at",
    )
    return [dict(zip(cols, r)) for r in rows]


def _get_connection_sync(pid: int, patient_username: str) -> dict | None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, practitioner_id, patient_username, established_at, "
            "status, ai_summary, ai_summary_generated_at "
            "FROM practitioner_patient_connections "
            "WHERE practitioner_id = ? AND patient_username = ?",
            (pid, patient_username),
        ).fetchone()
    if not row:
        return None
    cols = (
        "id", "practitioner_id", "patient_username", "established_at",
        "status", "ai_summary", "ai_summary_generated_at",
    )
    return dict(zip(cols, row))


def _save_ai_summary_sync(
    pid: int, patient_username: str, summary_json: str
) -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE practitioner_patient_connections
            SET ai_summary = ?, ai_summary_generated_at = ?
            WHERE practitioner_id = ? AND patient_username = ?
            """,
            (summary_json, _now(), pid, patient_username),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Practitioner notes
# ---------------------------------------------------------------------------
def _add_note_sync(pid: int, patient_username: str, note_text: str) -> dict:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO practitioner_notes "
            "(practitioner_id, patient_username, note_text, created_at) "
            "VALUES (?, ?, ?, ?)",
            (pid, patient_username, note_text, _now()),
        )
        conn.commit()
        nid = cur.lastrowid
    return {
        "id": nid,
        "practitioner_id": pid,
        "patient_username": patient_username,
        "note_text": note_text,
        "created_at": _now(),
    }


def _list_notes_sync(pid: int, patient_username: str) -> list[dict]:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, practitioner_id, patient_username, note_text, created_at "
            "FROM practitioner_notes "
            "WHERE practitioner_id = ? AND patient_username = ? "
            "ORDER BY created_at DESC",
            (pid, patient_username),
        ).fetchall()
    cols = ("id", "practitioner_id", "patient_username", "note_text", "created_at")
    return [dict(zip(cols, r)) for r in rows]


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------
async def register_practitioner(data: dict) -> dict | None:
    return await asyncio.to_thread(_register_practitioner_sync, data)


async def verify_practitioner(username: str, password: str) -> dict | None:
    return await asyncio.to_thread(_verify_practitioner_sync, username, password)


async def get_practitioner_by_id(pid: int) -> dict | None:
    p = await asyncio.to_thread(_get_practitioner_by_id_sync, pid)
    return _public_practitioner(p) if p else None


async def get_practitioner_by_username(username: str) -> dict | None:
    return await asyncio.to_thread(_get_practitioner_by_username_sync, username)


async def list_active_practitioners(
    search: str | None = None, specialization: str | None = None
) -> list[dict]:
    return await asyncio.to_thread(
        _list_active_practitioners_sync, search, specialization
    )


async def update_practitioner_profile(pid: int, updates: dict) -> dict | None:
    return await asyncio.to_thread(_update_practitioner_profile_sync, pid, updates)


async def create_practitioner_token(pid: int) -> str:
    return await asyncio.to_thread(_create_practitioner_token_sync, pid)


async def get_practitioner_by_token(token: str) -> dict | None:
    return await asyncio.to_thread(_get_practitioner_by_token_sync, token)


async def delete_practitioner_token(token: str) -> None:
    await asyncio.to_thread(_delete_practitioner_token_sync, token)


async def create_appointment(data: dict) -> dict:
    return await asyncio.to_thread(_create_appointment_sync, data)


async def get_appointment(aid: int) -> dict | None:
    return await asyncio.to_thread(_get_appointment_sync, aid)


async def list_appointments_for_patient(username: str) -> list[dict]:
    return await asyncio.to_thread(_list_appointments_for_patient_sync, username)


async def list_appointments_for_practitioner(
    pid: int, status: str | None = None
) -> list[dict]:
    return await asyncio.to_thread(
        _list_appointments_for_practitioner_sync, pid, status
    )


async def set_appointment_status(
    aid: int, status: str, practitioner_note: str | None = None
) -> dict | None:
    return await asyncio.to_thread(
        _set_appointment_status_sync, aid, status, practitioner_note
    )


async def ensure_connection(pid: int, patient_username: str) -> None:
    await asyncio.to_thread(_ensure_connection_sync, pid, patient_username)


async def has_connection(pid: int, patient_username: str) -> bool:
    return await asyncio.to_thread(_has_connection_sync, pid, patient_username)


async def list_connections_for_practitioner(pid: int) -> list[dict]:
    return await asyncio.to_thread(_list_connections_for_practitioner_sync, pid)


async def get_connection(pid: int, patient_username: str) -> dict | None:
    return await asyncio.to_thread(_get_connection_sync, pid, patient_username)


async def save_ai_summary(
    pid: int, patient_username: str, summary_json: str
) -> None:
    await asyncio.to_thread(
        _save_ai_summary_sync, pid, patient_username, summary_json
    )


async def add_note(pid: int, patient_username: str, note_text: str) -> dict:
    return await asyncio.to_thread(
        _add_note_sync, pid, patient_username, note_text
    )


async def list_notes(pid: int, patient_username: str) -> list[dict]:
    return await asyncio.to_thread(_list_notes_sync, pid, patient_username)
