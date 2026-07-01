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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                username TEXT PRIMARY KEY,
                profile_json TEXT NOT NULL,
                plan_json TEXT NOT NULL,
                doc_summary_json TEXT,
                onboarded INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
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
        conn.commit()


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
            "SELECT profile_json, plan_json, doc_summary_json, onboarded "
            "FROM user_profiles WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return None
    profile_json, plan_json, doc_summary_json, onboarded = row
    return {
        "profile": json.loads(profile_json) if profile_json else None,
        "plan": json.loads(plan_json) if plan_json else None,
        "doc_summary": json.loads(doc_summary_json) if doc_summary_json else None,
        "onboarded": bool(onboarded),
    }


def _save_profile_sync(
    username: str,
    profile_json: str,
    plan_json: str,
    doc_summary_json: str | None,
    onboarded: bool,
) -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO user_profiles
                (username, profile_json, plan_json, doc_summary_json, onboarded, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                profile_json = excluded.profile_json,
                plan_json = excluded.plan_json,
                doc_summary_json = excluded.doc_summary_json,
                onboarded = excluded.onboarded,
                updated_at = excluded.updated_at
            """,
            (
                username,
                profile_json,
                plan_json,
                doc_summary_json,
                1 if onboarded else 0,
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
) -> None:
    await asyncio.to_thread(
        _save_profile_sync,
        username,
        profile_json,
        plan_json,
        doc_summary_json,
        onboarded,
    )


async def add_doc_record(username: str, filename: str, mime_type: str) -> int:
    return await asyncio.to_thread(_add_doc_record_sync, username, filename, mime_type)


async def list_docs(username: str) -> list[dict]:
    return await asyncio.to_thread(_list_docs_sync, username)
