"""SQLite-backed store for tracking plans, plan metrics, outcomes, phases,
and plan drafts.

Mirrors the sync-function + async-wrapper pattern used in ``database.py``.
Shares the same ``auth.db`` file and the same ``_lock`` so writes are
serialized across the patient and practitioner stores.

Tables (created in ``_init_plan_db_sync``, called from
``database._init_db_sync``):
  - plans
  - plan_outcomes
  - plan_metrics
  - plan_phases
  - plan_drafts
  - plan_suggestions

The ``daily_logs`` table gains a ``metric_id`` column (added in
``database._init_db_sync``) that references ``plan_metrics.id``.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import date, timedelta

from app.database import DB_PATH, _lock, _now, _column_exists


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------
def _init_plan_db_sync() -> None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_username TEXT NOT NULL,
                practitioner_id INTEGER,
                version INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                title TEXT,
                rationale TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plans_patient_active "
            "ON plans (patient_username, is_active)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                biomarker_name TEXT NOT NULL,
                target_value REAL NOT NULL,
                target_direction TEXT NOT NULL,
                target_high REAL,
                unit TEXT NOT NULL,
                target_date TEXT,
                current_value REAL,
                current_as_of TEXT,
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                template_id TEXT NOT NULL,
                label TEXT NOT NULL,
                unit TEXT NOT NULL,
                frequency TEXT NOT NULL,
                time_of_day TEXT,
                target_type TEXT NOT NULL,
                target_value REAL,
                target_high REAL,
                is_active INTEGER NOT NULL DEFAULT 1,
                phase INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plan_metrics_plan "
            "ON plan_metrics (plan_id, sort_order)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_phases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                phase_number INTEGER NOT NULL,
                name TEXT NOT NULL,
                focus TEXT,
                actions TEXT,
                day_start INTEGER NOT NULL,
                day_end INTEGER NOT NULL,
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_username TEXT NOT NULL,
                practitioner_id INTEGER NOT NULL,
                title TEXT,
                rationale TEXT,
                outcomes_json TEXT,
                metrics_json TEXT,
                phases_json TEXT,
                is_published INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plan_drafts_patient_unpublished "
            "ON plan_drafts (patient_username, is_published)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS plan_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_username TEXT NOT NULL,
                practitioner_id INTEGER,
                source TEXT NOT NULL,
                suggestion_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                decided_at TEXT,
                decided_by INTEGER
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_plan_suggestions_patient "
            "ON plan_suggestions (patient_username, status)"
        )
        # Add metric_id column to daily_logs (safe migration).
        if not _column_exists(conn, "daily_logs", "metric_id"):
            conn.execute(
                "ALTER TABLE daily_logs ADD COLUMN metric_id INTEGER REFERENCES plan_metrics(id)"
            )
        conn.commit()


# ---------------------------------------------------------------------------
# Row -> dict helpers
# ---------------------------------------------------------------------------
def _plan_row_to_dict(row: tuple) -> dict:
    cols = (
        "id", "patient_username", "practitioner_id", "version", "is_active",
        "title", "rationale", "created_at", "updated_at",
    )
    d = dict(zip(cols, row))
    d["is_active"] = bool(d["is_active"])
    d["practitioner_id"] = d["practitioner_id"]  # may be None
    return d


def _outcome_row_to_dict(row: tuple) -> dict:
    cols = (
        "id", "plan_id", "biomarker_name", "target_value", "target_direction",
        "target_high", "unit", "target_date", "current_value", "current_as_of",
    )
    return dict(zip(cols, row))


def _metric_row_to_dict(row: tuple) -> dict:
    cols = (
        "id", "plan_id", "template_id", "label", "unit", "frequency",
        "time_of_day", "target_type", "target_value", "target_high",
        "is_active", "phase", "sort_order",
    )
    d = dict(zip(cols, row))
    d["is_active"] = bool(d["is_active"])
    return d


def _phase_row_to_dict(row: tuple) -> dict:
    cols = (
        "id", "plan_id", "phase_number", "name", "focus", "actions",
        "day_start", "day_end",
    )
    d = dict(zip(cols, row))
    if d.get("actions"):
        try:
            d["actions"] = json.loads(d["actions"])
        except (json.JSONDecodeError, TypeError):
            d["actions"] = []
    else:
        d["actions"] = []
    return d


def _draft_row_to_dict(row: tuple) -> dict:
    cols = (
        "id", "patient_username", "practitioner_id", "title", "rationale",
        "outcomes_json", "metrics_json", "phases_json", "is_published",
        "created_at", "updated_at",
    )
    d = dict(zip(cols, row))
    d["is_published"] = bool(d["is_published"])
    for k in ("outcomes_json", "metrics_json", "phases_json"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except (json.JSONDecodeError, TypeError):
                d[k] = [] if k != "outcomes_json" else []
        else:
            d[k] = []
    return d


# ---------------------------------------------------------------------------
# Plans (active plan CRUD + queries)
# ---------------------------------------------------------------------------
def _get_active_plan_sync(patient_username: str) -> dict | None:
    """Return the active plan for a patient with all child rows, or None."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        plan_row = conn.execute(
            "SELECT id, patient_username, practitioner_id, version, is_active, "
            "title, rationale, created_at, updated_at FROM plans "
            "WHERE patient_username = ? AND is_active = 1 "
            "ORDER BY version DESC LIMIT 1",
            (patient_username,),
        ).fetchone()
        if not plan_row:
            return None
        plan = _plan_row_to_dict(plan_row)
        plan["outcomes"] = _fetch_outcomes(conn, plan["id"])
        plan["metrics"] = _fetch_metrics(conn, plan["id"])
        plan["phases"] = _fetch_phases(conn, plan["id"])
        return plan


def _fetch_outcomes(conn: sqlite3.Connection, plan_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, plan_id, biomarker_name, target_value, target_direction, "
        "target_high, unit, target_date, current_value, current_as_of "
        "FROM plan_outcomes WHERE plan_id = ? ORDER BY id ASC",
        (plan_id,),
    ).fetchall()
    return [_outcome_row_to_dict(r) for r in rows]


def _fetch_metrics(conn: sqlite3.Connection, plan_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, plan_id, template_id, label, unit, frequency, time_of_day, "
        "target_type, target_value, target_high, is_active, phase, sort_order "
        "FROM plan_metrics WHERE plan_id = ? ORDER BY sort_order ASC, id ASC",
        (plan_id,),
    ).fetchall()
    return [_metric_row_to_dict(r) for r in rows]


def _fetch_phases(conn: sqlite3.Connection, plan_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, plan_id, phase_number, name, focus, actions, day_start, day_end "
        "FROM plan_phases WHERE plan_id = ? ORDER BY phase_number ASC",
        (plan_id,),
    ).fetchall()
    return [_phase_row_to_dict(r) for r in rows]


def _create_plan_sync(
    patient_username: str,
    practitioner_id: int | None,
    title: str | None,
    rationale: str | None,
    outcomes: list[dict],
    metrics: list[dict],
    phases: list[dict],
) -> dict:
    """Create a new active plan (new version), archiving any prior active plan.

    Returns the new plan dict (with child rows).
    """
    now = _now()
    with _lock, sqlite3.connect(DB_PATH) as conn:
        # Determine the next version number.
        prior_version = conn.execute(
            "SELECT MAX(version) FROM plans WHERE patient_username = ?",
            (patient_username,),
        ).fetchone()
        next_version = (prior_version[0] or 0) + 1
        # Archive any existing active plan.
        conn.execute(
            "UPDATE plans SET is_active = 0 WHERE patient_username = ? AND is_active = 1",
            (patient_username,),
        )
        cur = conn.execute(
            "INSERT INTO plans (patient_username, practitioner_id, version, "
            "is_active, title, rationale, created_at, updated_at) "
            "VALUES (?, ?, ?, 1, ?, ?, ?, ?)",
            (patient_username, practitioner_id, next_version, title, rationale, now, now),
        )
        plan_id = cur.lastrowid
        _insert_outcomes(conn, plan_id, outcomes)
        _insert_metrics(conn, plan_id, metrics)
        _insert_phases(conn, plan_id, phases)
        conn.commit()
        plan = _plan_row_to_dict(
            conn.execute(
                "SELECT id, patient_username, practitioner_id, version, is_active, "
                "title, rationale, created_at, updated_at FROM plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
        )
        plan["outcomes"] = _fetch_outcomes(conn, plan_id)
        plan["metrics"] = _fetch_metrics(conn, plan_id)
        plan["phases"] = _fetch_phases(conn, plan_id)
        return plan


def _insert_outcomes(conn: sqlite3.Connection, plan_id: int, outcomes: list[dict]) -> None:
    for o in outcomes:
        conn.execute(
            "INSERT INTO plan_outcomes (plan_id, biomarker_name, target_value, "
            "target_direction, target_high, unit, target_date, current_value, "
            "current_as_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                plan_id,
                o.get("biomarker_name", ""),
                float(o.get("target_value", 0)),
                o.get("target_direction", "below"),
                o.get("target_high"),
                o.get("unit", ""),
                o.get("target_date"),
                o.get("current_value"),
                o.get("current_as_of"),
            ),
        )


def _insert_metrics(conn: sqlite3.Connection, plan_id: int, metrics: list[dict]) -> None:
    for i, m in enumerate(metrics):
        conn.execute(
            "INSERT INTO plan_metrics (plan_id, template_id, label, unit, "
            "frequency, time_of_day, target_type, target_value, target_high, "
            "is_active, phase, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                plan_id,
                m.get("template_id", ""),
                m.get("label", ""),
                m.get("unit", ""),
                m.get("frequency", "daily"),
                m.get("time_of_day"),
                m.get("target_type", "minimum"),
                m.get("target_value"),
                m.get("target_high"),
                1 if m.get("is_active", True) else 0,
                m.get("phase"),
                m.get("sort_order", i),
            ),
        )


def _insert_phases(conn: sqlite3.Connection, plan_id: int, phases: list[dict]) -> None:
    for p in phases:
        actions = p.get("actions", [])
        actions_json = json.dumps(actions) if isinstance(actions, list) else (actions or "[]")
        conn.execute(
            "INSERT INTO plan_phases (plan_id, phase_number, name, focus, actions, "
            "day_start, day_end) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                plan_id,
                int(p.get("phase_number", 1)),
                p.get("name", ""),
                p.get("focus", ""),
                actions_json,
                int(p.get("day_start", 1)),
                int(p.get("day_end", 30)),
            ),
        )


def _has_active_plan_sync(patient_username: str) -> bool:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM plans WHERE patient_username = ? AND is_active = 1",
            (patient_username,),
        ).fetchone()
    return row is not None


def _get_metric_sync(metric_id: int) -> dict | None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, plan_id, template_id, label, unit, frequency, time_of_day, "
            "target_type, target_value, target_high, is_active, phase, sort_order "
            "FROM plan_metrics WHERE id = ?",
            (metric_id,),
        ).fetchone()
    return _metric_row_to_dict(row) if row else None


def _list_active_metric_ids_sync(patient_username: str) -> list[int]:
    """Return the IDs of all metrics in the patient's active plan."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT pm.id FROM plan_metrics pm "
            "JOIN plans p ON pm.plan_id = p.id "
            "WHERE p.patient_username = ? AND p.is_active = 1 AND pm.is_active = 1 "
            "ORDER BY pm.sort_order ASC",
            (patient_username,),
        ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Plan drafts
# ---------------------------------------------------------------------------
def _get_unpublished_draft_sync(patient_username: str) -> dict | None:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, patient_username, practitioner_id, title, rationale, "
            "outcomes_json, metrics_json, phases_json, is_published, "
            "created_at, updated_at FROM plan_drafts "
            "WHERE patient_username = ? AND is_published = 0 "
            "ORDER BY id DESC LIMIT 1",
            (patient_username,),
        ).fetchone()
    return _draft_row_to_dict(row) if row else None


def _create_draft_sync(
    patient_username: str,
    practitioner_id: int,
    title: str | None = None,
    rationale: str | None = None,
    outcomes: list[dict] | None = None,
    metrics: list[dict] | None = None,
    phases: list[dict] | None = None,
) -> dict:
    """Create a new draft, replacing any existing unpublished draft."""
    now = _now()
    with _lock, sqlite3.connect(DB_PATH) as conn:
        # Replace any existing unpublished draft.
        conn.execute(
            "DELETE FROM plan_drafts WHERE patient_username = ? AND is_published = 0",
            (patient_username,),
        )
        cur = conn.execute(
            "INSERT INTO plan_drafts (patient_username, practitioner_id, title, "
            "rationale, outcomes_json, metrics_json, phases_json, is_published, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)",
            (
                patient_username,
                practitioner_id,
                title,
                rationale,
                json.dumps(outcomes or []),
                json.dumps(metrics or []),
                json.dumps(phases or []),
                now,
                now,
            ),
        )
        draft_id = cur.lastrowid
        conn.commit()
        row = conn.execute(
            "SELECT id, patient_username, practitioner_id, title, rationale, "
            "outcomes_json, metrics_json, phases_json, is_published, "
            "created_at, updated_at FROM plan_drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
    return _draft_row_to_dict(row)


def _update_draft_sync(
    patient_username: str,
    title: str | None = None,
    rationale: str | None = None,
    outcomes: list[dict] | None = None,
    metrics: list[dict] | None = None,
    phases: list[dict] | None = None,
) -> dict | None:
    """Update fields on the existing unpublished draft. Only non-None fields
    are updated. Returns the updated draft or None if no draft exists."""
    now = _now()
    sets: list[str] = ["updated_at = ?"]
    params: list = [now]
    if title is not None:
        sets.append("title = ?")
        params.append(title)
    if rationale is not None:
        sets.append("rationale = ?")
        params.append(rationale)
    if outcomes is not None:
        sets.append("outcomes_json = ?")
        params.append(json.dumps(outcomes))
    if metrics is not None:
        sets.append("metrics_json = ?")
        params.append(json.dumps(metrics))
    if phases is not None:
        sets.append("phases_json = ?")
        params.append(json.dumps(phases))
    params.append(patient_username)
    with _lock, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            f"UPDATE plan_drafts SET {', '.join(sets)} "
            f"WHERE patient_username = ? AND is_published = 0",
            params,
        )
        if cur.rowcount == 0:
            conn.commit()
            return None
        conn.commit()
        row = conn.execute(
            "SELECT id, patient_username, practitioner_id, title, rationale, "
            "outcomes_json, metrics_json, phases_json, is_published, "
            "created_at, updated_at FROM plan_drafts "
            "WHERE patient_username = ? AND is_published = 0 "
            "ORDER BY id DESC LIMIT 1",
            (patient_username,),
        ).fetchone()
    return _draft_row_to_dict(row) if row else None


def _delete_draft_sync(patient_username: str) -> bool:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "DELETE FROM plan_drafts WHERE patient_username = ? AND is_published = 0",
            (patient_username,),
        )
        conn.commit()
        return cur.rowcount > 0


def _publish_draft_sync(patient_username: str) -> dict | None:
    """Publish the current unpublished draft: create a new active plan from
    the draft's JSON, mark the draft as published. Returns the new active plan
    or None if no unpublished draft exists."""
    draft = _get_unpublished_draft_sync(patient_username)
    if not draft:
        return None
    plan = _create_plan_sync(
        patient_username=patient_username,
        practitioner_id=draft["practitioner_id"],
        title=draft.get("title"),
        rationale=draft.get("rationale"),
        outcomes=draft.get("outcomes_json") or [],
        metrics=draft.get("metrics_json") or [],
        phases=draft.get("phases_json") or [],
    )
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE plan_drafts SET is_published = 1, updated_at = ? "
            "WHERE id = ?",
            (_now(), draft["id"]),
        )
        conn.commit()
    return plan


# ---------------------------------------------------------------------------
# Plan suggestions (AI-proposed adjustments for practitioner approval)
# ---------------------------------------------------------------------------
def _add_plan_suggestion_sync(
    patient_username: str,
    practitioner_id: int | None,
    source: str,
    suggestion: dict,
) -> dict:
    now = _now()
    with _lock, sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO plan_suggestions (patient_username, practitioner_id, "
            "source, suggestion_json, status, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (patient_username, practitioner_id, source, json.dumps(suggestion), now),
        )
        sid = cur.lastrowid
        conn.commit()
    return {
        "id": sid,
        "patient_username": patient_username,
        "practitioner_id": practitioner_id,
        "source": source,
        "suggestion": suggestion,
        "status": "pending",
        "created_at": now,
        "decided_at": None,
        "decided_by": None,
    }


def _list_plan_suggestions_sync(
    patient_username: str, status: str | None = None
) -> list[dict]:
    with _lock, sqlite3.connect(DB_PATH) as conn:
        if status:
            rows = conn.execute(
                "SELECT id, patient_username, practitioner_id, source, "
                "suggestion_json, status, created_at, decided_at, decided_by "
                "FROM plan_suggestions WHERE patient_username = ? AND status = ? "
                "ORDER BY created_at DESC",
                (patient_username, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, patient_username, practitioner_id, source, "
                "suggestion_json, status, created_at, decided_at, decided_by "
                "FROM plan_suggestions WHERE patient_username = ? "
                "ORDER BY created_at DESC",
                (patient_username,),
            ).fetchall()
    out = []
    for r in rows:
        try:
            suggestion = json.loads(r[4])
        except (json.JSONDecodeError, TypeError):
            suggestion = {}
        out.append(
            {
                "id": r[0],
                "patient_username": r[1],
                "practitioner_id": r[2],
                "source": r[3],
                "suggestion": suggestion,
                "status": r[5],
                "created_at": r[6],
                "decided_at": r[7],
                "decided_by": r[8],
            }
        )
    return out


def _set_suggestion_status_sync(
    suggestion_id: int,
    status: str,
    decided_by: int | None = None,
) -> dict | None:
    now = _now()
    with _lock, sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE plan_suggestions SET status = ?, decided_at = ?, decided_by = ? "
            "WHERE id = ?",
            (status, now, decided_by, suggestion_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, patient_username, practitioner_id, source, "
            "suggestion_json, status, created_at, decided_at, decided_by "
            "FROM plan_suggestions WHERE id = ?",
            (suggestion_id,),
        ).fetchone()
    if not row:
        return None
    try:
        suggestion = json.loads(row[4])
    except (json.JSONDecodeError, TypeError):
        suggestion = {}
    return {
        "id": row[0],
        "patient_username": row[1],
        "practitioner_id": row[2],
        "source": row[3],
        "suggestion": suggestion,
        "status": row[5],
        "created_at": row[6],
        "decided_at": row[7],
        "decided_by": row[8],
    }


# ---------------------------------------------------------------------------
# Daily logs (metric_id-aware helpers)
# ---------------------------------------------------------------------------
def _save_metric_log_sync(
    username: str,
    iso_date: str,
    metric_id: int,
    log_json: str,
) -> None:
    """Upsert a daily log row keyed by (username, date, metric_id).

    Keeps the old ``domain`` column in sync by looking up the metric's
    template_id (so legacy code paths that read by domain still work during
    migration). The primary key is extended to include metric_id.
    """
    with _lock, sqlite3.connect(DB_PATH) as conn:
        # Look up the metric to get a domain-like value for the legacy column.
        metric = conn.execute(
            "SELECT template_id FROM plan_metrics WHERE id = ?", (metric_id,)
        ).fetchone()
        domain = metric[0] if metric else "other"
        conn.execute(
            """
            INSERT INTO daily_logs (username, date, domain, metric_id, log_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, date, domain) DO UPDATE SET
                metric_id = excluded.metric_id,
                log_json = excluded.log_json,
                updated_at = excluded.updated_at
            """,
            (username, iso_date, domain, metric_id, log_json, _now()),
        )
        conn.commit()


def _get_metric_logs_sync(username: str, iso_date: str) -> dict[int, list[dict]]:
    """Return all metric logs for a user on a date, keyed by metric_id."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT metric_id, log_json FROM daily_logs "
            "WHERE username = ? AND date = ? AND metric_id IS NOT NULL",
            (username, iso_date),
        ).fetchall()
    out: dict[int, list[dict]] = {}
    for metric_id, log_json in rows:
        if metric_id is None:
            continue
        try:
            out[metric_id] = json.loads(log_json)
        except (json.JSONDecodeError, TypeError):
            out[metric_id] = []
    return out


def _get_recent_metric_logs_sync(
    username: str, metric_id: int, days: int
) -> list[dict]:
    """Return the last `days` days of logs for a single metric, oldest first."""
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT date, log_json FROM daily_logs "
            "WHERE username = ? AND metric_id = ? "
            "ORDER BY date DESC LIMIT ?",
            (username, metric_id, days),
        ).fetchall()
    out = [{"date": d, "entries": json.loads(j)} for d, j in rows]
    out.reverse()
    return out


def _get_all_metric_logs_range_sync(
    username: str, metric_id: int, days: int
) -> list[dict]:
    """Return logs for a metric over the last `days` days (same as recent)."""
    return _get_recent_metric_logs_sync(username, metric_id, days)


# ---------------------------------------------------------------------------
# Migration: create default plans for existing onboarded patients
# ---------------------------------------------------------------------------
def _migrate_domain_logs_for_patient_sync(
    conn: sqlite3.Connection,
    patient_username: str,
    plan_id: int,
    metric_id_by_template: dict[str, int],
) -> int:
    """Re-point existing daily_logs rows (with domain values) to the new
    metric IDs in the default plan. Returns the number of rows updated."""
    from app.metric_templates import DOMAIN_TO_TEMPLATE
    updated = 0
    for domain, template_id in DOMAIN_TO_TEMPLATE.items():
        metric_id = metric_id_by_template.get(template_id)
        if metric_id is None:
            continue
        cur = conn.execute(
            "UPDATE daily_logs SET metric_id = ? "
            "WHERE username = ? AND domain = ? AND metric_id IS NULL",
            (metric_id, patient_username, domain),
        )
        updated += cur.rowcount
    return updated


def _create_default_plan_for_patient_sync(
    patient_username: str,
    plan_json: dict | None,
) -> dict | None:
    """Create a default plan for an existing onboarded patient, mapping the
    old 6 wellness domains to template metrics. Idempotent — skips if the
    patient already has an active plan."""
    from app.metric_templates import DOMAIN_TO_TEMPLATE, get_template

    if _has_active_plan_sync(patient_username):
        return None

    summary = (plan_json or {}).get("summary", "Wellness Plan")
    phases_raw = (plan_json or {}).get("phases", [])
    phases: list[dict] = []
    for i, p in enumerate(phases_raw, start=1):
        day_start = 1 + (i - 1) * 30
        day_end = i * 30
        phases.append(
            {
                "phase_number": i,
                "name": p.get("name", f"Phase {i}: Days {day_start}-{day_end}"),
                "focus": p.get("focus", ""),
                "actions": p.get("actions", []),
                "day_start": day_start,
                "day_end": day_end,
            }
        )
    if not phases:
        phases = [
            {
                "phase_number": 1,
                "name": "Phase 1: Days 1-30",
                "focus": "Build foundational wellness habits.",
                "actions": [],
                "day_start": 1,
                "day_end": 30,
            }
        ]

    metrics: list[dict] = []
    sort = 0
    for domain in ("workout", "diet", "meditation", "medication", "mental_health"):
        template_id = DOMAIN_TO_TEMPLATE.get(domain)
        if not template_id:
            continue
        t = get_template(template_id)
        if not t:
            continue
        metrics.append(
            {
                "template_id": t.key,
                "label": t.label,
                "unit": t.unit,
                "frequency": t.frequency_options[0],
                "time_of_day": None,
                "target_type": t.target_type,
                "target_value": t.default_target,
                "target_high": t.default_target_high,
                "is_active": True,
                "phase": None,
                "sort_order": sort,
            }
        )
        sort += 1

    plan = _create_plan_sync(
        patient_username=patient_username,
        practitioner_id=None,
        title=summary,
        rationale=summary,
        outcomes=[],
        metrics=metrics,
        phases=phases,
    )

    # Re-point existing daily_logs rows to the new metric IDs.
    metric_id_by_template: dict[str, int] = {}
    for m in plan["metrics"]:
        metric_id_by_template[m["template_id"]] = m["id"]
    with _lock, sqlite3.connect(DB_PATH) as conn:
        _migrate_domain_logs_for_patient_sync(
            conn, patient_username, plan["id"], metric_id_by_template
        )
        conn.commit()
    return plan


def _run_plan_migration_sync() -> None:
    """Run the migration: for each onboarded patient with no active plan,
    create a default plan and re-point logs. Idempotent."""
    from app.database import _get_profile_sync  # avoid circular import at module load
    with _lock, sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT username FROM user_profiles WHERE onboarded = 1"
        ).fetchall()
    for (username,) in rows:
        if _has_active_plan_sync(username):
            continue
        profile_data = _get_profile_sync(username)
        plan_json = profile_data.get("plan") if profile_data else None
        _create_default_plan_for_patient_sync(username, plan_json)


# ---------------------------------------------------------------------------
# Async wrappers
# ---------------------------------------------------------------------------
async def get_active_plan(patient_username: str) -> dict | None:
    return await asyncio.to_thread(_get_active_plan_sync, patient_username)


async def create_plan(
    patient_username: str,
    practitioner_id: int | None,
    title: str | None,
    rationale: str | None,
    outcomes: list[dict],
    metrics: list[dict],
    phases: list[dict],
) -> dict:
    return await asyncio.to_thread(
        _create_plan_sync,
        patient_username,
        practitioner_id,
        title,
        rationale,
        outcomes,
        metrics,
        phases,
    )


async def has_active_plan(patient_username: str) -> bool:
    return await asyncio.to_thread(_has_active_plan_sync, patient_username)


async def get_metric(metric_id: int) -> dict | None:
    return await asyncio.to_thread(_get_metric_sync, metric_id)


async def list_active_metric_ids(patient_username: str) -> list[int]:
    return await asyncio.to_thread(_list_active_metric_ids_sync, patient_username)


async def get_unpublished_draft(patient_username: str) -> dict | None:
    return await asyncio.to_thread(_get_unpublished_draft_sync, patient_username)


async def create_draft(
    patient_username: str,
    practitioner_id: int,
    title: str | None = None,
    rationale: str | None = None,
    outcomes: list[dict] | None = None,
    metrics: list[dict] | None = None,
    phases: list[dict] | None = None,
) -> dict:
    return await asyncio.to_thread(
        _create_draft_sync,
        patient_username,
        practitioner_id,
        title,
        rationale,
        outcomes,
        metrics,
        phases,
    )


async def update_draft(
    patient_username: str,
    title: str | None = None,
    rationale: str | None = None,
    outcomes: list[dict] | None = None,
    metrics: list[dict] | None = None,
    phases: list[dict] | None = None,
) -> dict | None:
    return await asyncio.to_thread(
        _update_draft_sync,
        patient_username,
        title,
        rationale,
        outcomes,
        metrics,
        phases,
    )


async def delete_draft(patient_username: str) -> bool:
    return await asyncio.to_thread(_delete_draft_sync, patient_username)


async def publish_draft(patient_username: str) -> dict | None:
    return await asyncio.to_thread(_publish_draft_sync, patient_username)


async def add_plan_suggestion(
    patient_username: str,
    practitioner_id: int | None,
    source: str,
    suggestion: dict,
) -> dict:
    return await asyncio.to_thread(
        _add_plan_suggestion_sync,
        patient_username,
        practitioner_id,
        source,
        suggestion,
    )


async def list_plan_suggestions(
    patient_username: str, status: str | None = None
) -> list[dict]:
    return await asyncio.to_thread(
        _list_plan_suggestions_sync, patient_username, status
    )


async def set_suggestion_status(
    suggestion_id: int, status: str, decided_by: int | None = None
) -> dict | None:
    return await asyncio.to_thread(
        _set_suggestion_status_sync, suggestion_id, status, decided_by
    )


async def save_metric_log(
    username: str, iso_date: str, metric_id: int, log_json: str
) -> None:
    await asyncio.to_thread(_save_metric_log_sync, username, iso_date, metric_id, log_json)


async def get_metric_logs(username: str, iso_date: str) -> dict[int, list[dict]]:
    return await asyncio.to_thread(_get_metric_logs_sync, username, iso_date)


async def get_recent_metric_logs(
    username: str, metric_id: int, days: int
) -> list[dict]:
    return await asyncio.to_thread(_get_recent_metric_logs_sync, username, metric_id, days)


async def run_plan_migration() -> None:
    await asyncio.to_thread(_run_plan_migration_sync)


async def create_default_plan_for_patient(
    patient_username: str, plan_json: dict | None
) -> dict | None:
    return await asyncio.to_thread(
        _create_default_plan_for_patient_sync, patient_username, plan_json
    )
