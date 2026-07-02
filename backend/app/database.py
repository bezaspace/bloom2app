"""Minimal SQLite-backed user authentication store.

Uses Python's built-in sqlite3 and hashlib (PBKDF2) so no extra auth dependencies
are required. The async wrappers run blocking DB calls via asyncio.to_thread().
"""

import asyncio
import hashlib
import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "auth.db"

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_salt() -> bytes:
    return os.urandom(32)


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000).hex()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Return True if `column` exists on `table` (used for safe migrations)."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def _init_db_sync() -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # Onboarding profile + 90-day plan, persisted per user across sessions.
        # `onboarded_at` records when onboarding was finalized so the dashboard
        # can compute "day of plan". NULL for rows created before this column
        # existed; the dashboard falls back to day 1 in that case.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                username TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                doc_summary_json TEXT,
                onboarded INTEGER NOT NULL DEFAULT 0,
                onboarded_at TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        # Backfill the column on existing databases that predate it.
        conn.execute(
            "ALTER TABLE user_profiles ADD COLUMN onboarded_at TEXT"
            if not _column_exists(conn, "user_profiles", "onboarded_at")
            else "SELECT 1"
        )
        # Metadata for uploaded health documents (the file bytes are stored on
        # disk under backend/uploads/<username>/; this table tracks them).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                filename TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                uploaded_at TEXT NOT NULL
            )
            """
        )
        # AI-generated daily schedule, cached per user per day.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_schedules (
                username TEXT NOT NULL,
                date TEXT NOT NULL,
                schedule_json TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                PRIMARY KEY (username, date)
            )
            """
        )
        # User-entered actuals / check-offs, one row per user/date/domain.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_logs (
                username TEXT NOT NULL,
                date TEXT NOT NULL,
                domain TEXT NOT NULL,
                log_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (username, date, domain)
            )
            """
        )
        # Structured biomarker readings extracted from uploaded lab documents.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS biomarkers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                name TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL,
                ref_low REAL,
                ref_high REAL,
                optimal_low REAL,
                optimal_high REAL,
                status TEXT,
                source_doc TEXT,
                measured_at TEXT,
                extracted_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_biomarkers_user_name "
            "ON biomarkers (username, name, measured_at)"
        )
        conn.commit()

    # Initialize the practitioner-side tables (separate module, same DB file).
    from app.practitioner_db import _init_practitioner_db_sync
    _init_practitioner_db_sync()

    # Initialize the tracking-plan tables (plans, metrics, outcomes, phases,
    # drafts, suggestions) and add the metric_id column to daily_logs.
    from app.plan_db import _init_plan_db_sync
    _init_plan_db_sync()


def _register_user_sync(username: str, password: str) -> bool:
    salt = _make_salt()
    password_hash = _hash_password(password, salt)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
                (username, password_hash, salt.hex(), _now()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def _verify_user_sync(username: str, password: str) -> bool:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT password_hash, salt FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return False
    stored_hash, salt_hex = row
    return stored_hash == _hash_password(password, bytes.fromhex(salt_hex))


def _create_token_sync(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO tokens (token, username, created_at) VALUES (?, ?, ?)",
            (token, username, _now()),
        )
        conn.commit()
    return token


def _get_user_by_token_sync(token: str) -> str | None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT username FROM tokens WHERE token = ?", (token,)
        ).fetchone()
    return row[0] if row else None


def _delete_token_sync(token: str) -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
        conn.commit()


# ---------------------------------------------------------------------------
# Onboarding profile + plan + document summary (per-user, persistent)
# ---------------------------------------------------------------------------
def _get_profile_sync(username: str) -> dict | None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT profile_json, plan_json, doc_summary_json, onboarded, onboarded_at "
            "FROM user_profiles WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    profile_json, plan_json, doc_summary_json, onboarded, onboarded_at = row
    return {
        "profile": json.loads(profile_json) if profile_json else None,
        "plan": json.loads(plan_json) if plan_json else None,
        "doc_summary": json.loads(doc_summary_json) if doc_summary_json else None,
        "onboarded": bool(onboarded),
        "onboarded_at": onboarded_at,
    }


def _save_profile_sync(
    username: str,
    profile_json: str,
    plan_json: str,
    doc_summary_json: str | None,
    onboarded: bool,
    onboarded_at: str | None = None,
) -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        # On a fresh insert, set onboarded_at to now if finalizing and not given.
        # On conflict, only update onboarded_at when one is explicitly provided
        # (so re-saving a doc_summary during onboarding doesn't clobber the
        # timestamp that finalize_onboarding sets later).
        if onboarded and onboarded_at is None:
            # Check if a row already exists with a non-null onboarded_at.
            existing = conn.execute(
                "SELECT onboarded_at FROM user_profiles WHERE username = ?",
                (username,),
            ).fetchone()
            if not existing or not existing[0]:
                onboarded_at = _now()
            else:
                onboarded_at = existing[0]
        conn.execute(
            """
            INSERT INTO user_profiles
                (username, profile_json, plan_json, doc_summary_json,
                 onboarded, onboarded_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                profile_json = excluded.profile_json,
                plan_json = excluded.plan_json,
                doc_summary_json = excluded.doc_summary_json,
                onboarded = excluded.onboarded,
                onboarded_at = COALESCE(excluded.onboarded_at, user_profiles.onboarded_at),
                updated_at = excluded.updated_at
            """,
            (
                username,
                profile_json,
                plan_json,
                doc_summary_json,
                1 if onboarded else 0,
                onboarded_at,
                _now(),
            ),
        )
        conn.commit()


def _add_doc_record_sync(username: str, filename: str, mime_type: str) -> int:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO user_docs (username, filename, mime_type, uploaded_at) "
            "VALUES (?, ?, ?, ?)",
            (username, filename, mime_type, _now()),
        )
        conn.commit()
        return cur.lastrowid


def _list_docs_sync(username: str) -> list[dict]:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, filename, mime_type, uploaded_at FROM user_docs "
            "WHERE username = ? ORDER BY uploaded_at DESC",
            (username,),
        ).fetchall()
    return [
        {"id": r[0], "filename": r[1], "mime_type": r[2], "uploaded_at": r[3]}
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------
async def init_db() -> None:
    await asyncio.to_thread(_init_db_sync)


async def register_user(username: str, password: str) -> bool:
    return await asyncio.to_thread(_register_user_sync, username, password)


async def verify_user(username: str, password: str) -> bool:
    return await asyncio.to_thread(_verify_user_sync, username, password)


async def create_token(username: str) -> str:
    return await asyncio.to_thread(_create_token_sync, username)


async def get_user_by_token(token: str) -> str | None:
    return await asyncio.to_thread(_get_user_by_token_sync, token)


async def delete_token(token: str) -> None:
    await asyncio.to_thread(_delete_token_sync, token)


async def get_profile(username: str) -> dict | None:
    return await asyncio.to_thread(_get_profile_sync, username)


async def save_profile(
    username: str,
    profile_json: str,
    plan_json: str,
    doc_summary_json: str | None,
    onboarded: bool,
    onboarded_at: str | None = None,
) -> None:
    await asyncio.to_thread(
        _save_profile_sync,
        username,
        profile_json,
        plan_json,
        doc_summary_json,
        onboarded,
        onboarded_at,
    )


async def add_doc_record(username: str, filename: str, mime_type: str) -> int:
    return await asyncio.to_thread(_add_doc_record_sync, username, filename, mime_type)


async def list_docs(username: str) -> list[dict]:
    return await asyncio.to_thread(_list_docs_sync, username)


# ---------------------------------------------------------------------------
# Dashboard: daily schedules, daily logs, biomarkers
# ---------------------------------------------------------------------------
def _get_daily_schedule_sync(username: str, date: str) -> dict | None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT schedule_json FROM daily_schedules "
            "WHERE username = ? AND date = ?",
            (username, date),
        ).fetchone()
    return json.loads(row[0]) if row else None


def _save_daily_schedule_sync(username: str, date: str, schedule_json: str) -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO daily_schedules (username, date, schedule_json, generated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(username, date) DO UPDATE SET
                schedule_json = excluded.schedule_json,
                generated_at = excluded.generated_at
            """,
            (username, date, schedule_json, _now()),
        )
        conn.commit()


def _delete_daily_schedule_sync(username: str, date: str) -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "DELETE FROM daily_schedules WHERE username = ? AND date = ?",
            (username, date),
        )
        conn.commit()


def _get_daily_logs_sync(username: str, date: str) -> dict:
    """Return all domain logs for a user on a date, keyed by domain."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT domain, log_json FROM daily_logs "
            "WHERE username = ? AND date = ?",
            (username, date),
        ).fetchall()
    return {domain: json.loads(log_json) for domain, log_json in rows}


def _get_recent_daily_logs_sync(
    username: str, domain: str, days: int
) -> list[dict]:
    """Return the last `days` days of logs for a domain, oldest first.

    Each entry is {"date": ..., "entries": [...]}. Days with no log row are
    omitted (the caller fills gaps with empty entries).
    """
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT date, log_json FROM daily_logs "
            "WHERE username = ? AND domain = ? "
            "ORDER BY date DESC LIMIT ?",
            (username, domain, days),
        ).fetchall()
    out = [{"date": d, "entries": json.loads(j)} for d, j in rows]
    out.reverse()
    return out


def _save_daily_log_sync(
    username: str, date: str, domain: str, log_json: str
) -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO daily_logs (username, date, domain, log_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(username, date, domain) DO UPDATE SET
                log_json = excluded.log_json,
                updated_at = excluded.updated_at
            """,
            (username, date, domain, log_json, _now()),
        )
        conn.commit()


def _add_biomarkers_sync(username: str, readings: list[dict]) -> None:
    """Insert biomarker readings, deduping on (name, value, measured_at, source_doc)."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        for r in readings:
            # Check for an existing identical reading to avoid duplicates on
            # re-extraction from the same doc.
            exists = conn.execute(
                "SELECT 1 FROM biomarkers WHERE username = ? AND name = ? "
                "AND value = ? AND measured_at IS ? AND source_doc = ?",
                (
                    username,
                    r["name"],
                    r["value"],
                    r.get("measured_at"),
                    r.get("source_doc", ""),
                ),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO biomarkers
                    (username, name, value, unit, ref_low, ref_high,
                     optimal_low, optimal_high, status, source_doc,
                     measured_at, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    _now(),
                ),
            )
        conn.commit()


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


def _list_biomarkers_sync(username: str) -> list[dict]:
    """Return all biomarker readings for a user, newest measurement first."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, name, value, unit, ref_low, ref_high, optimal_low, "
            "optimal_high, status, source_doc, measured_at, extracted_at "
            "FROM biomarkers WHERE username = ? "
            "ORDER BY name ASC, measured_at DESC NULLS LAST, extracted_at DESC",
            (username,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "value": r[2],
            "unit": r[3],
            "ref_low": r[4],
            "ref_high": r[5],
            "optimal_low": r[6],
            "optimal_high": r[7],
            "status": r[8],
            "source_doc": r[9],
            "measured_at": r[10],
            "extracted_at": r[11],
        }
        for r in rows
    ]


def _list_biomarkers_by_name_sync(username: str, name: str) -> list[dict]:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, name, value, unit, ref_low, ref_high, optimal_low, "
            "optimal_high, status, source_doc, measured_at, extracted_at "
            "FROM biomarkers WHERE username = ? AND name = ? "
            "ORDER BY measured_at ASC NULLS LAST, extracted_at ASC",
            (username, name),
        ).fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "value": r[2],
            "unit": r[3],
            "ref_low": r[4],
            "ref_high": r[5],
            "optimal_low": r[6],
            "optimal_high": r[7],
            "status": r[8],
            "source_doc": r[9],
            "measured_at": r[10],
            "extracted_at": r[11],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Async wrappers for dashboard tables
# ---------------------------------------------------------------------------
async def get_daily_schedule(username: str, date: str) -> dict | None:
    return await asyncio.to_thread(_get_daily_schedule_sync, username, date)


async def save_daily_schedule(
    username: str, date: str, schedule_json: str
) -> None:
    await asyncio.to_thread(_save_daily_schedule_sync, username, date, schedule_json)


async def delete_daily_schedule(username: str, date: str) -> None:
    await asyncio.to_thread(_delete_daily_schedule_sync, username, date)


async def get_daily_logs(username: str, date: str) -> dict:
    return await asyncio.to_thread(_get_daily_logs_sync, username, date)


async def get_recent_daily_logs(
    username: str, domain: str, days: int
) -> list[dict]:
    return await asyncio.to_thread(
        _get_recent_daily_logs_sync, username, domain, days
    )


async def save_daily_log(
    username: str, date: str, domain: str, log_json: str
) -> None:
    await asyncio.to_thread(_save_daily_log_sync, username, date, domain, log_json)


async def add_biomarkers(username: str, readings: list[dict]) -> None:
    await asyncio.to_thread(_add_biomarkers_sync, username, readings)


async def list_biomarkers(username: str) -> list[dict]:
    return await asyncio.to_thread(_list_biomarkers_sync, username)


async def list_biomarkers_by_name(username: str, name: str) -> list[dict]:
    return await asyncio.to_thread(_list_biomarkers_by_name_sync, username, name)


# ---------------------------------------------------------------------------
# Cascade delete (used by the seed script's --force flag)
# ---------------------------------------------------------------------------
def _delete_user_cascade_sync(username: str) -> None:
    """Delete a user and ALL associated data across every table."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        # Plan tables: delete child rows first, then plans/drafts/suggestions.
        plan_ids = [r[0] for r in conn.execute(
            "SELECT id FROM plans WHERE patient_username = ?", (username,)
        ).fetchall()]
        for pid in plan_ids:
            conn.execute("DELETE FROM plan_outcomes WHERE plan_id = ?", (pid,))
            conn.execute("DELETE FROM plan_metrics WHERE plan_id = ?", (pid,))
            conn.execute("DELETE FROM plan_phases WHERE plan_id = ?", (pid,))
        conn.execute("DELETE FROM plans WHERE patient_username = ?", (username,))
        conn.execute("DELETE FROM plan_drafts WHERE patient_username = ?", (username,))
        conn.execute("DELETE FROM plan_suggestions WHERE patient_username = ?", (username,))
        conn.execute("DELETE FROM biomarkers WHERE username = ?", (username,))
        conn.execute("DELETE FROM daily_logs WHERE username = ?", (username,))
        conn.execute("DELETE FROM daily_schedules WHERE username = ?", (username,))
        conn.execute("DELETE FROM user_docs WHERE username = ?", (username,))
        conn.execute("DELETE FROM user_profiles WHERE username = ?", (username,))
        conn.execute("DELETE FROM tokens WHERE username = ?", (username,))
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()


async def delete_user_cascade(username: str) -> None:
    await asyncio.to_thread(_delete_user_cascade_sync, username)
