"""Seed the database with demo data for testing the voice + dashboard features.

Creates a demo user (``demo`` / ``demodemo``) with:
  - An onboarded profile + 90-day wellness plan (day 14 of plan)
  - A doc summary (simulating an uploaded lab report)
  - Today's AI-generated daily schedule (8 timed items across all domains)
  - 7 days of daily logs (today partially complete, past days varied for streaks)
  - 4 biomarkers with 2-3 readings each over time (for trend charts + deltas)

Idempotent: skips seeding if the demo user already exists and is onboarded,
unless ``--force`` is passed (which wipes the demo user's data and re-seeds).

Usage:
    uv run python -m app.seed              # seed if not already seeded
    uv run python -m app.seed --force      # wipe demo data and re-seed
    uv run python -m app.seed --check      # print seed status without modifying

Auto-runs on app startup when the ``SEED_ON_STARTUP`` env var is not ``"false"``
and the demo user is not already onboarded.
"""

import asyncio
import json
import logging
from datetime import date, timedelta

from app.database import (
    add_biomarkers,
    delete_user_cascade,
    get_profile,
    init_db,
    register_user,
    save_daily_log,
    save_daily_schedule,
    save_profile,
)
from app.practitioner_db import (
    create_appointment,
    get_practitioner_by_username,
    register_practitioner,
)

logger = logging.getLogger("bloom2.seed")

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demodemo"

# How many days into the plan the demo user is. onboarded_at is set to
# (DAYS_INTO_PLAN - 1) days ago so _compute_day_of_plan returns this value.
DAYS_INTO_PLAN = 14


# ---------------------------------------------------------------------------
# Static demo data
# ---------------------------------------------------------------------------
DEMO_PROFILE = {
    "goal": "Better sleep and stress reduction",
    "activity_level": "lightly active",
    "sleep_hours": 6.5,
    "stress_level": "moderate",
    "conditions": ["mild hypertension"],
    "medications": ["lisinopril 10mg"],
    "allergies": [],
    "diet": "no restrictions",
    "time_available": "30 min/day",
    "equipment": "none",
}

DEMO_PLAN = {
    "summary": (
        "A 90-day plan focused on improving sleep quality and reducing stress "
        "through daily meditation, regular light exercise, and consistent sleep "
        "hygiene. Medication adherence for blood pressure management."
    ),
    "phases": [
        {
            "name": "Phase 1: Days 1-30",
            "focus": (
                "Build a daily meditation habit and establish a consistent "
                "sleep schedule."
            ),
            "actions": [
                "Meditate 10 minutes every morning",
                "Walk 20 minutes 3x per week",
                "Lights out by 10:30pm",
                "Take lisinopril each morning with breakfast",
            ],
        },
        {
            "name": "Phase 2: Days 31-60",
            "focus": "Increase activity and introduce breathwork for stress.",
            "actions": [
                "Meditate 15 minutes daily",
                "Walk 30 minutes 4x per week",
                "Add 5-min breathwork after lunch",
                "Track sleep in a journal",
            ],
        },
        {
            "name": "Phase 3: Days 61-90",
            "focus": "Solidify habits and add variety.",
            "actions": [
                "Meditate 20 minutes daily",
                "Try yoga 2x per week",
                "Review sleep and mood trends",
                "Plan the next 90 days",
            ],
        },
    ],
    "weekly_rhythm": (
        "Meditation every morning, walks Mon/Wed/Fri/Sat, medication daily, "
        "mood check-in each evening."
    ),
}

DEMO_DOC_SUMMARY = {
    "conditions": ["mild hypertension"],
    "medications": ["lisinopril 10mg daily"],
    "allergies": [],
    "recent_labs": [
        "HbA1c 5.8%",
        "LDL Cholesterol 122 mg/dL",
        "Vitamin D 28 ng/mL",
        "TSH 2.1 mIU/L",
    ],
    "lifestyle_notes": (
        "Patient reports 6 hours of sleep per night, moderate stress, "
        "lightly active lifestyle."
    ),
    "red_flags": [],
    "free_text_summary": (
        "Recent annual physical showing mild hypertension managed with "
        "lisinopril. Lab work shows borderline HbA1c and low-normal vitamin D. "
        "No acute concerns."
    ),
}


def _build_schedule(iso_date: str, day_of_plan: int) -> dict:
    """Build a deterministic daily schedule for the demo user."""
    return {
        "date": iso_date,
        "day_of_plan": day_of_plan,
        "phase": "Phase 1: Days 1-30",
        "focus_today": (
            "Build a daily meditation habit and establish a consistent "
            "sleep schedule."
        ),
        "items": [
            {
                "time": "07:00",
                "title": "Morning meditation",
                "domain": "meditation",
                "duration_min": 10,
                "detail": "10 minutes of guided breathing to start the day calm.",
                "target": {"minutes": 10},
            },
            {
                "time": "07:30",
                "title": "Take lisinopril",
                "domain": "medication",
                "duration_min": None,
                "detail": "10mg with breakfast.",
                "target": None,
            },
            {
                "time": "08:00",
                "title": "Breakfast",
                "domain": "diet",
                "duration_min": None,
                "detail": "Oatmeal with berries and nuts.",
                "target": None,
            },
            {
                "time": "12:30",
                "title": "Lunch",
                "domain": "diet",
                "duration_min": None,
                "detail": "Grilled chicken salad with olive oil.",
                "target": None,
            },
            {
                "time": "17:00",
                "title": "Evening walk",
                "domain": "workout",
                "duration_min": 20,
                "detail": "20-minute walk around the neighborhood.",
                "target": {"minutes": 20},
            },
            {
                "time": "18:30",
                "title": "Dinner",
                "domain": "diet",
                "duration_min": None,
                "detail": "Salmon with roasted vegetables.",
                "target": None,
            },
            {
                "time": "21:00",
                "title": "Wind-down meditation",
                "domain": "meditation",
                "duration_min": 5,
                "detail": "5 minutes of body scan before bed.",
                "target": {"minutes": 5},
            },
            {
                "time": "21:30",
                "title": "Mood check-in",
                "domain": "mental_health",
                "duration_min": None,
                "detail": "Rate your mood 1-5 and reflect on the day.",
                "target": None,
            },
        ],
        "daily_targets": {
            "workout_minutes": 20,
            "meditation_minutes": 15,
            "meals_logged": 3,
            "meds_taken": 1,
        },
        "motivation_note": (
            "You're two weeks in — the habit is forming. Keep showing up!"
        ),
    }


def _build_logs_for_day(offset: int) -> dict[str, list[dict]]:
    """Build per-domain log entries for a day `offset` days from today.

    Today (offset=0) is partially complete. Past days have varied completion
    patterns to create interesting streaks:
      - Meditation: 4-day streak (today + 3 prior)
      - Workout: 2-day streak (today + yesterday)
      - Medication: 7-day streak (today + 6 prior)
      - Mental health (mood): 2-day streak (today + yesterday)
    """
    logs: dict[str, list[dict]] = {}

    if offset == 0:
        # Today: partially complete — morning meditation done, evening not yet.
        logs["meditation"] = [
            {"key": "Morning meditation", "completed": True, "value": 10},
            {"key": "Wind-down meditation", "completed": False, "value": None},
        ]
        logs["workout"] = [
            {"key": "Evening walk", "completed": True, "value": 20},
        ]
        logs["medication"] = [
            {"key": "Take lisinopril", "completed": True, "value": 1},
        ]
        logs["diet"] = [
            {"key": "Breakfast", "completed": True, "value": 1},
        ]
        logs["mental_health"] = [
            {"key": "mood", "completed": True, "value": 4},
        ]
    elif offset == -1:
        # Yesterday: full day — meditation, workout, meds, mood.
        logs["meditation"] = [
            {"key": "Morning meditation", "completed": True, "value": 10},
            {"key": "Wind-down meditation", "completed": True, "value": 5},
        ]
        logs["workout"] = [
            {"key": "Evening walk", "completed": True, "value": 20},
        ]
        logs["medication"] = [
            {"key": "Take lisinopril", "completed": True, "value": 1},
        ]
        logs["mental_health"] = [
            {"key": "mood", "completed": True, "value": 3},
        ]
    elif offset == -2:
        # Day -2: meditation + meds, no workout.
        logs["meditation"] = [
            {"key": "Morning meditation", "completed": True, "value": 10},
        ]
        logs["medication"] = [
            {"key": "Take lisinopril", "completed": True, "value": 1},
        ]
    elif offset == -3:
        # Day -3: meditation + workout + meds + mood.
        logs["meditation"] = [
            {"key": "Morning meditation", "completed": True, "value": 10},
        ]
        logs["workout"] = [
            {"key": "Evening walk", "completed": True, "value": 15},
        ]
        logs["medication"] = [
            {"key": "Take lisinopril", "completed": True, "value": 1},
        ]
        logs["mental_health"] = [
            {"key": "mood", "completed": True, "value": 3},
        ]
    elif offset == -4:
        # Day -4: only meds (streak breaker for meditation).
        logs["medication"] = [
            {"key": "Take lisinopril", "completed": True, "value": 1},
        ]
    elif offset == -5:
        # Day -5: meditation + workout + meds + mood.
        logs["meditation"] = [
            {"key": "Morning meditation", "completed": True, "value": 10},
        ]
        logs["workout"] = [
            {"key": "Evening walk", "completed": True, "value": 20},
        ]
        logs["medication"] = [
            {"key": "Take lisinopril", "completed": True, "value": 1},
        ]
        logs["mental_health"] = [
            {"key": "mood", "completed": True, "value": 2},
        ]
    elif offset == -6:
        # Day -6: meditation + meds.
        logs["meditation"] = [
            {"key": "Morning meditation", "completed": True, "value": 10},
        ]
        logs["medication"] = [
            {"key": "Take lisinopril", "completed": True, "value": 1},
        ]
    # offset == -7: gap day (no logs) — breaks the 7-day medication streak.

    return logs


def _build_biomarkers() -> list[dict]:
    """Build biomarker readings with multiple measurements over time.

    4 markers, each with 2-3 readings, providing trend deltas:
      - HbA1c: 6.1 → 5.9 → 5.8 (down trend, still above range)
      - LDL Cholesterol: 135 → 128 → 122 (down trend)
      - Vitamin D: 22 → 28 (up trend, still below range)
      - TSH: 2.4 → 2.1 (down trend, in range)
    """
    today = date.today()
    days_ago = lambda n: (today - timedelta(days=n)).isoformat()

    return [
        # HbA1c — 3 readings, downward trend
        {
            "name": "HbA1c",
            "value": 6.1,
            "unit": "%",
            "ref_low": 4.0,
            "ref_high": 5.6,
            "optimal_low": None,
            "optimal_high": 5.4,
            "measured_at": days_ago(90),
            "source_doc": "lab_report_2026_03.pdf",
        },
        {
            "name": "HbA1c",
            "value": 5.9,
            "unit": "%",
            "ref_low": 4.0,
            "ref_high": 5.6,
            "optimal_low": None,
            "optimal_high": 5.4,
            "measured_at": days_ago(45),
            "source_doc": "lab_report_2026_05.pdf",
        },
        {
            "name": "HbA1c",
            "value": 5.8,
            "unit": "%",
            "ref_low": 4.0,
            "ref_high": 5.6,
            "optimal_low": None,
            "optimal_high": 5.4,
            "measured_at": days_ago(10),
            "source_doc": "lab_report_2026_06.pdf",
        },
        # LDL Cholesterol — 3 readings, downward trend
        {
            "name": "LDL Cholesterol",
            "value": 135,
            "unit": "mg/dL",
            "ref_low": 0,
            "ref_high": 100,
            "optimal_low": None,
            "optimal_high": 130,
            "measured_at": days_ago(180),
            "source_doc": "lab_report_2025_12.pdf",
        },
        {
            "name": "LDL Cholesterol",
            "value": 128,
            "unit": "mg/dL",
            "ref_low": 0,
            "ref_high": 100,
            "optimal_low": None,
            "optimal_high": 130,
            "measured_at": days_ago(90),
            "source_doc": "lab_report_2026_03.pdf",
        },
        {
            "name": "LDL Cholesterol",
            "value": 122,
            "unit": "mg/dL",
            "ref_low": 0,
            "ref_high": 100,
            "optimal_low": None,
            "optimal_high": 130,
            "measured_at": days_ago(10),
            "source_doc": "lab_report_2026_06.pdf",
        },
        # Vitamin D — 2 readings, upward trend
        {
            "name": "Vitamin D (25-OH)",
            "value": 22,
            "unit": "ng/mL",
            "ref_low": 30,
            "ref_high": 100,
            "optimal_low": 40,
            "optimal_high": 60,
            "measured_at": days_ago(180),
            "source_doc": "lab_report_2025_12.pdf",
        },
        {
            "name": "Vitamin D (25-OH)",
            "value": 28,
            "unit": "ng/mL",
            "ref_low": 30,
            "ref_high": 100,
            "optimal_low": 40,
            "optimal_high": 60,
            "measured_at": days_ago(10),
            "source_doc": "lab_report_2026_06.pdf",
        },
        # TSH — 2 readings, downward trend, in range
        {
            "name": "TSH",
            "value": 2.4,
            "unit": "mIU/L",
            "ref_low": 0.4,
            "ref_high": 4.0,
            "optimal_low": None,
            "optimal_high": None,
            "measured_at": days_ago(180),
            "source_doc": "lab_report_2025_12.pdf",
        },
        {
            "name": "TSH",
            "value": 2.1,
            "unit": "mIU/L",
            "ref_low": 0.4,
            "ref_high": 4.0,
            "optimal_low": None,
            "optimal_high": None,
            "measured_at": days_ago(10),
            "source_doc": "lab_report_2026_06.pdf",
        },
    ]


# ---------------------------------------------------------------------------
# Demo practitioners
# ---------------------------------------------------------------------------
DEMO_PRACTITIONERS = [
    {
        "username": "dranya",
        "password": DEMO_PASSWORD,
        "full_name": "Dr. Anya Sharma",
        "title": "MD",
        "specialization": "Endocrinology",
        "bio": (
            "Board-certified endocrinologist focused on metabolic health, "
            "diabetes management, and thyroid disorders. 12 years of "
            "experience helping patients reverse prediabetes through "
            "lifestyle medicine."
        ),
        "email": "anya.sharma@bloom.demo",
        "phone": "+1-555-0101",
        "years_experience": 12,
        "consultation_fee": 150.0,
    },
    {
        "username": "marcop",
        "password": DEMO_PASSWORD,
        "full_name": "Marco Perez",
        "title": "Nutritionist",
        "specialization": "Nutrition & Diet",
        "bio": (
            "Registered dietitian specializing in sustainable weight "
            "management, plant-based nutrition, and sports nutrition. "
            "Believes in small, lasting habit changes over restrictive diets."
        ),
        "email": "marco.perez@bloom.demo",
        "phone": "+1-555-0102",
        "years_experience": 8,
        "consultation_fee": 90.0,
    },
    {
        "username": "drchen",
        "password": DEMO_PASSWORD,
        "full_name": "Dr. Lin Chen",
        "title": "MD",
        "specialization": "Mental Health",
        "bio": (
            "Psychiatrist with a focus on integrative mental health — "
            "combining evidence-based therapy, mindfulness, and lifestyle "
            "interventions for anxiety, depression, and stress-related "
            "conditions."
        ),
        "email": "lin.chen@bloom.demo",
        "phone": "+1-555-0103",
        "years_experience": 15,
        "consultation_fee": 175.0,
    },
]


async def seed_demo_practitioners(force: bool = False) -> bool:
    """Seed demo practitioner accounts and one demo appointment.

    Idempotent: skips practitioners that already exist unless ``force`` is
    True (which wipes all practitioner data first).
    """
    await init_db()

    if force:
        import sqlite3
        from app.database import DB_PATH, _lock
        with _lock, sqlite3.connect(DB_PATH) as conn:
            conn.execute("DELETE FROM practitioner_patient_connections")
            conn.execute("DELETE FROM appointments")
            conn.execute("DELETE FROM practitioner_notes")
            conn.execute("DELETE FROM practitioner_tokens")
            conn.execute("DELETE FROM practitioners")
            conn.commit()
        logger.info("Seed: --force wiped all practitioner data.")

    created = []
    for pdata in DEMO_PRACTITIONERS:
        existing = await get_practitioner_by_username(pdata["username"])
        if existing:
            logger.info("Seed: practitioner '%s' already exists — skipping.", pdata["username"])
            created.append(existing)
            continue
        p = await register_practitioner(pdata)
        if p:
            created.append(p)
            logger.info("Seed: created practitioner '%s' (%s).", p["username"], p["full_name"])
        else:
            logger.warning("Seed: failed to create practitioner '%s'.", pdata["username"])

    # Seed one demo appointment from the demo patient to the first practitioner,
    # in pending status, so the practitioner web app has something to act on.
    if created:
        from app.practitioner_db import list_appointments_for_patient
        existing_appts = await list_appointments_for_patient(DEMO_USERNAME)
        if not existing_appts:
            target_date = (date.today() + timedelta(days=3)).isoformat()
            await create_appointment({
                "patient_username": DEMO_USERNAME,
                "practitioner_id": created[0]["id"],
                "requested_date": target_date,
                "requested_time": "10:00",
                "reason": "Initial consultation — review recent labs and 90-day plan",
                "patient_note": "I'd like to discuss my HbA1c trend and sleep plan.",
            })
            logger.info(
                "Seed: created demo appointment from '%s' to '%s' on %s (pending).",
                DEMO_USERNAME, created[0]["username"], target_date,
            )

    if created:
        logger.info(
            "Seed: practitioners ready. Log in with '%s' / '%s'",
            DEMO_PRACTITIONERS[0]["username"], DEMO_PASSWORD,
        )
    return bool(created)


# ---------------------------------------------------------------------------
# Seed logic
# ---------------------------------------------------------------------------
async def seed_demo_data(force: bool = False) -> bool:
    """Seed the demo user's data. Returns True if seeding was performed.

    Args:
        force: If True, wipe the demo user's existing data and re-seed.
    """
    await init_db()

    # Check if demo user already exists and is onboarded.
    existing = await get_profile(DEMO_USERNAME)

    if existing and existing.get("onboarded") and not force:
        logger.info("Seed: demo user already onboarded — skipping (use --force to re-seed).")
        # Still ensure demo practitioners are seeded (they're independent of
        # the demo patient and may not exist yet on a DB where the patient
        # was seeded before the practitioner feature existed).
        await seed_demo_practitioners(force=False)
        return False

    if force:
        logger.info("Seed: --force specified, wiping demo user data.")
        await delete_user_cascade(DEMO_USERNAME)
        existing = None

    # Register the demo user (if not already registered after a force wipe).
    if not existing:
        registered = await register_user(DEMO_USERNAME, DEMO_PASSWORD)
        if not registered:
            # User exists but has no profile — that's fine, we'll save one.
            logger.info("Seed: demo user already registered (no profile yet).")

    # Save the onboarded profile + plan + doc summary.
    # Set onboarded_at to (DAYS_INTO_PLAN - 1) days ago so day_of_plan is correct.
    onboarded_at = (date.today() - timedelta(days=DAYS_INTO_PLAN - 1)).isoformat()
    await save_profile(
        username=DEMO_USERNAME,
        profile_json=json.dumps(DEMO_PROFILE),
        plan_json=json.dumps(DEMO_PLAN),
        doc_summary_json=json.dumps(DEMO_DOC_SUMMARY),
        onboarded=True,
        onboarded_at=onboarded_at,
    )
    logger.info("Seed: saved profile + plan + doc summary (day %d of plan).", DAYS_INTO_PLAN)

    # Save today's schedule.
    today = date.today()
    schedule = _build_schedule(today.isoformat(), DAYS_INTO_PLAN)
    await save_daily_schedule(DEMO_USERNAME, today.isoformat(), json.dumps(schedule))
    logger.info("Seed: saved today's schedule (%d items).", len(schedule["items"]))

    # Save 7 days of daily logs (today + past 7 days).
    log_count = 0
    for offset in range(0, -8, -1):
        day = today + timedelta(days=offset)
        logs = _build_logs_for_day(offset)
        for domain, entries in logs.items():
            await save_daily_log(
                DEMO_USERNAME, day.isoformat(), domain, json.dumps(entries)
            )
            log_count += 1
    logger.info("Seed: saved %d daily log entries across 8 days.", log_count)

    # Save biomarker readings.
    readings = _build_biomarkers()
    await add_biomarkers(DEMO_USERNAME, readings)
    logger.info("Seed: saved %d biomarker readings (4 markers).", len(readings))

    # Create a practitioner-designed tracking plan for the demo patient.
    await _seed_demo_tracking_plan()

    logger.info("Seed: complete. Log in with %s / %s", DEMO_USERNAME, DEMO_PASSWORD)

    # Also seed demo practitioners + a demo appointment.
    await seed_demo_practitioners(force=force)

    return True


async def _seed_demo_tracking_plan() -> None:
    """Create a practitioner-designed tracking plan for the demo patient.

    Designed by Dr. Anya Sharma (endocrinologist) based on the demo patient's
    biomarkers (borderline HbA1c, mild hypertension, low vitamin D) and
    profile (sleep/stress goals). Includes:
      - 3 outcome targets (HbA1c < 5.6, LDL < 100, Vitamin D >= 30)
      - 6 tracked metrics (steps, sleep, meditation, mood, BP, medication)
      - 3 phases (30 days each)
    Re-points the existing daily logs to the new metric IDs.
    """
    from app.plan_db import (
        _has_active_plan_sync,
        _create_plan_sync,
        _migrate_domain_logs_for_patient_sync,
    )
    from app.metric_templates import DOMAIN_TO_TEMPLATE

    if _has_active_plan_sync(DEMO_USERNAME):
        logger.info("Seed: demo patient already has an active plan — skipping plan creation.")
        return

    # Look up Dr. Anya Sharma's practitioner ID.
    dr_anya = await get_practitioner_by_username("dranya")
    practitioner_id = dr_anya["id"] if dr_anya else None

    outcomes = [
        {
            "biomarker_name": "HbA1c",
            "target_value": 5.6,
            "target_direction": "below",
            "target_high": None,
            "unit": "%",
            "target_date": (date.today() + timedelta(days=76)).isoformat(),  # ~90 days out
            "current_value": 5.8,
            "current_as_of": (date.today() - timedelta(days=10)).isoformat(),
        },
        {
            "biomarker_name": "LDL Cholesterol",
            "target_value": 100,
            "target_direction": "below",
            "target_high": None,
            "unit": "mg/dL",
            "target_date": (date.today() + timedelta(days=76)).isoformat(),
            "current_value": 122,
            "current_as_of": (date.today() - timedelta(days=10)).isoformat(),
        },
        {
            "biomarker_name": "Vitamin D (25-OH)",
            "target_value": 30,
            "target_direction": "above",
            "target_high": None,
            "unit": "ng/mL",
            "target_date": (date.today() + timedelta(days=76)).isoformat(),
            "current_value": 28,
            "current_as_of": (date.today() - timedelta(days=10)).isoformat(),
        },
    ]

    metrics = [
        {
            "template_id": "steps",
            "label": "Steps",
            "unit": "steps",
            "frequency": "daily",
            "time_of_day": "evening",
            "target_type": "minimum",
            "target_value": 8000,
            "target_high": None,
            "is_active": True,
            "phase": None,
            "sort_order": 0,
        },
        {
            "template_id": "sleep_duration",
            "label": "Sleep Duration",
            "unit": "hours",
            "frequency": "daily",
            "time_of_day": "morning",
            "target_type": "minimum",
            "target_value": 7,
            "target_high": None,
            "is_active": True,
            "phase": None,
            "sort_order": 1,
        },
        {
            "template_id": "meditation_minutes",
            "label": "Meditation",
            "unit": "minutes",
            "frequency": "daily",
            "time_of_day": "morning",
            "target_type": "minimum",
            "target_value": 15,
            "target_high": None,
            "is_active": True,
            "phase": None,
            "sort_order": 2,
        },
        {
            "template_id": "mood",
            "label": "Mood",
            "unit": "/5",
            "frequency": "daily",
            "time_of_day": "evening",
            "target_type": "minimum",
            "target_value": 3,
            "target_high": None,
            "is_active": True,
            "phase": None,
            "sort_order": 3,
        },
        {
            "template_id": "blood_pressure_systolic",
            "label": "Blood Pressure (Systolic)",
            "unit": "mmHg",
            "frequency": "daily",
            "time_of_day": "morning",
            "target_type": "maximum",
            "target_value": 120,
            "target_high": None,
            "is_active": True,
            "phase": None,
            "sort_order": 4,
        },
        {
            "template_id": "medication_adherence",
            "label": "Lisinopril Taken",
            "unit": "doses",
            "frequency": "daily",
            "time_of_day": "morning",
            "target_type": "count",
            "target_value": 1,
            "target_high": None,
            "is_active": True,
            "phase": None,
            "sort_order": 5,
        },
    ]

    phases = [
        {
            "phase_number": 1,
            "name": "Phase 1: Days 1-30",
            "focus": "Build a daily meditation habit and establish a consistent sleep schedule.",
            "actions": [
                "Meditate 10 minutes every morning",
                "Walk 20 minutes 3x per week",
                "Lights out by 10:30pm",
                "Take lisinopril each morning with breakfast",
            ],
            "day_start": 1,
            "day_end": 30,
        },
        {
            "phase_number": 2,
            "name": "Phase 2: Days 31-60",
            "focus": "Increase activity and introduce breathwork for stress.",
            "actions": [
                "Meditate 15 minutes daily",
                "Walk 30 minutes 4x per week",
                "Add 5-min breathwork after lunch",
                "Track sleep in a journal",
            ],
            "day_start": 31,
            "day_end": 60,
        },
        {
            "phase_number": 3,
            "name": "Phase 3: Days 61-90",
            "focus": "Solidify habits and add variety.",
            "actions": [
                "Meditate 20 minutes daily",
                "Try yoga 2x per week",
                "Review sleep and mood trends",
                "Plan the next 90 days",
            ],
            "day_start": 61,
            "day_end": 90,
        },
    ]

    plan = _create_plan_sync(
        patient_username=DEMO_USERNAME,
        practitioner_id=practitioner_id,
        title="Metabolic Health & Sleep Optimization — 90 Days",
        rationale=(
            "Designed by Dr. Anya Sharma based on recent labs showing borderline "
            "HbA1c (5.8%), elevated LDL (122 mg/dL), and low vitamin D (28 ng/mL). "
            "Plan targets the behavioral levers most impactful for metabolic health: "
            "daily activity (steps), sleep quality, stress reduction (meditation), "
            "and medication adherence (lisinopril for BP). Mood tracked as a leading "
            "indicator of adherence. Outcomes: HbA1c < 5.6%, LDL < 100, Vitamin D >= 30."
        ),
        outcomes=outcomes,
        metrics=metrics,
        phases=phases,
    )
    logger.info(
        "Seed: created tracking plan '%s' with %d metrics, %d outcomes, %d phases.",
        plan["title"], len(plan["metrics"]), len(plan["outcomes"]), len(plan["phases"]),
    )

    # Re-point existing daily logs to the new metric IDs.
    metric_id_by_template: dict[str, int] = {}
    for m in plan["metrics"]:
        metric_id_by_template[m["template_id"]] = m["id"]
    import sqlite3
    from app.database import DB_PATH, _lock
    with _lock, sqlite3.connect(DB_PATH) as conn:
        updated = _migrate_domain_logs_for_patient_sync(
            conn, DEMO_USERNAME, plan["id"], metric_id_by_template
        )
        conn.commit()
    if updated:
        logger.info("Seed: re-pointed %d daily log rows to new metric IDs.", updated)


async def check_seed_status() -> None:
    """Print the current seed status without modifying anything."""
    await init_db()
    existing = await get_profile(DEMO_USERNAME)
    if existing and existing.get("onboarded"):
        print(f"Demo user '{DEMO_USERNAME}' is seeded and onboarded (day {DAYS_INTO_PLAN} of plan).")
        print(f"  Login: {DEMO_USERNAME} / {DEMO_PASSWORD}")
        print("  Use --force to wipe and re-seed.")
    else:
        print(f"Demo user '{DEMO_USERNAME}' is NOT seeded.")
        print("  Run `uv run python -m app.seed` to seed.")

    # Practitioner seed status.
    from app.practitioner_db import get_practitioner_by_username
    prac = await get_practitioner_by_username(DEMO_PRACTITIONERS[0]["username"])
    if prac:
        print(f"Demo practitioners are seeded ({len(DEMO_PRACTITIONERS)} accounts).")
        print(f"  Practitioner login: {DEMO_PRACTITIONERS[0]['username']} / {DEMO_PASSWORD}")
    else:
        print("Demo practitioners are NOT seeded.")
        print("  Run `uv run python -m app.seed` to seed them alongside the demo user.")


def main() -> None:
    """CLI entry point for `python -m app.seed`."""
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    args = sys.argv[1:]
    if "--check" in args:
        asyncio.run(check_seed_status())
    elif "--force" in args:
        asyncio.run(seed_demo_data(force=True))
    else:
        asyncio.run(seed_demo_data())


if __name__ == "__main__":
    main()
