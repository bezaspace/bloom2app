"""Computed analytics for tracking plans: per-metric adherence, overall
adherence score, trend detection, and correlation analysis.

These are pure deterministic functions that read logs + plan + biomarkers
and return structured analytics. The LLM never does the math — it receives
the output of these functions and focuses on interpretation (see
``plan_insights.py``).

Adherence rules (per metric target_type):
  - minimum: min(1.0, actual / target)
  - maximum: 1.0 if actual <= target else (target / actual)
  - range:   1.0 if target_low <= actual <= target_high else 0.0
  - count:   min(1.0, actual / target)
  - exact:   1.0 if actual == target else 0.0
  - none:    no adherence (tracked for pattern detection only)
  - target:  treated like minimum for adherence (patient-specific goal)
"""

from __future__ import annotations

import asyncio
import math
from datetime import date, timedelta
from typing import Optional

from app.plan_db import (
    get_active_plan,
    get_metric_logs,
    get_recent_metric_logs,
)


# ---------------------------------------------------------------------------
# Adherence
# ---------------------------------------------------------------------------
def _sum_actual(entries: list[dict]) -> float:
    """Sum the value of completed entries (or all entries if none marked)."""
    total = 0.0
    for e in entries:
        if e.get("completed", True):
            v = e.get("value")
            if v is not None:
                total += float(v)
    return total


def _count_actual(entries: list[dict]) -> float:
    """Count completed entries."""
    return float(sum(1 for e in entries if e.get("completed", True)))


def _last_value(entries: list[dict]) -> float | None:
    """Return the value of the most recent entry (for mood, BP, weight)."""
    if not entries:
        return None
    # Take the last entry's value.
    for e in reversed(entries):
        v = e.get("value")
        if v is not None:
            return float(v)
    return None


def _actual_for_metric(metric: dict, entries: list[dict]) -> float | None:
    """Compute the 'actual' value for a metric from today's entries.

    For cumulative metrics (steps, minutes, meals, doses, water, carbs per
    meal aggregated) we sum. For point-in-time metrics (mood, BP, weight,
    stress, anxiety, sleep quality) we take the last value. For count-type
    metrics (medication_adherence, meals_logged, therapy_homework) we count
    completed entries.
    """
    target_type = metric.get("target_type", "minimum")
    template_id = metric.get("template_id", "")
    if target_type == "count":
        return _count_actual(entries)
    # Point-in-time metrics: take the last value.
    point_in_time = {
        "mood", "stress_level", "anxiety_level", "sleep_quality",
        "blood_pressure_systolic", "blood_pressure_diastolic",
        "resting_heart_rate", "weight", "symptom_severity",
    }
    if template_id in point_in_time:
        return _last_value(entries)
    # Default: sum the values.
    return _sum_actual(entries)


def _adherence_for_metric(metric: dict, actual: float | None) -> float | None:
    """Return adherence as a 0..1 fraction, or None if not computable."""
    if actual is None:
        return None
    target_type = metric.get("target_type", "minimum")
    target = metric.get("target_value")
    target_high = metric.get("target_high")
    if target_type == "none":
        return None
    if target_type == "range":
        if target is None or target_high is None:
            return None
        return 1.0 if target <= actual <= target_high else 0.0
    if target_type == "exact":
        if target is None:
            return None
        return 1.0 if abs(actual - target) < 1e-9 else 0.0
    # minimum / maximum / count / target
    if target is None or target == 0:
        return None
    if target_type == "maximum":
        return 1.0 if actual <= target else (target / actual if actual > 0 else 0.0)
    # minimum, count, target
    return min(1.0, actual / target)


async def compute_adherence_for_date(
    patient_username: str, iso_date: str
) -> dict:
    """Per-metric adherence % for a given date + overall adherence score.

    Returns:
        dict with: date, metrics (list of {metric_id, label, template_id,
        target_type, target, actual, adherence (0..1 or null), unit}),
        overall (0..1 or null).
    """
    plan = await get_active_plan(patient_username)
    if not plan:
        return {"date": iso_date, "metrics": [], "overall": None}
    logs_by_metric = await get_metric_logs(patient_username, iso_date)
    out_metrics = []
    weighted_sum = 0.0
    weight_total = 0.0
    for m in plan["metrics"]:
        if not m.get("is_active", True):
            continue
        entries = logs_by_metric.get(m["id"], [])
        actual = _actual_for_metric(m, entries)
        adherence = _adherence_for_metric(m, actual)
        out_metrics.append(
            {
                "metric_id": m["id"],
                "label": m["label"],
                "template_id": m["template_id"],
                "unit": m["unit"],
                "frequency": m["frequency"],
                "target_type": m["target_type"],
                "target": m.get("target_value"),
                "target_high": m.get("target_high"),
                "actual": actual,
                "adherence": adherence,
                "phase": m.get("phase"),
            }
        )
        if adherence is not None:
            freq = m.get("frequency", "daily")
            weight = 1.0 if freq == "daily" else 0.5
            weighted_sum += adherence * weight
            weight_total += weight
    overall = (weighted_sum / weight_total) if weight_total > 0 else None
    return {
        "date": iso_date,
        "plan_id": plan["id"],
        "plan_title": plan.get("title"),
        "metrics": out_metrics,
        "overall": overall,
    }


async def compute_adherence_summary(
    patient_username: str, days: int = 7
) -> dict:
    """Per-metric adherence averaged over the last N days + overall average."""
    plan = await get_active_plan(patient_username)
    if not plan:
        return {"days": days, "metrics": [], "overall": None}
    today = date.today()
    per_metric_sums: dict[int, list[float]] = {}
    per_metric_meta: dict[int, dict] = {}
    overall_sums: list[float] = []
    for i in range(days):
        d = today - timedelta(days=i)
        ad = await compute_adherence_for_date(patient_username, d.isoformat())
        if ad.get("overall") is not None:
            overall_sums.append(ad["overall"])
        for m in ad["metrics"]:
            if m["adherence"] is not None:
                per_metric_sums.setdefault(m["metric_id"], []).append(m["adherence"])
            per_metric_meta[m["metric_id"]] = {
                "label": m["label"],
                "template_id": m["template_id"],
                "unit": m["unit"],
                "target_type": m["target_type"],
                "target": m["target"],
            }
    out_metrics = []
    for mid, vals in per_metric_sums.items():
        meta = per_metric_meta[mid]
        avg = sum(vals) / len(vals) if vals else None
        out_metrics.append({"metric_id": mid, **meta, "adherence_avg": avg, "days_with_data": len(vals)})
    overall_avg = (sum(overall_sums) / len(overall_sums)) if overall_sums else None
    return {"days": days, "metrics": out_metrics, "overall": overall_avg}


# ---------------------------------------------------------------------------
# Trend detection
# ---------------------------------------------------------------------------
def _pearson(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation coefficient. Returns None if < 2 points or zero variance."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _slope(values: list[float]) -> float | None:
    """Simple linear regression slope against index (0..n-1)."""
    n = len(values)
    if n < 2:
        return None
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(values) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, values))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    return num / den


async def compute_trends(patient_username: str, days: int = 14) -> dict:
    """Trend analysis per metric: direction, magnitude, last 7 vs prior 7 days."""
    plan = await get_active_plan(patient_username)
    if not plan:
        return {"days": days, "trends": []}
    today = date.today()
    out = []
    for m in plan["metrics"]:
        if not m.get("is_active", True):
            continue
        # Gather daily aggregated values for the last `days` days.
        daily_values: list[tuple[str, float]] = []
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            logs = await get_metric_logs(patient_username, d.isoformat())
            entries = logs.get(m["id"], [])
            actual = _actual_for_metric(m, entries)
            if actual is not None:
                daily_values.append((d.isoformat(), actual))
        if len(daily_values) < 2:
            out.append(
                {
                    "metric_id": m["id"],
                    "label": m["label"],
                    "template_id": m["template_id"],
                    "unit": m["unit"],
                    "direction": "unknown",
                    "magnitude": None,
                    "recent_avg": None,
                    "prior_avg": None,
                    "slope": None,
                    "n_points": len(daily_values),
                }
            )
            continue
        values = [v for _, v in daily_values]
        slope = _slope(values)
        mid = len(values) // 2
        recent_vals = values[mid:] if mid > 0 else values
        prior_vals = values[:mid] if mid > 0 else []
        recent_avg = sum(recent_vals) / len(recent_vals) if recent_vals else None
        prior_avg = sum(prior_vals) / len(prior_vals) if prior_vals else None
        magnitude = (recent_avg - prior_avg) if (recent_avg is not None and prior_avg is not None) else None
        if slope is None:
            direction = "steady"
        elif slope > 0:
            direction = "up"
        elif slope < 0:
            direction = "down"
        else:
            direction = "steady"
        out.append(
            {
                "metric_id": m["id"],
                "label": m["label"],
                "template_id": m["template_id"],
                "unit": m["unit"],
                "direction": direction,
                "magnitude": round(magnitude, 4) if magnitude is not None else None,
                "recent_avg": round(recent_avg, 4) if recent_avg is not None else None,
                "prior_avg": round(prior_avg, 4) if prior_avg is not None else None,
                "slope": round(slope, 4) if slope is not None else None,
                "n_points": len(daily_values),
            }
        )
    return {"days": days, "trends": out}


# ---------------------------------------------------------------------------
# Correlation analysis
# ---------------------------------------------------------------------------
async def compute_correlations(patient_username: str, days: int = 30) -> dict:
    """Pairwise Pearson correlation coefficients between daily-aggregated
    metric values. Surfaces pairs with |r| >= 0.4 and >= 14 overlapping
    data points.
    """
    plan = await get_active_plan(patient_username)
    if not plan:
        return {"days": days, "correlations": []}
    today = date.today()
    # Build per-metric daily value maps: {metric_id: {date_iso: value}}.
    per_metric: dict[int, dict[str, float]] = {}
    metric_meta: dict[int, dict] = {}
    for m in plan["metrics"]:
        if not m.get("is_active", True):
            continue
        metric_meta[m["id"]] = {
            "label": m["label"],
            "template_id": m["template_id"],
            "unit": m["unit"],
        }
        daily: dict[str, float] = {}
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            logs = await get_metric_logs(patient_username, d.isoformat())
            entries = logs.get(m["id"], [])
            actual = _actual_for_metric(m, entries)
            if actual is not None:
                daily[d.isoformat()] = actual
        per_metric[m["id"]] = daily
    # Pairwise correlations.
    out = []
    mids = list(per_metric.keys())
    for i in range(len(mids)):
        for j in range(i + 1, len(mids)):
            a, b = mids[i], mids[j]
            da, db = per_metric[a], per_metric[b]
            common = sorted(set(da.keys()) & set(db.keys()))
            if len(common) < 14:
                continue
            xs = [da[d] for d in common]
            ys = [db[d] for d in common]
            r = _pearson(xs, ys)
            if r is None or abs(r) < 0.4:
                continue
            out.append(
                {
                    "metric_a": metric_meta[a],
                    "metric_b": metric_meta[b],
                    "r": round(r, 3),
                    "n": len(common),
                    "direction": "positive" if r > 0 else "negative",
                }
            )
    # Sort by absolute r descending.
    out.sort(key=lambda c: abs(c["r"]), reverse=True)
    return {"days": days, "correlations": out}


# ---------------------------------------------------------------------------
# Outcome target progress
# ---------------------------------------------------------------------------
async def compute_biomarker_progress(patient_username: str) -> dict:
    """Outcome target progress: current vs target for each plan outcome, with
    trajectory (delta from prior reading, projected achievement)."""
    from app.database import list_biomarkers_by_name
    plan = await get_active_plan(patient_username)
    if not plan:
        return {"outcomes": []}
    out = []
    for o in plan["outcomes"]:
        name = o["biomarker_name"]
        readings = await list_biomarkers_by_name(patient_username, name)
        latest = readings[-1] if readings else None
        prior = readings[-2] if len(readings) >= 2 else None
        current = latest["value"] if latest else o.get("current_value")
        target = o["target_value"]
        direction = o["target_direction"]
        target_high = o.get("target_high")
        # Determine if on track.
        on_track = None
        if current is not None:
            if direction == "below":
                on_track = current <= target
            elif direction == "above":
                on_track = current >= target
            elif direction == "range" and target_high is not None:
                on_track = target <= current <= target_high
        delta = (latest["value"] - prior["value"]) if (latest and prior) else None
        out.append(
            {
                "biomarker_name": name,
                "target_value": target,
                "target_direction": direction,
                "target_high": target_high,
                "unit": o["unit"],
                "target_date": o.get("target_date"),
                "current_value": current,
                "current_as_of": latest["measured_at"] if latest else o.get("current_as_of"),
                "prior_value": prior["value"] if prior else None,
                "delta": round(delta, 4) if delta is not None else None,
                "on_track": on_track,
                "n_readings": len(readings),
            }
        )
    return {"outcomes": out}
