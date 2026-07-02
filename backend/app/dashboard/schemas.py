"""Pydantic schemas for the dashboard feature.

These models are used in three places:
  1. As ``response_schema`` for Gemini Flash-Lite structured-output calls
     (``DailySchedule``, ``BiomarkerExtraction``).
  2. As request/response bodies for the dashboard REST endpoints in
     ``main.py``.
  3. As the shape of the JSON persisted in the SQLite ``daily_schedules`` and
     ``daily_logs`` tables.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

# The six wellness domains tracked across the dashboard. Kept as plain strings
# (not an enum) so they serialize cleanly to JSON for storage and so the AI
# generator can emit them directly.
WELLNESS_DOMAINS = (
    "workout",
    "diet",
    "medication",
    "mental_health",
    "meditation",
    "other",
)


# ---------------------------------------------------------------------------
# Daily schedule (AI-generated, cached per user per day)
# ---------------------------------------------------------------------------
class ScheduleItem(BaseModel):
    """A single timed entry in the user's day."""

    time: str = Field(
        ...,
        description="24-hour local time in HH:MM format, e.g. '07:00'.",
    )
    title: str = Field(..., description="Short human-readable title, e.g. 'Morning walk'.")
    domain: str = Field(
        ...,
        description=(
            "Wellness domain this item belongs to. One of: "
            "workout, diet, medication, mental_health, meditation, other."
        ),
    )
    duration_min: Optional[int] = Field(
        default=None,
        description="Planned duration in minutes, if applicable.",
    )
    detail: str = Field(
        default="",
        description="One-sentence description of what to do and why.",
    )
    target: Optional[dict] = Field(
        default=None,
        description=(
            "Optional quantitative target, e.g. {'steps': 5000} or "
            "{'calories': 400} or {'minutes': 20}."
        ),
    )


class DailySchedule(BaseModel):
    """The full AI-generated plan for a single day."""

    date: str = Field(..., description="ISO date string (YYYY-MM-DD) this schedule is for.")
    day_of_plan: int = Field(
        ...,
        description="Which day of the 90-day plan this is (1-90). 1 if unknown.",
    )
    phase: str = Field(
        ...,
        description="Current plan phase name, e.g. 'Phase 1: Days 1-30'.",
    )
    focus_today: str = Field(
        ...,
        description="One-sentence focus for today, derived from the plan phase.",
    )
    items: list[ScheduleItem] = Field(
        default_factory=list,
        description="Ordered list of scheduled items across the day.",
    )
    daily_targets: dict = Field(
        default_factory=dict,
        description=(
            "Aggregate daily targets keyed by metric, e.g. "
            "{'workout_minutes': 30, 'meditation_minutes': 15, 'meals_logged': 3}."
        ),
    )
    motivation_note: str = Field(
        default="",
        description="A short, encouraging note for the user (1-2 sentences).",
    )


# ---------------------------------------------------------------------------
# Biomarker extraction (structured pass over uploaded lab documents)
# ---------------------------------------------------------------------------
class BiomarkerReading(BaseModel):
    """A single biomarker value parsed from a lab document."""

    name: str = Field(
        ...,
        description="Standardized biomarker name, e.g. 'HbA1c', 'LDL Cholesterol', 'Vitamin D (25-OH)'.",
    )
    value: float = Field(..., description="Numeric value of the reading.")
    unit: str = Field(..., description="Unit of measurement, e.g. '%', 'mg/dL', 'nmol/L'.")
    ref_low: Optional[float] = Field(
        default=None,
        description="Lower bound of the reference range printed on the report, if any.",
    )
    ref_high: Optional[float] = Field(
        default=None,
        description="Upper bound of the reference range printed on the report, if any.",
    )
    optimal_low: Optional[float] = Field(
        default=None,
        description="Lower bound of an optimal range if the report specifies one. Else null.",
    )
    optimal_high: Optional[float] = Field(
        default=None,
        description="Upper bound of an optimal range if the report specifies one. Else null.",
    )
    measured_at: Optional[str] = Field(
        default=None,
        description="Date the sample was collected (YYYY-MM-DD) if present in the document.",
    )
    source_doc: str = Field(
        default="",
        description="Filename of the source document this reading was extracted from.",
    )


class BiomarkerExtraction(BaseModel):
    """Wrapper used as the Gemini response_schema for biomarker extraction."""

    readings: list[BiomarkerReading] = Field(
        default_factory=list,
        description="All biomarker readings found in the document. Empty list if none.",
    )


# ---------------------------------------------------------------------------
# Daily logging (user-entered actuals / check-offs)
# ---------------------------------------------------------------------------
class LogEntry(BaseModel):
    """A single user log entry within a domain for a day."""

    key: str = Field(
        ...,
        description=(
            "Identifier for what was logged. Either a schedule item title "
            "(for a check-off) or a free-form key like 'extra_meditation'."
        ),
    )
    completed: bool = Field(
        default=True,
        description="Whether the scheduled item was completed (true) or skipped (false).",
    )
    value: Optional[float] = Field(
        default=None,
        description="Quantitative actual value, e.g. minutes meditated or calories eaten.",
    )
    note: Optional[str] = Field(default=None, description="Optional free-text note.")


class DailyLogRequest(BaseModel):
    """Request body for POST /dashboard/log."""

    date: str = Field(..., description="ISO date (YYYY-MM-DD) the log is for.")
    domain: str = Field(..., description=f"One of: {', '.join(WELLNESS_DOMAINS)}.")
    entries: list[LogEntry] = Field(
        default_factory=list,
        description="Entries to upsert for this domain on this date (replaces prior entries).",
    )


class DailyLog(BaseModel):
    """A persisted daily log row (one per user/date/domain)."""

    date: str
    domain: str
    entries: list[LogEntry]


# ---------------------------------------------------------------------------
# Aggregate dashboard response
# ---------------------------------------------------------------------------
class DashboardToday(BaseModel):
    """Response body for GET /dashboard/today — everything the dashboard needs in one call."""

    date: str
    onboarded: bool
    day_of_plan: int
    phase: str
    plan_summary: Optional[str] = None
    plan_phase_focus: Optional[str] = None
    schedule: Optional[DailySchedule] = None
    logs: dict[str, list[LogEntry]] = Field(
        default_factory=dict,
        description="Logs keyed by domain.",
    )
    biomarker_count: int = 0
