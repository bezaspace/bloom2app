"""Tools for the Bloom healthcare voice agent.

These are ADK FunctionTools that the live agent calls during the voice
conversation. ADK's ``run_live()`` executes them automatically when the model
emits a function-call.

Two groups:

1. **Onboarding tools** — read/write the per-user onboarding profile, plan, and
   document summary. Used during the first session.
2. **Progress tools** — read today's logs/schedule/biomarker trends/streaks and
   write voice-logged entries to ``daily_logs``. These bridge the voice agent
   and the dashboard so Bloom can speak about real progress and accept logs by
   voice.

The username is injected into the session state as ``"username"`` by the
WebSocket handler in ``main.py`` at session creation time, so the tools can
read it via ``tool_context.state.get("username")``.

Tool responses are kept compact and human-readable (with a ``summary`` string)
because they are spoken back to the model — we do not want Bloom reading raw
JSON tables aloud.
"""

import json
import logging
import time
from datetime import date, timedelta

from google.adk.tools import ToolContext

from app.database import (
    get_daily_logs,
    get_daily_schedule,
    get_profile,
    get_recent_daily_logs,
    list_biomarkers,
    save_daily_log,
    save_profile,
)
from app.dashboard.schemas import WELLNESS_DOMAINS

logger = logging.getLogger("bloom2.tools")


def _today_iso() -> str:
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Onboarding tools
# ---------------------------------------------------------------------------
async def get_user_profile(tool_context: ToolContext) -> dict:
    """Returns the current user's onboarding status, profile, plan, and document summary.

    Call this at the start of a session to decide whether to run onboarding.
    If ``onboarded`` is false or ``profile`` is null, the user needs onboarding.
    If ``onboarded`` is true, ``profile`` and ``plan`` contain the stored data.

    Returns:
        dict with keys: onboarded (bool), profile (dict|null), plan (dict|null),
        doc_summary (dict|null).
    """
    username = tool_context.state.get("username")
    if not username:
        return {"onboarded": False, "profile": None, "plan": None, "doc_summary": None}

    profile_data = await get_profile(username)
    if not profile_data:
        return {"onboarded": False, "profile": None, "plan": None, "doc_summary": None}
    return profile_data


async def get_document_summary(tool_context: ToolContext) -> dict:
    """Returns the structured summary extracted from the user's uploaded health documents.

    Call this after the user confirms they have uploaded documents (or says they
    want to skip) to incorporate medical context into the 90-day plan. If no
    documents have been uploaded, returns ``{"available": false}``.

    Returns:
        dict with keys: available (bool), summary (dict|null).
    """
    username = tool_context.state.get("username")
    if not username:
        return {"available": False, "summary": None}

    profile_data = await get_profile(username)
    if not profile_data or not profile_data.get("doc_summary"):
        return {"available": False, "summary": None}
    return {"available": True, "summary": profile_data["doc_summary"]}


async def finalize_onboarding(
    profile_json: str,
    plan_json: str,
    tool_context: ToolContext = None,
) -> dict:
    """Saves the user's onboarding profile and 90-day plan, marking onboarding complete.

    Call this once you have asked all onboarding questions (max 5) and checked
    for any uploaded documents via get_document_summary. The profile and plan
    should be JSON strings. The plan should cover a 90-day period.

    Args:
        profile_json: A JSON string of the user's profile (goal, activity level,
            sleep/stress, conditions/medications, diet/constraints).
        plan_json: A JSON string of the 90-day wellness plan.

    Returns:
        dict with keys: status ("success"|"error"), message (str).
    """
    username = tool_context.state.get("username")
    if not username:
        return {"status": "error", "message": "No authenticated user in session."}

    # Validate that the inputs are valid JSON before storing.
    try:
        json.loads(profile_json)
        json.loads(plan_json)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON: {e}"}

    # Preserve any existing doc_summary when finalizing.
    existing = await get_profile(username)
    doc_summary_json = (
        json.dumps(existing["doc_summary"]) if existing and existing.get("doc_summary") else None
    )

    await save_profile(
        username=username,
        profile_json=profile_json,
        plan_json=plan_json,
        doc_summary_json=doc_summary_json,
        onboarded=True,
    )
    logger.info("Onboarding finalized for user %s", username)
    return {
        "status": "success",
        "message": "Profile and 90-day plan saved successfully.",
    }


# ---------------------------------------------------------------------------
# Progress tools (read) — "Bloom knows your progress"
# ---------------------------------------------------------------------------
async def get_today_progress(tool_context: ToolContext) -> dict:
    """Returns a compact summary of the user's wellness progress for today.

    Call this at the start of a session for an onboarded user (after
    get_user_profile confirms onboarding) so you can greet them with real
    progress: which schedule items are done, per-domain actuals vs targets,
    and today's mood. The ``summary`` field is a ready-to-speak sentence.

    Returns:
        dict with: date, day_of_plan, phase, focus_today, schedule_items
        (list of {time, title, domain, done}), domain_totals (per-domain
        actual/target/unit), mood (int|null), completed_count, total_items,
        and a human-readable summary string. Returns {"available": false} if
        the user is not onboarded or has no schedule yet.
    """
    username = tool_context.state.get("username")
    if not username:
        return {"available": False, "summary": "No authenticated user."}

    profile_data = await get_profile(username)
    if not profile_data or not profile_data.get("onboarded"):
        return {"available": False, "summary": "User not onboarded yet."}

    iso_date = _today_iso()
    schedule = await get_daily_schedule(username, iso_date)
    logs = await get_daily_logs(username, iso_date)

    if not schedule:
        return {
            "available": False,
            "date": iso_date,
            "summary": "No schedule generated for today yet.",
        }

    # Build a set of completed schedule-item titles (entries keyed by title).
    completed_keys: set[str] = set()
    for entries in logs.values():
        for e in entries:
            if e.get("completed"):
                completed_keys.add(e.get("key"))

    items_out = []
    completed_count = 0
    for item in schedule.get("items", []):
        done = item.get("title") in completed_keys
        if done:
            completed_count += 1
        items_out.append(
            {
                "time": item.get("time", ""),
                "title": item.get("title", ""),
                "domain": item.get("domain", ""),
                "done": done,
            }
        )

    # Per-domain actual vs target.
    targets = schedule.get("daily_targets", {}) or {}
    domain_totals = {}
    for domain in ("workout", "diet", "meditation", "medication"):
        entries = logs.get(domain, [])
        actual = sum((e.get("value") or 0) for e in entries)
        # Map domain to its target metric in daily_targets.
        target_key = {
            "workout": "workout_minutes",
            "diet": "meals_logged",
            "meditation": "meditation_minutes",
            "medication": "meds_taken",
        }.get(domain)
        target = targets.get(target_key) if target_key else None
        unit = {"workout": "min", "diet": "meals", "meditation": "min",
                "medication": "doses"}.get(domain, "")
        if target is not None or actual > 0:
            domain_totals[domain] = {"actual": actual, "target": target, "unit": unit}

    # Mood (mental_health domain, entry with key "mood").
    mood = None
    for e in logs.get("mental_health", []):
        if e.get("key") == "mood":
            mood = e.get("value")
            break

    # Build a compact summary string for the model to speak.
    bits = []
    if schedule.get("items"):
        bits.append(f"{completed_count} of {len(schedule['items'])} schedule items done")
    for domain, t in domain_totals.items():
        if t["target"]:
            bits.append(f"{domain} {t['actual']}/{t['target']} {t['unit']}")
        elif t["actual"]:
            bits.append(f"{domain} {t['actual']} {t['unit']}")
    if mood is not None:
        bits.append(f"mood {mood}/5")
    summary = ". ".join(bits) + "." if bits else "Nothing logged yet today."

    return {
        "available": True,
        "date": iso_date,
        "day_of_plan": schedule.get("day_of_plan", 1),
        "phase": schedule.get("phase", ""),
        "focus_today": schedule.get("focus_today", ""),
        "schedule_items": items_out,
        "domain_totals": domain_totals,
        "mood": mood,
        "completed_count": completed_count,
        "total_items": len(schedule.get("items", [])),
        "summary": summary,
    }


async def get_streaks(tool_context: ToolContext) -> dict:
    """Returns current completion streaks per wellness domain.

    A "streak" is the number of consecutive days (ending today) on which the
    user logged at least one completed entry for that domain. Use this to give
    encouragement like "you've meditated three days in a row." The ``summary``
    field is a ready-to-speak sentence.

    Returns:
        dict with: streaks (list of {domain, current_streak, last_logged}) and
        a summary string. Returns {"available": false} if not onboarded.
    """
    username = tool_context.state.get("username")
    if not username:
        return {"available": False, "summary": "No authenticated user."}

    profile_data = await get_profile(username)
    if not profile_data or not profile_data.get("onboarded"):
        return {"available": False, "summary": "User not onboarded yet."}

    today = date.today()
    streaks = []
    for domain in ("workout", "diet", "meditation", "medication", "mental_health"):
        rows = await get_recent_daily_logs(username, domain, 30)
        # Build a set of active dates (at least one completed entry).
        active_days: set[str] = set()
        for row in rows:
            if any(e.get("completed") for e in row.get("entries", [])):
                active_days.add(row["date"])
        # Count consecutive days ending today.
        streak = 0
        d = today
        while d.isoformat() in active_days:
            streak += 1
            d -= timedelta(days=1)
        # If today not logged, report when they last logged.
        last_logged = "today" if today.isoformat() in active_days else None
        if last_logged is None and active_days:
            last_logged = max(active_days)
        streaks.append(
            {
                "domain": domain,
                "current_streak": streak,
                "last_logged": last_logged,
            }
        )

    # Summary highlighting streaks >= 2.
    hot = [s for s in streaks if s["current_streak"] >= 2]
    if hot:
        summary = ", ".join(
            f"{s['domain']} {s['current_streak']}-day streak" for s in hot
        ) + "."
    else:
        active_today = [s["domain"] for s in streaks if s["last_logged"] == "today"]
        if active_today:
            summary = f"Logged today: {', '.join(active_today)}."
        else:
            summary = "No streaks yet — today is a great day to start one."

    return {"available": True, "streaks": streaks, "summary": summary}


async def get_biomarker_trends(tool_context: ToolContext) -> dict:
    """Returns biomarker trend deltas (latest vs prior reading) for each marker.

    Use this to comment on real lab progress, e.g. "your HbA1c came down 0.3
    points." Only markers with at least two readings include a delta. The
    ``summary`` field is a ready-to-speak sentence.

    Returns:
        dict with: trends (list of {name, latest, prior, unit, delta, direction,
        status}) and a summary string. Returns {"available": false, "count": 0}
        if not onboarded or no biomarkers.
    """
    username = tool_context.state.get("username")
    if not username:
        return {"available": False, "summary": "No authenticated user.", "count": 0}

    profile_data = await get_profile(username)
    if not profile_data or not profile_data.get("onboarded"):
        return {"available": False, "summary": "User not onboarded yet.", "count": 0}

    rows = await list_biomarkers(username)
    if not rows:
        return {
            "available": False,
            "summary": "No biomarkers uploaded yet.",
            "count": 0,
        }

    # Group by name. list_biomarkers returns newest measurement first per name.
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["name"], []).append(r)

    trends = []
    for name, readings in groups.items():
        # readings are newest-first; latest = readings[0], prior = readings[1].
        latest = readings[0]
        prior = readings[1] if len(readings) > 1 else None
        entry = {
            "name": name,
            "latest": latest["value"],
            "prior": prior["value"] if prior else None,
            "unit": latest["unit"],
            "delta": None,
            "direction": "unknown",
            "status": latest.get("status", "unknown"),
        }
        if prior is not None:
            delta = round(latest["value"] - prior["value"], 4)
            entry["delta"] = delta
            entry["direction"] = "down" if delta < 0 else ("up" if delta > 0 else "steady")
        trends.append(entry)

    # Summary: mention markers with a delta, prioritizing notable changes.
    changed = [t for t in trends if t["delta"] is not None and t["direction"] != "steady"]
    if changed:
        parts = []
        for t in changed:
            arrow = "down" if t["delta"] < 0 else "up"
            parts.append(f"{t['name']} {arrow} {abs(t['delta'])} {t['unit']} to {t['latest']} {t['unit']} ({t['status']})")
        summary = "; ".join(parts) + "."
    else:
        summary = f"{len(trends)} biomarker(s) on file, no changes between readings."

    return {"available": True, "trends": trends, "count": len(trends), "summary": summary}


# ---------------------------------------------------------------------------
# Progress tools (write) — voice-logged entries
# ---------------------------------------------------------------------------
async def log_wellness_entry(
    domain: str,
    value: float | None = None,
    note: str | None = None,
    completed: bool = True,
    date: str | None = None,
    tool_context: ToolContext = None,
) -> dict:
    """Logs a wellness activity the user reports by voice (e.g. "I just meditated for 15 minutes").

    Appends one entry to the user's daily log for the given domain and date
    (default today) WITHOUT erasing existing entries — it reads the current
    entries, appends the new one, and writes the full list back. The entry is
    tagged with note "via voice" so the dashboard can badge it.

    ALWAYS confirm with the user in speech BEFORE calling this tool (e.g.
    "Got it — 15 minutes of meditation, logging that now") so a misheard
    utterance does not create a junk entry.

    Args:
        domain: One of: workout, diet, medication, mental_health, meditation,
            other.
        value: Quantitative actual value if applicable (e.g. minutes meditated,
            calories, 1 for one meal/dose). Omit for a simple check-off.
        note: Optional free-text note. If omitted, "via voice" is used.
        completed: Whether the activity was completed (default true).
        date: ISO date (YYYY-MM-DD) the log is for. Defaults to today.

    Returns:
        dict with: status ("success"|"error"), message, and a summary string.
    """
    username = tool_context.state.get("username")
    if not username:
        return {"status": "error", "message": "No authenticated user in session."}

    if domain not in WELLNESS_DOMAINS:
        return {
            "status": "error",
            "message": f"Invalid domain '{domain}'. Must be one of: {list(WELLNESS_DOMAINS)}.",
        }

    iso_date = date or _today_iso()

    # Read existing entries for this domain/date so we append rather than wipe.
    all_logs = await get_daily_logs(username, iso_date)
    existing = list(all_logs.get(domain, []))

    entry = {
        "key": f"voice_{int(time.time() * 1000)}",
        "completed": completed,
        "value": value,
        "note": note if note is not None else "via voice",
    }
    existing.append(entry)
    await save_daily_log(username, iso_date, domain, json.dumps(existing))

    val_str = f" ({value})" if value is not None else ""
    logger.info("Voice log for %s: %s%s on %s", username, domain, val_str, iso_date)
    return {
        "status": "success",
        "message": f"Logged {domain}{val_str} for {iso_date}.",
        "summary": f"Logged {domain}{val_str} for {iso_date}.",
    }


async def log_mood(
    score: int,
    note: str | None = None,
    tool_context: ToolContext = None,
) -> dict:
    """Logs the user's mood for today (1-5 scale) by voice.

    Replaces any prior mood entry for today (the dashboard's mood card uses the
    entry with key "mood"). Use this when the user says something like "I'm
    feeling a 4 today."

    Args:
        score: Mood score from 1 (low) to 5 (great).
        note: Optional free-text note.

    Returns:
        dict with: status ("success"|"error"), message, and a summary string.
    """
    username = tool_context.state.get("username")
    if not username:
        return {"status": "error", "message": "No authenticated user in session."}

    if not 1 <= score <= 5:
        return {"status": "error", "message": "Mood score must be between 1 and 5."}

    iso_date = _today_iso()
    all_logs = await get_daily_logs(username, iso_date)
    existing = [e for e in all_logs.get("mental_health", []) if e.get("key") != "mood"]
    existing.append(
        {
            "key": "mood",
            "completed": True,
            "value": float(score),
            "note": note if note is not None else "via voice",
        }
    )
    await save_daily_log(username, iso_date, "mental_health", json.dumps(existing))

    logger.info("Voice mood log for %s: %d on %s", username, score, iso_date)
    return {
        "status": "success",
        "message": f"Logged mood {score}/5 for {iso_date}.",
        "summary": f"Logged mood {score}/5 for {iso_date}.",
    }
