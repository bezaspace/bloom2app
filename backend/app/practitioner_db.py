"""PostgreSQL-backed store for practitioner accounts, appointments, and connections.

Uses ``psycopg3`` (async) via the shared connection pool in ``app.db``.
Replaces the old SQLite + threading.Lock pattern.
"""

from __future__ import annotations

import hashlib
import os
import secrets

from app.db import execute, fetchall, fetchone, get_conn, now


# ---------------------------------------------------------------------------
# Password hashing (same scheme as patient auth)
# ---------------------------------------------------------------------------
def _make_salt() -> bytes:
    return os.urandom(32)


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000).hex()


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------
_PRACTITIONER_COLS = (
    "id", "username", "password_hash", "salt", "full_name", "title",
    "specialization", "bio", "email", "phone", "years_experience",
    "consultation_fee", "is_active", "created_at",
)


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


def _get_practitioner_row(row: dict) -> dict:
    """Convert a fetched row dict to the full practitioner dict."""
    return {col: row.get(col) for col in _PRACTITIONER_COLS}


_APPOINTMENT_COLS = (
    "id", "patient_username", "practitioner_id", "requested_date",
    "requested_time", "reason", "status", "patient_note",
    "practitioner_note", "created_at", "decided_at", "completed_at",
)


def _appointment_row_to_dict(row: dict) -> dict:
    return {col: row.get(col) for col in _APPOINTMENT_COLS}


_CONNECTION_COLS = (
    "id", "practitioner_id", "patient_username", "established_at",
    "status", "ai_summary", "ai_summary_generated_at",
)


# ---------------------------------------------------------------------------
# Practitioner accounts
# ---------------------------------------------------------------------------
async def register_practitioner(data: dict) -> dict | None:
    """Insert a practitioner. Returns the new row (without secrets) or None
    if the username is taken."""
    salt = _make_salt()
    password_hash = _hash_password(data["password"], salt)
    try:
        row = await fetchone(
            """
            INSERT INTO practitioners
                (username, password_hash, salt, full_name, title,
                 specialization, bio, email, phone, years_experience,
                 consultation_fee, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s)
            RETURNING id
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
                now(),
            ),
        )
    except Exception:  # noqa: BLE001 — unique constraint violation
        return None
    return _public_practitioner(await get_practitioner_by_id(row["id"]))


async def verify_practitioner(username: str, password: str) -> dict | None:
    """Return the practitioner dict (with id) if credentials match, else None."""
    row = await fetchone(
        "SELECT id, username, password_hash, salt, is_active "
        "FROM practitioners WHERE username = %s",
        (username,),
    )
    if not row:
        return None
    if not bool(row["is_active"]):
        return None
    if row["password_hash"] != _hash_password(password, bytes.fromhex(row["salt"])):
        return None
    return {"id": row["id"], "username": row["username"]}


async def _get_practitioner_by_id_sync(pid: int) -> dict | None:
    """Internal: return the full practitioner dict (with secrets). Used by
    other functions that need to call _public_practitioner."""
    row = await fetchone(
        "SELECT id, username, password_hash, salt, full_name, title, "
        "specialization, bio, email, phone, years_experience, "
        "consultation_fee, is_active, created_at "
        "FROM practitioners WHERE id = %s",
        (pid,),
    )
    return _get_practitioner_row(row) if row else None


async def get_practitioner_by_id(pid: int) -> dict | None:
    p = await _get_practitioner_by_id_sync(pid)
    return _public_practitioner(p) if p else None


async def get_practitioner_by_username(username: str) -> dict | None:
    """Return the full practitioner dict (with secrets) — used internally."""
    row = await fetchone(
        "SELECT id, username, password_hash, salt, full_name, title, "
        "specialization, bio, email, phone, years_experience, "
        "consultation_fee, is_active, created_at "
        "FROM practitioners WHERE username = %s",
        (username,),
    )
    if not row:
        return None
    # Return the public version for external callers. Internal callers that
    # need secrets should use the raw row directly.
    return _public_practitioner(_get_practitioner_row(row))


async def list_active_practitioners(
    search: str | None = None, specialization: str | None = None
) -> list[dict]:
    """Return all active practitioners, optionally filtered. Public view."""
    clauses = ["is_active = TRUE"]
    params: list = []
    if search:
        clauses.append(
            "(full_name ILIKE %s OR specialization ILIKE %s OR bio ILIKE %s)"
        )
        like = f"%{search}%"
        params.extend([like, like, like])
    if specialization:
        clauses.append("specialization ILIKE %s")
        params.append(f"%{specialization}%")
    where = " AND ".join(clauses)
    rows = await fetchall(
        f"SELECT id, username, password_hash, salt, full_name, title, "
        f"specialization, bio, email, phone, years_experience, "
        f"consultation_fee, is_active, created_at "
        f"FROM practitioners WHERE {where} "
        f"ORDER BY full_name ASC",
        tuple(params),
    )
    return [_public_practitioner(_get_practitioner_row(r)) for r in rows]


async def update_practitioner_profile(pid: int, updates: dict) -> dict | None:
    """Update editable profile fields. Returns the updated public dict."""
    allowed = (
        "full_name", "title", "specialization", "bio", "email", "phone",
        "years_experience", "consultation_fee",
    )
    sets = []
    params: list = []
    for k in allowed:
        if k in updates:
            sets.append(f"{k} = %s")
            params.append(updates[k])
    if not sets:
        return await get_practitioner_by_id(pid)
    params.append(pid)
    await execute(
        f"UPDATE practitioners SET {', '.join(sets)} WHERE id = %s",
        tuple(params),
    )
    return await get_practitioner_by_id(pid)


# ---------------------------------------------------------------------------
# Practitioner tokens
# ---------------------------------------------------------------------------
async def create_practitioner_token(pid: int) -> str:
    token = secrets.token_urlsafe(32)
    await execute(
        "INSERT INTO practitioner_tokens (token, practitioner_id, created_at) "
        "VALUES (%s, %s, %s)",
        (token, pid, now()),
    )
    return token


async def get_practitioner_by_token(token: str) -> dict | None:
    """Return the full practitioner dict (with secrets) if the token is valid."""
    row = await fetchone(
        "SELECT p.id, p.username, p.password_hash, p.salt, p.full_name, "
        "p.title, p.specialization, p.bio, p.email, p.phone, "
        "p.years_experience, p.consultation_fee, p.is_active, p.created_at "
        "FROM practitioner_tokens t JOIN practitioners p "
        "ON t.practitioner_id = p.id WHERE t.token = %s",
        (token,),
    )
    if not row:
        return None
    p = _get_practitioner_row(row)
    if not p["is_active"]:
        return None
    return p


async def delete_practitioner_token(token: str) -> None:
    await execute("DELETE FROM practitioner_tokens WHERE token = %s", (token,))


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------
async def create_appointment(data: dict) -> dict:
    row = await fetchone(
        """
        INSERT INTO appointments
            (patient_username, practitioner_id, requested_date,
             requested_time, reason, status, patient_note, created_at)
        VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)
        RETURNING id, patient_username, practitioner_id, requested_date,
            requested_time, reason, status, patient_note,
            practitioner_note, created_at, decided_at, completed_at
        """,
        (
            data["patient_username"],
            data["practitioner_id"],
            data["requested_date"],
            data.get("requested_time"),
            data.get("reason"),
            data.get("patient_note"),
            now(),
        ),
    )
    return _appointment_row_to_dict(row)


async def get_appointment(aid: int) -> dict | None:
    row = await fetchone(
        "SELECT id, patient_username, practitioner_id, requested_date, "
        "requested_time, reason, status, patient_note, practitioner_note, "
        "created_at, decided_at, completed_at FROM appointments WHERE id = %s",
        (aid,),
    )
    return _appointment_row_to_dict(row) if row else None


async def list_appointments_for_patient(username: str) -> list[dict]:
    rows = await fetchall(
        "SELECT id, patient_username, practitioner_id, requested_date, "
        "requested_time, reason, status, patient_note, practitioner_note, "
        "created_at, decided_at, completed_at FROM appointments "
        "WHERE patient_username = %s ORDER BY created_at DESC",
        (username,),
    )
    return [_appointment_row_to_dict(r) for r in rows]


async def list_appointments_for_practitioner(
    pid: int, status: str | None = None
) -> list[dict]:
    if status:
        rows = await fetchall(
            "SELECT id, patient_username, practitioner_id, requested_date, "
            "requested_time, reason, status, patient_note, practitioner_note, "
            "created_at, decided_at, completed_at FROM appointments "
            "WHERE practitioner_id = %s AND status = %s ORDER BY created_at DESC",
            (pid, status),
        )
    else:
        rows = await fetchall(
            "SELECT id, patient_username, practitioner_id, requested_date, "
            "requested_time, reason, status, patient_note, practitioner_note, "
            "created_at, decided_at, completed_at FROM appointments "
            "WHERE practitioner_id = %s ORDER BY created_at DESC",
            (pid,),
        )
    return [_appointment_row_to_dict(r) for r in rows]


async def set_appointment_status(
    aid: int, status: str, practitioner_note: str | None = None
) -> dict | None:
    """Transition an appointment to a new status. Sets decided_at for
    accept/decline and completed_at for complete. Returns the updated row."""
    appt = await get_appointment(aid)
    if not appt:
        return None
    ts = now()
    sets = ["status = %s"]
    params: list = [status]
    if status in ("accepted", "declined"):
        sets.append("decided_at = %s")
        params.append(ts)
    if status == "completed":
        sets.append("completed_at = %s")
        params.append(ts)
    if practitioner_note is not None:
        sets.append("practitioner_note = %s")
        params.append(practitioner_note)
    params.append(aid)
    await execute(
        f"UPDATE appointments SET {', '.join(sets)} WHERE id = %s",
        tuple(params),
    )
    return await get_appointment(aid)


# ---------------------------------------------------------------------------
# Practitioner-patient connections
# ---------------------------------------------------------------------------
async def ensure_connection(pid: int, patient_username: str) -> None:
    """Create a connection if it doesn't already exist (idempotent)."""
    await execute(
        """
        INSERT INTO practitioner_patient_connections
            (practitioner_id, patient_username, established_at, status)
        VALUES (%s, %s, %s, 'active')
        ON CONFLICT(practitioner_id, patient_username) DO UPDATE SET
            status = 'active'
        """,
        (pid, patient_username, now()),
    )


async def has_connection(pid: int, patient_username: str) -> bool:
    row = await fetchone(
        "SELECT 1 FROM practitioner_patient_connections "
        "WHERE practitioner_id = %s AND patient_username = %s AND status = 'active'",
        (pid, patient_username),
    )
    return row is not None


async def list_connections_for_practitioner(pid: int) -> list[dict]:
    rows = await fetchall(
        "SELECT id, practitioner_id, patient_username, established_at, "
        "status, ai_summary, ai_summary_generated_at "
        "FROM practitioner_patient_connections "
        "WHERE practitioner_id = %s AND status = 'active' "
        "ORDER BY established_at DESC",
        (pid,),
    )
    return [{col: r.get(col) for col in _CONNECTION_COLS} for r in rows]


async def get_connection(pid: int, patient_username: str) -> dict | None:
    row = await fetchone(
        "SELECT id, practitioner_id, patient_username, established_at, "
        "status, ai_summary, ai_summary_generated_at "
        "FROM practitioner_patient_connections "
        "WHERE practitioner_id = %s AND patient_username = %s",
        (pid, patient_username),
    )
    if not row:
        return None
    return {col: row.get(col) for col in _CONNECTION_COLS}


async def save_ai_summary(
    pid: int, patient_username: str, summary_json: str
) -> None:
    await execute(
        """
        UPDATE practitioner_patient_connections
        SET ai_summary = %s, ai_summary_generated_at = %s
        WHERE practitioner_id = %s AND patient_username = %s
        """,
        (summary_json, now(), pid, patient_username),
    )


# ---------------------------------------------------------------------------
# Practitioner notes
# ---------------------------------------------------------------------------
async def add_note(pid: int, patient_username: str, note_text: str) -> dict:
    row = await fetchone(
        "INSERT INTO practitioner_notes "
        "(practitioner_id, patient_username, note_text, created_at) "
        "VALUES (%s, %s, %s, %s) RETURNING id, created_at",
        (pid, patient_username, note_text, now()),
    )
    return {
        "id": row["id"],
        "practitioner_id": pid,
        "patient_username": patient_username,
        "note_text": note_text,
        "created_at": row["created_at"],
    }


async def list_notes(pid: int, patient_username: str) -> list[dict]:
    rows = await fetchall(
        "SELECT id, practitioner_id, patient_username, note_text, created_at "
        "FROM practitioner_notes "
        "WHERE practitioner_id = %s AND patient_username = %s "
        "ORDER BY created_at DESC",
        (pid, patient_username),
    )
    return rows
