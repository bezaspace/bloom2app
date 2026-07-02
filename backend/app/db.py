"""Central PostgreSQL connection pool and migration runner.

Replaces the old SQLite ``sqlite3`` + ``threading.Lock`` pattern with an
async ``psycopg_pool.AsyncConnectionPool``. The pool is created once in the
FastAPI lifespan and shared across all DB modules.

All queries use ``%s`` placeholders (psycopg3 style). Rows are returned as
dicts via ``dict_row`` row_factory, so callers can access columns by name
without manual ``dict(zip(cols, row))`` conversions.

Migration scripts live in ``backend/migrations/`` as numbered ``.sql`` files.
A lightweight runner tracks applied versions in ``_schema_migrations`` and
executes any unrun scripts on startup.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger("bloom2.db")

# ---------------------------------------------------------------------------
# Pool management
# ---------------------------------------------------------------------------
_pool: AsyncConnectionPool | None = None

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def _get_database_url() -> str:
    """Return the PostgreSQL connection URL from env or default."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://bloom:bloom@localhost:5432/bloom2",
    )


async def init_pool() -> None:
    """Create the global connection pool. Call once at app startup."""
    global _pool
    if _pool is not None:
        return
    db_url = _get_database_url()
    logger.info("Creating PostgreSQL connection pool: %s", _mask_password(db_url))
    _pool = AsyncConnectionPool(
        conninfo=db_url,
        min_size=2,
        max_size=10,
        timeout=30,
        max_lifetime=3600,
        open=False,
        kwargs={
            "row_factory": dict_row,
            "autocommit": False,
        },
    )
    await _pool.open()
    logger.info("PostgreSQL connection pool ready.")


async def close_pool() -> None:
    """Close the pool. Call on app shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed.")


def _mask_password(url: str) -> str:
    """Mask the password in a connection URL for logging."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            creds, host_part = rest.rsplit("@", 1)
            if ":" in creds:
                user, _pw = creds.rsplit(":", 1)
                return f"{scheme}://{user}:***@{host_part}"
    return url


def get_pool() -> AsyncConnectionPool:
    """Return the global pool. Raises if not initialized."""
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_pool() first")
    return _pool


@asynccontextmanager
async def get_conn():
    """Acquire a connection from the pool (context manager).

    Yields an ``AsyncConnection`` with ``dict_row`` row_factory.
    The connection is returned to the pool on exit. Transactions are
    committed automatically on clean exit, rolled back on exception.
    """
    pool = get_pool()
    async with pool.connection() as conn:
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


@asynccontextmanager
async def get_cursor(conn: AsyncConnection | None = None):
    """Acquire a cursor, optionally from an externally-provided connection.

    If ``conn`` is None, a connection is acquired from the pool (with
    auto-commit/rollback semantics). If a connection is provided, the caller
    manages the transaction.

    Yields an ``AsyncCursor`` with ``dict_row`` row_factory.
    """
    if conn is not None:
        async with conn.cursor() as cur:
            yield cur
    else:
        async with get_conn() as own_conn:
            async with own_conn.cursor() as cur:
                yield cur


# ---------------------------------------------------------------------------
# Convenience query helpers
# ---------------------------------------------------------------------------
async def fetchone(sql: str, params: tuple | None = None) -> dict | None:
    """Execute a query and return the first row as a dict, or None."""
    async with get_cursor() as cur:
        await cur.execute(sql, params)
        return await cur.fetchone()


async def fetchall(sql: str, params: tuple | None = None) -> list[dict]:
    """Execute a query and return all rows as dicts."""
    async with get_cursor() as cur:
        await cur.execute(sql, params)
        return await cur.fetchall()


async def execute(sql: str, params: tuple | None = None) -> str:
    """Execute a statement (INSERT/UPDATE/DELETE) and return the status string.

    For INSERT ... RETURNING, use ``fetchone`` or ``fetchall`` instead.
    """
    async with get_cursor() as cur:
        await cur.execute(sql, params)
        return cur.statusmessage


async def fetchval(sql: str, params: tuple | None = None):
    """Execute a query and return the first column of the first row."""
    row = await fetchone(sql, params)
    if row is None:
        return None
    # Return the first value from the dict
    return next(iter(row.values()))


# ---------------------------------------------------------------------------
# Timestamp helper
# ---------------------------------------------------------------------------
def now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime.

    PostgreSQL ``TIMESTAMPTZ`` columns accept this directly. When rows are
    read back, the value is also a timezone-aware datetime.
    """
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------
async def run_migrations() -> None:
    """Run any pending SQL migration scripts.

    Scripts in ``backend/migrations/*.sql`` are executed in filename order.
    Each script is wrapped in a transaction. Applied versions are recorded in
    the ``_schema_migrations`` table.
    """
    if not MIGRATIONS_DIR.is_dir():
        logger.warning("Migrations directory not found: %s", MIGRATIONS_DIR)
        return

    scripts = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not scripts:
        logger.warning("No migration scripts found in %s", MIGRATIONS_DIR)
        return

    async with get_conn() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS _schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            await cur.execute("SELECT version FROM _schema_migrations")
            applied = {row["version"] for row in await cur.fetchall()}

        pending = [s for s in scripts if s.stem not in applied]
        if not pending:
            logger.info("Migrations: all %d scripts already applied.", len(scripts))
            return

        for script in pending:
            version = script.stem
            logger.info("Migrations: applying %s ...", version)
            sql_text = script.read_text(encoding="utf-8")
            async with conn.cursor() as cur:
                await cur.execute(sql_text)
                await cur.execute(
                    "INSERT INTO _schema_migrations (version) VALUES (%s)",
                    (version,),
                )
            logger.info("Migrations: %s applied.", version)

    logger.info("Migrations: %d script(s) applied.", len(pending))
