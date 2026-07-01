"""Minimal SQLite-backed user authentication store.

Uses Python's built-in sqlite3 and hashlib (PBKDF2) so no extra auth dependencies
are required. The async wrappers run blocking DB calls via asyncio.to_thread().
"""

import asyncio
import hashlib
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
