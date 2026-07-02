"""Pre-defined metric template library for practitioner-designed tracking plans.

Each template defines a metric type the practitioner can pick from when
building a patient's plan. The template specifies the key, label, unit,
allowed frequencies, target type, default target, default visualization,
and a short description for the practitioner UI.

The library is intentionally finite (~25 templates) covering the common
preventive-medicine tracking needs. Free-form custom metrics are a future
feature (see PLAN_TRACKING_PLANS.md section 11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class MetricTemplate:
    """A pre-defined metric type in the template library."""

    key: str
    label: str
    unit: str
    frequency_options: tuple[str, ...]
    target_type: str  # "minimum" | "maximum" | "range" | "exact" | "count" | "none" | "target"
    default_target: Optional[float]
    visualization: str  # "bar" | "line" | "line_with_target" | "line_with_range" | "ring" | "scatter"
    description: str
    default_target_high: Optional[float] = None


METRIC_TEMPLATES: list[MetricTemplate] = [
    MetricTemplate(
        key="fasting_glucose",
        label="Fasting Glucose",
        unit="mg/dL",
        frequency_options=("daily",),
        target_type="maximum",
        default_target=100,
        visualization="line_with_target",
        description="Morning fasting blood glucose. Target is a maximum (e.g., < 100 mg/dL).",
    ),
    MetricTemplate(
        key="steps",
        label="Steps",
        unit="steps",
        frequency_options=("daily",),
        target_type="minimum",
        default_target=8000,
        visualization="bar",
        description="Daily step count from phone or wearable.",
    ),
    MetricTemplate(
        key="sleep_duration",
        label="Sleep Duration",
        unit="hours",
        frequency_options=("daily",),
        target_type="minimum",
        default_target=7,
        visualization="bar",
        description="Hours of sleep per night.",
    ),
    MetricTemplate(
        key="sleep_quality",
        label="Sleep Quality",
        unit="/5",
        frequency_options=("daily",),
        target_type="minimum",
        default_target=4,
        visualization="bar",
        description="Subjective sleep quality, 1-5 scale.",
    ),
    MetricTemplate(
        key="mood",
        label="Mood",
        unit="/5",
        frequency_options=("daily", "as_needed"),
        target_type="minimum",
        default_target=3,
        visualization="line",
        description="Overall mood, 1-5 scale. Can be logged multiple times per day.",
    ),
    MetricTemplate(
        key="stress_level",
        label="Stress Level",
        unit="/5",
        frequency_options=("daily", "as_needed"),
        target_type="maximum",
        default_target=3,
        visualization="line",
        description="Subjective stress, 1-5 scale (5 = highest stress).",
    ),
    MetricTemplate(
        key="meditation_minutes",
        label="Meditation",
        unit="minutes",
        frequency_options=("daily",),
        target_type="minimum",
        default_target=15,
        visualization="bar",
        description="Minutes of meditation or breathing exercises per day.",
    ),
    MetricTemplate(
        key="workout_minutes",
        label="Workout",
        unit="minutes",
        frequency_options=("daily",),
        target_type="minimum",
        default_target=30,
        visualization="bar",
        description="Minutes of exercise (walk, run, yoga, strength, etc.).",
    ),
    MetricTemplate(
        key="weight",
        label="Weight",
        unit="kg",
        frequency_options=("daily", "weekly"),
        target_type="target",
        default_target=None,
        visualization="line_with_target",
        description="Body weight. Target is patient-specific (weight loss/gain/maintenance).",
    ),
    MetricTemplate(
        key="blood_pressure_systolic",
        label="Blood Pressure (Systolic)",
        unit="mmHg",
        frequency_options=("daily", "as_needed"),
        target_type="maximum",
        default_target=120,
        visualization="line_with_target",
        description="Systolic blood pressure reading.",
    ),
    MetricTemplate(
        key="blood_pressure_diastolic",
        label="Blood Pressure (Diastolic)",
        unit="mmHg",
        frequency_options=("daily", "as_needed"),
        target_type="maximum",
        default_target=80,
        visualization="line_with_target",
        description="Diastolic blood pressure reading.",
    ),
    MetricTemplate(
        key="resting_heart_rate",
        label="Resting Heart Rate",
        unit="bpm",
        frequency_options=("daily",),
        target_type="range",
        default_target=60,
        default_target_high=80,
        visualization="line_with_range",
        description="Resting heart rate, in beats per minute.",
    ),
    MetricTemplate(
        key="medication_adherence",
        label="Medication Taken",
        unit="doses",
        frequency_options=("daily",),
        target_type="count",
        default_target=1,
        visualization="ring",
        description="Whether a specific medication was taken. Configure per medication.",
    ),
    MetricTemplate(
        key="meals_logged",
        label="Meals Logged",
        unit="meals",
        frequency_options=("daily",),
        target_type="count",
        default_target=3,
        visualization="ring",
        description="Number of meals logged per day (basic nutrition adherence).",
    ),
    MetricTemplate(
        key="carbs_per_meal",
        label="Carbs per Meal",
        unit="grams",
        frequency_options=("per_meal",),
        target_type="maximum",
        default_target=45,
        visualization="bar",
        description="Carbohydrate grams per meal. For low-carb or diabetic plans.",
    ),
    MetricTemplate(
        key="calories_per_meal",
        label="Calories per Meal",
        unit="kcal",
        frequency_options=("per_meal",),
        target_type="maximum",
        default_target=500,
        visualization="bar",
        description="Calories per meal. For calorie-controlled plans.",
    ),
    MetricTemplate(
        key="protein_per_meal",
        label="Protein per Meal",
        unit="grams",
        frequency_options=("per_meal",),
        target_type="minimum",
        default_target=25,
        visualization="bar",
        description="Protein grams per meal. For high-protein plans.",
    ),
    MetricTemplate(
        key="water_intake",
        label="Water Intake",
        unit="glasses",
        frequency_options=("daily",),
        target_type="minimum",
        default_target=8,
        visualization="ring",
        description="Glasses of water per day.",
    ),
    MetricTemplate(
        key="caffeine_intake",
        label="Caffeine",
        unit="mg",
        frequency_options=("daily",),
        target_type="maximum",
        default_target=200,
        visualization="bar",
        description="Caffeine intake in mg. Relevant for sleep/anxiety plans.",
    ),
    MetricTemplate(
        key="alcohol_drinks",
        label="Alcohol",
        unit="drinks",
        frequency_options=("daily",),
        target_type="maximum",
        default_target=1,
        visualization="bar",
        description="Number of alcoholic drinks per day.",
    ),
    MetricTemplate(
        key="symptom_severity",
        label="Symptom Severity",
        unit="/5",
        frequency_options=("as_needed",),
        target_type="none",
        default_target=None,
        visualization="scatter",
        description="Log a symptom with severity 1-5. No target — tracked for pattern detection.",
    ),
    MetricTemplate(
        key="anxiety_level",
        label="Anxiety Level",
        unit="/5",
        frequency_options=("daily", "as_needed"),
        target_type="maximum",
        default_target=2,
        visualization="line",
        description="Subjective anxiety, 1-5 scale. For mental health plans.",
    ),
    MetricTemplate(
        key="therapy_homework",
        label="Therapy Homework",
        unit="done",
        frequency_options=("weekly",),
        target_type="count",
        default_target=1,
        visualization="ring",
        description="Whether therapy homework was completed this week.",
    ),
    MetricTemplate(
        key="screen_time",
        label="Screen Time",
        unit="hours",
        frequency_options=("daily",),
        target_type="maximum",
        default_target=4,
        visualization="bar",
        description="Hours of screen time per day. Relevant for sleep/mental health.",
    ),
]


# Index for fast lookups by key.
_TEMPLATES_BY_KEY: dict[str, MetricTemplate] = {t.key: t for t in METRIC_TEMPLATES}


def get_template(key: str) -> MetricTemplate | None:
    """Return the template with the given key, or None if not found."""
    return _TEMPLATES_BY_KEY.get(key)


def list_templates() -> list[MetricTemplate]:
    """Return all available metric templates."""
    return list(METRIC_TEMPLATES)


def template_exists(key: str) -> bool:
    """Return True if a template with the given key exists."""
    return key in _TEMPLATES_BY_KEY


def templates_as_dicts() -> list[dict]:
    """Return all templates as plain dicts (for JSON serialization)."""
    out = []
    for t in METRIC_TEMPLATES:
        out.append(
            {
                "key": t.key,
                "label": t.label,
                "unit": t.unit,
                "frequency_options": list(t.frequency_options),
                "target_type": t.target_type,
                "default_target": t.default_target,
                "default_target_high": t.default_target_high,
                "visualization": t.visualization,
                "description": t.description,
            }
        )
    return out


def template_to_dict(t: MetricTemplate) -> dict:
    """Return a single template as a plain dict."""
    return {
        "key": t.key,
        "label": t.label,
        "unit": t.unit,
        "frequency_options": list(t.frequency_options),
        "target_type": t.target_type,
        "default_target": t.default_target,
        "default_target_high": t.default_target_high,
        "visualization": t.visualization,
        "description": t.description,
    }


# Mapping from the old hardcoded wellness domains to the closest template,
# used by the migration (section 9 of PLAN_TRACKING_PLANS.md).
DOMAIN_TO_TEMPLATE: dict[str, str] = {
    "workout": "workout_minutes",
    "diet": "meals_logged",
    "meditation": "meditation_minutes",
    "medication": "medication_adherence",
    "mental_health": "mood",
    # "other" has no good template match and is omitted.
}
