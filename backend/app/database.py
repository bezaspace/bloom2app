"""PostgreSQL-backed user authentication store.

Uses ``psycopg3`` (async) via the shared connection pool in ``app.db``.
Replaces the old SQLite + threading.Lock pattern. All functions are async;
callers should ``await`` them directly.
"""

from __future__ import annotations

import hashlib
import os
import secrets

from app.db import (
    execute,
    fetchall,
    fetchone,
    get_conn,
    now,
    run_migrations,
)


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2 — same scheme as before)
# ---------------------------------------------------------------------------
def _make_salt() -> bytes:
    return os.urandom(32)


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000).hex()


def _biomarker_status(
    value: float, ref_low: float | None, ref_high: float | None
) -> str:
    """Classify a reading against its reference range."""
    if ref_low is not None and value < ref_low:
        return "low"
    if ref_high is not None and value > ref_high:
        return "high"
    if ref_low is not None and ref_high is not None:
        return "normal"
    return "unknown"


# ---------------------------------------------------------------------------
# Schema initialization (delegated to the migration runner)
# ---------------------------------------------------------------------------
async def init_db() -> None:
    """Run pending migrations. The schema is defined in backend/migrations/."""
    await run_migrations()


# ---------------------------------------------------------------------------
# User registration + token management
# ---------------------------------------------------------------------------
async def register_user(username: str, password: str) -> bool:
    """Register a new user. Returns True on success, False if username taken."""
    salt = _make_salt()
    password_hash = _hash_password(password, salt)
    try:
        await execute(
            "INSERT INTO users (username, password_hash, salt, created_at) "
            "VALUES (%s, %s, %s, %s)",
            (username, password_hash, salt.hex(), now()),
        )
        return True
    except Exception:  # noqa: BLE001 — unique constraint violation
        return False


async def verify_user(username: str, password: str) -> bool:
    row = await fetchone(
        "SELECT password_hash, salt FROM users WHERE username = %s",
        (username,),
    )
    if not row:
        return False
    return row["password_hash"] == _hash_password(
        password, bytes.fromhex(row["salt"])
    )


async def create_token(username: str) -> str:
    token = secrets.token_urlsafe(32)
    await execute(
        "INSERT INTO tokens (token, username, created_at) VALUES (%s, %s, %s)",
        (token, username, now()),
    )
    return token


async def get_user_by_token(token: str) -> str | None:
    row = await fetchone(
        "SELECT username FROM tokens WHERE token = %s", (token,)
    )
    return row["username"] if row else None


async def delete_token(token: str) -> None:
    await execute("DELETE FROM tokens WHERE token = %s", (token,))


# ---------------------------------------------------------------------------
# Onboarding profile + plan + document summary (per-user, persistent)
# ---------------------------------------------------------------------------
async def get_profile(username: str) -> dict | None:
    row = await fetchone(
        "SELECT profile_json, plan_json, doc_summary_json, onboarded, onboarded_at "
        "FROM user_profiles WHERE username = %s",
        (username,),
    )
    if not row:
        return None
    # onboarded_at is a TIMESTAMPTZ; psycopg returns a datetime. Convert to
    # ISO string for backward compat with callers that parse it as a string.
    o_at = row["onboarded_at"]
    if o_at is not None and not isinstance(o_at, str):
        o_at = o_at.isoformat()
    return {
        "profile": row["profile_json"],
        "plan": row["plan_json"],
        "doc_summary": row["doc_summary_json"],
        "onboarded": bool(row["onboarded"]),
        "onboarded_at": o_at,
    }


async def save_profile(
    username: str,
    profile_json: str,
    plan_json: str,
    doc_summary_json: str | None,
    onboarded: bool,
    onboarded_at: str | None = None,
) -> None:
    """Upsert the user's profile + plan + doc summary.

    On a fresh insert where onboarding is finalized and no ``onboarded_at``
    is given, set it to now(). On conflict, COALESCE preserves any existing
    timestamp so re-saving a doc_summary during onboarding doesn't clobber it.
    """
    # profile_json / plan_json arrive as JSON strings (the caller does
    # json.dumps). JSONB columns accept strings directly.
    ts = onboarded_at
    if onboarded and ts is None:
        # Check if a row already exists with a non-null onboarded_at.
        existing = await fetchone(
            "SELECT onboarded_at FROM user_profiles WHERE username = %s",
            (username,),
        )
        if not existing or not existing["onboarded_at"]:
            ts = now()
        else:
            ts = existing["onboarded_at"]

    await execute(
        """
        INSERT INTO user_profiles
            (username, profile_json, plan_json, doc_summary_json,
             onboarded, onboarded_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(username) DO UPDATE SET
            profile_json = EXCLUDED.profile_json,
            plan_json = EXCLUDED.plan_json,
            doc_summary_json = EXCLUDED.doc_summary_json,
            onboarded = EXCLUDED.onboarded,
            onboarded_at = COALESCE(EXCLUDED.onboarded_at, user_profiles.onboarded_at),
            updated_at = EXCLUDED.updated_at
        """,
        (username, profile_json, plan_json, doc_summary_json, onboarded, ts, now()),
    )


async def add_doc_record(username: str, filename: str, mime_type: str) -> int:
    """Insert a doc metadata row and return its id."""
    row = await fetchone(
        "INSERT INTO user_docs (username, filename, mime_type, uploaded_at) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (username, filename, mime_type, now()),
    )
    return row["id"]


async def list_docs(username: str) -> list[dict]:
    rows = await fetchall(
        "SELECT id, filename, mime_type, uploaded_at FROM user_docs "
        "WHERE username = %s ORDER BY uploaded_at DESC",
        (username,),
    )
    return rows


# ---------------------------------------------------------------------------
# Dashboard: daily schedules
# ---------------------------------------------------------------------------
async def get_daily_schedule(username: str, date: str) -> dict | None:
    row = await fetchone(
        "SELECT schedule_json FROM daily_schedules "
        "WHERE username = %s AND date = %s",
        (username, date),
    )
    return row["schedule_json"] if row else None


async def save_daily_schedule(
    username: str, date: str, schedule_json: str
) -> None:
    await execute(
        """
        INSERT INTO daily_schedules (username, date, schedule_json, generated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT(username, date) DO UPDATE SET
            schedule_json = EXCLUDED.schedule_json,
            generated_at = EXCLUDED.generated_at
        """,
        (username, date, schedule_json, now()),
    )


async def delete_daily_schedule(username: str, date: str) -> None:
    await execute(
        "DELETE FROM daily_schedules WHERE username = %s AND date = %s",
        (username, date),
    )


# ---------------------------------------------------------------------------
# Dashboard: daily logs (domain-keyed)
# ---------------------------------------------------------------------------
async def get_daily_logs(username: str, date: str) -> dict:
    """Return all domain logs for a user on a date, keyed by domain."""
    rows = await fetchall(
        "SELECT domain, log_json FROM daily_logs "
        "WHERE username = %s AND date = %s",
        (username, date),
    )
    return {row["domain"]: row["log_json"] for row in rows}


async def get_recent_daily_logs(
    username: str, domain: str, days: int
) -> list[dict]:
    """Return the last `days` days of logs for a domain, oldest first.

    Each entry is {"date": ..., "entries": [...]}. Days with no log row are
    omitted (the caller fills gaps with empty entries).
    """
    rows = await fetchall(
        "SELECT date, log_json FROM daily_logs "
        "WHERE username = %s AND domain = %s "
        "ORDER BY date DESC LIMIT %s",
        (username, domain, days),
    )
    out = [{"date": row["date"], "entries": row["log_json"]} for row in rows]
    out.reverse()
    return out


async def save_daily_log(
    username: str, date: str, domain: str, log_json: str
) -> None:
    await execute(
        """
        INSERT INTO daily_logs (username, date, domain, log_json, updated_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT(username, date, domain) DO UPDATE SET
            log_json = EXCLUDED.log_json,
            updated_at = EXCLUDED.updated_at
        """,
        (username, date, domain, log_json, now()),
    )


# ---------------------------------------------------------------------------
# Dashboard: biomarkers
# ---------------------------------------------------------------------------
async def add_biomarkers(username: str, readings: list[dict]) -> None:
    """Insert biomarker readings, deduping on (name, value, measured_at, source_doc)."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            for r in readings:
                # Check for an existing identical reading to avoid duplicates
                # on re-extraction from the same doc.
                await cur.execute(
                    "SELECT 1 FROM biomarkers WHERE username = %s AND name = %s "
                    "AND value = %s AND measured_at IS NOT DISTINCT FROM %s "
                    "AND source_doc = %s",
                    (
                        username,
                        r["name"],
                        r["value"],
                        r.get("measured_at"),
                        r.get("source_doc", ""),
                    ),
                )
                if await cur.fetchone():
                    continue
                await cur.execute(
                    """
                    INSERT INTO biomarkers
                        (username, name, value, unit, ref_low, ref_high,
                         optimal_low, optimal_high, status, source_doc,
                         measured_at, extracted_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        username,
                        r["name"],
                        r["value"],
                        r["unit"],
                        r.get("ref_low"),
                        r.get("ref_high"),
                        r.get("optimal_low"),
                        r.get("optimal_high"),
                        _biomarker_status(
                            r["value"],
                            r.get("ref_low"),
                            r.get("ref_high"),
                        ),
                        r.get("source_doc", ""),
                        r.get("measured_at"),
                        now(),
                    ),
                )


async def list_biomarkers(username: str) -> list[dict]:
    """Return all biomarker readings for a user, newest measurement first."""
    return await fetchall(
        "SELECT id, name, value, unit, ref_low, ref_high, optimal_low, "
        "optimal_high, status, source_doc, measured_at, extracted_at "
        "FROM biomarkers WHERE username = %s "
        "ORDER BY name ASC, measured_at DESC NULLS LAST, extracted_at DESC",
        (username,),
    )


async def list_biomarkers_by_name(username: str, name: str) -> list[dict]:
    return await fetchall(
        "SELECT id, name, value, unit, ref_low, ref_high, optimal_low, "
        "optimal_high, status, source_doc, measured_at, extracted_at "
        "FROM biomarkers WHERE username = %s AND name = %s "
        "ORDER BY measured_at ASC NULLS LAST, extracted_at ASC",
        (username, name),
    )


# ---------------------------------------------------------------------------
# Cascade delete (used by the seed script's --force flag)
# ---------------------------------------------------------------------------
async def delete_user_cascade(username: str) -> None:
    """Delete a user and ALL associated data across every table."""
    async with get_conn() as conn:
        async with conn.cursor() as cur:
            # Plan tables: delete child rows first, then plans/drafts/suggestions.
            await cur.execute(
                "SELECT id FROM plans WHERE patient_username = %s", (username,)
            )
            plan_ids = [row["id"] for row in await cur.fetchall()]
            for pid in plan_ids:
                await cur.execute("DELETE FROM plan_outcomes WHERE plan_id = %s", (pid,))
                await cur.execute("DELETE FROM plan_metrics WHERE plan_id = %s", (pid,))
                await cur.execute("DELETE FROM plan_phases WHERE plan_id = %s", (pid,))
            await cur.execute("DELETE FROM plans WHERE patient_username = %s", (username,))
            await cur.execute("DELETE FROM plan_drafts WHERE patient_username = %s", (username,))
            await cur.execute("DELETE FROM plan_suggestions WHERE patient_username = %s", (username,))
            await cur.execute("DELETE FROM biomarkers WHERE username = %s", (username,))
            await cur.execute("DELETE FROM daily_logs WHERE username = %s", (username,))
            await cur.execute("DELETE FROM daily_schedules WHERE username = %s", (username,))
            await cur.execute("DELETE FROM user_docs WHERE username = %s", (username,))
            await cur.execute("DELETE FROM user_profiles WHERE username = %s", (username,))
            await cur.execute("DELETE FROM tokens WHERE username = %s", (username,))
            await cur.execute("DELETE FROM users WHERE username = %s", (username,))
