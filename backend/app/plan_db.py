"""PostgreSQL-backed store for tracking plans, plan metrics, outcomes, phases,
and plan drafts.

Uses ``psycopg3`` (async) via the shared connection pool in ``app.db``.
Replaces the old SQLite + threading.Lock pattern.

Tables (created by the migration runner in ``app.db``):
  - plans
  - plan_outcomes
  - plan_metrics
  - plan_phases
  - plan_drafts
  - plan_suggestions

The ``daily_logs`` table has a ``metric_id`` column (FK to plan_metrics.id).
"""

from __future__ import annotations

import json

from app.db import execute, fetchall, fetchone, get_conn, now


# ---------------------------------------------------------------------------
# Row -> dict helpers
# ---------------------------------------------------------------------------
def _plan_row_to_dict(row: dict) -> dict:
    d = {k: row.get(k) for k in (
        "id", "patient_username", "practitioner_id", "version", "is_active",
        "title", "rationale", "created_at", "updated_at",
    )}
    d["is_active"] = bool(d["is_active"])
    return d


def _outcome_row_to_dict(row: dict) -> dict:
    return {k: row.get(k) for k in (
        "id", "plan_id", "biomarker_name", "target_value", "target_direction",
        "target_high", "unit", "target_date", "current_value", "current_as_of",
    )}


def _metric_row_to_dict(row: dict) -> dict:
    d = {k: row.get(k) for k in (
        "id", "plan_id", "template_id", "label", "unit", "frequency",
        "time_of_day", "target_type", "target_value", "target_high",
        "is_active", "phase", "sort_order",
    )}
    d["is_active"] = bool(d["is_active"])
    return d


def _phase_row_to_dict(row: dict) -> dict:
    d = {k: row.get(k) for k in (
        "id", "plan_id", "phase_number", "name", "focus", "actions",
        "day_start", "day_end",
    )}
    # actions is JSONB — psycopg returns it as a Python list/dict already.
    if d.get("actions") is None:
        d["actions"] = []
    return d


def _draft_row_to_dict(row: dict) -> dict:
    d = {k: row.get(k) for k in (
        "id", "patient_username", "practitioner_id", "title", "rationale",
        "outcomes_json", "metrics_json", "phases_json", "is_published",
        "created_at", "updated_at",
    )}
    d["is_published"] = bool(d["is_published"])
    # JSONB columns come back as Python objects (list/dict) already.
    for k in ("outcomes_json", "metrics_json", "phases_json"):
        if d.get(k) is None:
            d[k] = []
    return d


# ---------------------------------------------------------------------------
# Plans (active plan CRUD + queries)
# ---------------------------------------------------------------------------
async def _fetch_outcomes(conn, plan_id: int) -> list[dict]:
    cur = conn.cursor()
    await cur.execute(
        "SELECT id, plan_id, biomarker_name, target_value, target_direction, "
        "target_high, unit, target_date, current_value, current_as_of "
        "FROM plan_outcomes WHERE plan_id = %s ORDER BY id ASC",
        (plan_id,),
    )
    rows = await cur.fetchall()
    return [_outcome_row_to_dict(r) for r in rows]


async def _fetch_metrics(conn, plan_id: int) -> list[dict]:
    cur = conn.cursor()
    await cur.execute(
        "SELECT id, plan_id, template_id, label, unit, frequency, time_of_day, "
        "target_type, target_value, target_high, is_active, phase, sort_order "
        "FROM plan_metrics WHERE plan_id = %s ORDER BY sort_order ASC, id ASC",
        (plan_id,),
    )
    rows = await cur.fetchall()
    return [_metric_row_to_dict(r) for r in rows]


async def _fetch_phases(conn, plan_id: int) -> list[dict]:
    cur = conn.cursor()
    await cur.execute(
        "SELECT id, plan_id, phase_number, name, focus, actions, day_start, day_end "
        "FROM plan_phases WHERE plan_id = %s ORDER BY phase_number ASC",
        (plan_id,),
    )
    rows = await cur.fetchall()
    return [_phase_row_to_dict(r) for r in rows]


async def get_active_plan(patient_username: str) -> dict | None:
    """Return the active plan for a patient with all child rows, or None."""
    async with get_conn() as conn:
        cur = conn.cursor()
        await cur.execute(
            "SELECT id, patient_username, practitioner_id, version, is_active, "
            "title, rationale, created_at, updated_at FROM plans "
            "WHERE patient_username = %s AND is_active = TRUE "
            "ORDER BY version DESC LIMIT 1",
            (patient_username,),
        )
        plan_row = await cur.fetchone()
        if not plan_row:
            return None
        plan = _plan_row_to_dict(plan_row)
        plan["outcomes"] = await _fetch_outcomes(conn, plan["id"])
        plan["metrics"] = await _fetch_metrics(conn, plan["id"])
        plan["phases"] = await _fetch_phases(conn, plan["id"])
        return plan


async def _insert_outcomes(conn, plan_id: int, outcomes: list[dict]) -> None:
    cur = conn.cursor()
    for o in outcomes:
        await cur.execute(
            "INSERT INTO plan_outcomes (plan_id, biomarker_name, target_value, "
            "target_direction, target_high, unit, target_date, current_value, "
            "current_as_of) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
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


async def _insert_metrics(conn, plan_id: int, metrics: list[dict]) -> None:
    cur = conn.cursor()
    for i, m in enumerate(metrics):
        await cur.execute(
            "INSERT INTO plan_metrics (plan_id, template_id, label, unit, "
            "frequency, time_of_day, target_type, target_value, target_high, "
            "is_active, phase, sort_order) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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
                bool(m.get("is_active", True)),
                m.get("phase"),
                m.get("sort_order", i),
            ),
        )


async def _insert_phases(conn, plan_id: int, phases: list[dict]) -> None:
    cur = conn.cursor()
    for p in phases:
        actions = p.get("actions", [])
        # actions is stored as JSONB; psycopg adapts Python lists as PG
        # arrays, not JSON. Convert to a JSON string for the JSONB column.
        if not isinstance(actions, str):
            actions = json.dumps(actions)
        await cur.execute(
            "INSERT INTO plan_phases (plan_id, phase_number, name, focus, actions, "
            "day_start, day_end) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                plan_id,
                int(p.get("phase_number", 1)),
                p.get("name", ""),
                p.get("focus", ""),
                actions,
                int(p.get("day_start", 1)),
                int(p.get("day_end", 30)),
            ),
        )


async def create_plan(
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
    ts = now()
    async with get_conn() as conn:
        cur = conn.cursor()
        # Determine the next version number.
        await cur.execute(
            "SELECT MAX(version) AS max_v FROM plans WHERE patient_username = %s",
            (patient_username,),
        )
        prior = await cur.fetchone()
        next_version = (prior["max_v"] or 0) + 1
        # Archive any existing active plan.
        await cur.execute(
            "UPDATE plans SET is_active = FALSE WHERE patient_username = %s AND is_active = TRUE",
            (patient_username,),
        )
        await cur.execute(
            "INSERT INTO plans (patient_username, practitioner_id, version, "
            "is_active, title, rationale, created_at, updated_at) "
            "VALUES (%s, %s, %s, TRUE, %s, %s, %s, %s) RETURNING id",
            (patient_username, practitioner_id, next_version, title, rationale, ts, ts),
        )
        plan_id = (await cur.fetchone())["id"]
        await _insert_outcomes(conn, plan_id, outcomes)
        await _insert_metrics(conn, plan_id, metrics)
        await _insert_phases(conn, plan_id, phases)
        # Fetch the complete plan with child rows.
        await cur.execute(
            "SELECT id, patient_username, practitioner_id, version, is_active, "
            "title, rationale, created_at, updated_at FROM plans WHERE id = %s",
            (plan_id,),
        )
        plan = _plan_row_to_dict(await cur.fetchone())
        plan["outcomes"] = await _fetch_outcomes(conn, plan_id)
        plan["metrics"] = await _fetch_metrics(conn, plan_id)
        plan["phases"] = await _fetch_phases(conn, plan_id)
        return plan


async def has_active_plan(patient_username: str) -> bool:
    row = await fetchone(
        "SELECT 1 FROM plans WHERE patient_username = %s AND is_active = TRUE",
        (patient_username,),
    )
    return row is not None


async def get_metric(metric_id: int) -> dict | None:
    row = await fetchone(
        "SELECT id, plan_id, template_id, label, unit, frequency, time_of_day, "
        "target_type, target_value, target_high, is_active, phase, sort_order "
        "FROM plan_metrics WHERE id = %s",
        (metric_id,),
    )
    return _metric_row_to_dict(row) if row else None


async def list_active_metric_ids(patient_username: str) -> list[int]:
    """Return the IDs of all metrics in the patient's active plan."""
    rows = await fetchall(
        "SELECT pm.id FROM plan_metrics pm "
        "JOIN plans p ON pm.plan_id = p.id "
        "WHERE p.patient_username = %s AND p.is_active = TRUE AND pm.is_active = TRUE "
        "ORDER BY pm.sort_order ASC",
        (patient_username,),
    )
    return [r["id"] for r in rows]


# ---------------------------------------------------------------------------
# Plan drafts
# ---------------------------------------------------------------------------
_DRAFT_COLS = (
    "id", "patient_username", "practitioner_id", "title", "rationale",
    "outcomes_json", "metrics_json", "phases_json", "is_published",
    "created_at", "updated_at",
)
_DRAFT_SELECT = ", ".join(_DRAFT_COLS)


async def get_unpublished_draft(patient_username: str) -> dict | None:
    row = await fetchone(
        f"SELECT {_DRAFT_SELECT} FROM plan_drafts "
        "WHERE patient_username = %s AND is_published = FALSE "
        "ORDER BY id DESC LIMIT 1",
        (patient_username,),
    )
    return _draft_row_to_dict(row) if row else None


async def create_draft(
    patient_username: str,
    practitioner_id: int,
    title: str | None = None,
    rationale: str | None = None,
    outcomes: list[dict] | None = None,
    metrics: list[dict] | None = None,
    phases: list[dict] | None = None,
) -> dict:
    """Create a new draft, replacing any existing unpublished draft."""
    ts = now()
    row = await fetchone(
        f"""
        WITH deleted AS (
            DELETE FROM plan_drafts WHERE patient_username = %s AND is_published = FALSE
        )
        INSERT INTO plan_drafts (patient_username, practitioner_id, title,
            rationale, outcomes_json, metrics_json, phases_json, is_published,
            created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s)
        RETURNING {_DRAFT_SELECT}
        """,
        (
            patient_username,
            patient_username,
            practitioner_id,
            title,
            rationale,
            json.dumps(outcomes or []),
            json.dumps(metrics or []),
            json.dumps(phases or []),
            ts,
            ts,
        ),
    )
    return _draft_row_to_dict(row)


async def update_draft(
    patient_username: str,
    title: str | None = None,
    rationale: str | None = None,
    outcomes: list[dict] | None = None,
    metrics: list[dict] | None = None,
    phases: list[dict] | None = None,
) -> dict | None:
    """Update fields on the existing unpublished draft. Only non-None fields
    are updated. Returns the updated draft or None if no draft exists."""
    sets: list[str] = ["updated_at = %s"]
    params: list = [now()]
    if title is not None:
        sets.append("title = %s")
        params.append(title)
    if rationale is not None:
        sets.append("rationale = %s")
        params.append(rationale)
    if outcomes is not None:
        sets.append("outcomes_json = %s")
        params.append(json.dumps(outcomes))
    if metrics is not None:
        sets.append("metrics_json = %s")
        params.append(json.dumps(metrics))
    if phases is not None:
        sets.append("phases_json = %s")
        params.append(json.dumps(phases))
    params.append(patient_username)

    async with get_conn() as conn:
        cur = conn.cursor()
        await cur.execute(
            f"UPDATE plan_drafts SET {', '.join(sets)} "
            f"WHERE patient_username = %s AND is_published = FALSE",
            tuple(params),
        )
        if cur.rowcount == 0:
            return None
        await cur.execute(
            f"SELECT {_DRAFT_SELECT} FROM plan_drafts "
            "WHERE patient_username = %s AND is_published = FALSE "
            "ORDER BY id DESC LIMIT 1",
            (patient_username,),
        )
        row = await cur.fetchone()
    return _draft_row_to_dict(row) if row else None


async def delete_draft(patient_username: str) -> bool:
    async with get_conn() as conn:
        cur = conn.cursor()
        await cur.execute(
            "DELETE FROM plan_drafts WHERE patient_username = %s AND is_published = FALSE",
            (patient_username,),
        )
        return cur.rowcount > 0


async def publish_draft(patient_username: str) -> dict | None:
    """Publish the current unpublished draft: create a new active plan from
    the draft's JSON, mark the draft as published. Returns the new active plan
    or None if no unpublished draft exists."""
    draft = await get_unpublished_draft(patient_username)
    if not draft:
        return None
    plan = await create_plan(
        patient_username=patient_username,
        practitioner_id=draft["practitioner_id"],
        title=draft.get("title"),
        rationale=draft.get("rationale"),
        outcomes=draft.get("outcomes_json") or [],
        metrics=draft.get("metrics_json") or [],
        phases=draft.get("phases_json") or [],
    )
    await execute(
        "UPDATE plan_drafts SET is_published = TRUE, updated_at = %s "
        "WHERE id = %s",
        (now(), draft["id"]),
    )
    return plan


# ---------------------------------------------------------------------------
# Plan suggestions (AI-proposed adjustments for practitioner approval)
# ---------------------------------------------------------------------------
async def add_plan_suggestion(
    patient_username: str,
    practitioner_id: int | None,
    source: str,
    suggestion: dict,
) -> dict:
    ts = now()
    row = await fetchone(
        "INSERT INTO plan_suggestions (patient_username, practitioner_id, "
        "source, suggestion_json, status, created_at) "
        "VALUES (%s, %s, %s, %s, 'pending', %s) RETURNING id",
        (patient_username, practitioner_id, source, json.dumps(suggestion), ts),
    )
    return {
        "id": row["id"],
        "patient_username": patient_username,
        "practitioner_id": practitioner_id,
        "source": source,
        "suggestion": suggestion,
        "status": "pending",
        "created_at": ts,
        "decided_at": None,
        "decided_by": None,
    }


async def list_plan_suggestions(
    patient_username: str, status: str | None = None
) -> list[dict]:
    if status:
        rows = await fetchall(
            "SELECT id, patient_username, practitioner_id, source, "
            "suggestion_json, status, created_at, decided_at, decided_by "
            "FROM plan_suggestions WHERE patient_username = %s AND status = %s "
            "ORDER BY created_at DESC",
            (patient_username, status),
        )
    else:
        rows = await fetchall(
            "SELECT id, patient_username, practitioner_id, source, "
            "suggestion_json, status, created_at, decided_at, decided_by "
            "FROM plan_suggestions WHERE patient_username = %s "
            "ORDER BY created_at DESC",
            (patient_username,),
        )
    out = []
    for r in rows:
        # suggestion_json is JSONB — already a Python dict.
        suggestion = r["suggestion_json"]
        if not isinstance(suggestion, dict):
            try:
                suggestion = json.loads(suggestion) if suggestion else {}
            except (json.JSONDecodeError, TypeError):
                suggestion = {}
        out.append({
            "id": r["id"],
            "patient_username": r["patient_username"],
            "practitioner_id": r["practitioner_id"],
            "source": r["source"],
            "suggestion": suggestion,
            "status": r["status"],
            "created_at": r["created_at"],
            "decided_at": r["decided_at"],
            "decided_by": r["decided_by"],
        })
    return out


async def set_suggestion_status(
    suggestion_id: int, status: str, decided_by: int | None = None
) -> dict | None:
    ts = now()
    await execute(
        "UPDATE plan_suggestions SET status = %s, decided_at = %s, decided_by = %s "
        "WHERE id = %s",
        (status, ts, decided_by, suggestion_id),
    )
    row = await fetchone(
        "SELECT id, patient_username, practitioner_id, source, "
        "suggestion_json, status, created_at, decided_at, decided_by "
        "FROM plan_suggestions WHERE id = %s",
        (suggestion_id,),
    )
    if not row:
        return None
    suggestion = row["suggestion_json"]
    if not isinstance(suggestion, dict):
        try:
            suggestion = json.loads(suggestion) if suggestion else {}
        except (json.JSONDecodeError, TypeError):
            suggestion = {}
    return {
        "id": row["id"],
        "patient_username": row["patient_username"],
        "practitioner_id": row["practitioner_id"],
        "source": row["source"],
        "suggestion": suggestion,
        "status": row["status"],
        "created_at": row["created_at"],
        "decided_at": row["decided_at"],
        "decided_by": row["decided_by"],
    }


# ---------------------------------------------------------------------------
# Daily logs (metric_id-aware helpers)
# ---------------------------------------------------------------------------
async def save_metric_log(
    username: str,
    iso_date: str,
    metric_id: int,
    log_json: str,
) -> None:
    """Upsert a daily log row keyed by (username, date, metric_id).

    Keeps the old ``domain`` column in sync by looking up the metric's
    template_id (so legacy code paths that read by domain still work during
    migration). The primary key is (username, date, domain).
    """
    async with get_conn() as conn:
        cur = conn.cursor()
        # Look up the metric to get a domain-like value for the legacy column.
        await cur.execute(
            "SELECT template_id FROM plan_metrics WHERE id = %s", (metric_id,)
        )
        metric = await cur.fetchone()
        domain = metric["template_id"] if metric else "other"
        await cur.execute(
            """
            INSERT INTO daily_logs (username, date, domain, metric_id, log_json, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(username, date, domain) DO UPDATE SET
                metric_id = EXCLUDED.metric_id,
                log_json = EXCLUDED.log_json,
                updated_at = EXCLUDED.updated_at
            """,
            (username, iso_date, domain, metric_id, log_json, now()),
        )


async def get_metric_logs(username: str, iso_date: str) -> dict[int, list[dict]]:
    """Return all metric logs for a user on a date, keyed by metric_id."""
    rows = await fetchall(
        "SELECT metric_id, log_json FROM daily_logs "
        "WHERE username = %s AND date = %s AND metric_id IS NOT NULL",
        (username, iso_date),
    )
    out: dict[int, list[dict]] = {}
    for row in rows:
        mid = row["metric_id"]
        if mid is None:
            continue
        lj = row["log_json"]
        # log_json is JSONB — already a Python list.
        out[mid] = lj if isinstance(lj, list) else []
    return out


async def get_recent_metric_logs(
    username: str, metric_id: int, days: int
) -> list[dict]:
    """Return the last `days` days of logs for a single metric, oldest first."""
    rows = await fetchall(
        "SELECT date, log_json FROM daily_logs "
        "WHERE username = %s AND metric_id = %s "
        "ORDER BY date DESC LIMIT %s",
        (username, metric_id, days),
    )
    out = [{"date": r["date"], "entries": r["log_json"]} for r in rows]
    out.reverse()
    return out


async def get_all_metric_logs_range(
    username: str, metric_id: int, days: int
) -> list[dict]:
    """Return logs for a metric over the last `days` days (same as recent)."""
    return await get_recent_metric_logs(username, metric_id, days)


# ---------------------------------------------------------------------------
# Migration: create default plans for existing onboarded patients
# ---------------------------------------------------------------------------
async def _migrate_domain_logs_for_patient(
    conn,
    patient_username: str,
    plan_id: int,
    metric_id_by_template: dict[str, int],
) -> int:
    """Re-point existing daily_logs rows (with domain values) to the new
    metric IDs in the default plan. Returns the number of rows updated."""
    from app.metric_templates import DOMAIN_TO_TEMPLATE
    cur = conn.cursor()
    updated = 0
    for domain, template_id in DOMAIN_TO_TEMPLATE.items():
        metric_id = metric_id_by_template.get(template_id)
        if metric_id is None:
            continue
        await cur.execute(
            "UPDATE daily_logs SET metric_id = %s "
            "WHERE username = %s AND domain = %s AND metric_id IS NULL",
            (metric_id, patient_username, domain),
        )
        updated += cur.rowcount
    return updated


async def create_default_plan_for_patient(
    patient_username: str, plan_json: dict | None
) -> dict | None:
    """Create a default plan for an existing onboarded patient, mapping the
    old 6 wellness domains to template metrics. Idempotent — skips if the
    patient already has an active plan."""
    from app.metric_templates import DOMAIN_TO_TEMPLATE, get_template

    if await has_active_plan(patient_username):
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

    plan = await create_plan(
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
    async with get_conn() as conn:
        updated = await _migrate_domain_logs_for_patient(
            conn, patient_username, plan["id"], metric_id_by_template
        )
    return plan


async def run_plan_migration() -> None:
    """Run the migration: for each onboarded patient with no active plan,
    create a default plan and re-point logs. Idempotent."""
    from app.database import get_profile  # avoid circular import at module load
    rows = await fetchall(
        "SELECT username FROM user_profiles WHERE onboarded = TRUE"
    )
    for row in rows:
        username = row["username"]
        if await has_active_plan(username):
            continue
        profile_data = await get_profile(username)
        plan_json = profile_data.get("plan") if profile_data else None
        await create_default_plan_for_patient(username, plan_json)
