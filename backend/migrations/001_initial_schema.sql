-- 001_initial_schema.sql
-- Full PostgreSQL schema for Bloom2 — all tables across all DB modules.
-- Replaces the inline CREATE TABLE IF NOT EXISTS calls that were in
-- database.py, practitioner_db.py, chat_db.py, and plan_db.py.
--
-- Table ordering respects foreign-key dependencies:
--   users → tokens, user_profiles, user_docs, daily_schedules
--   practitioners → practitioner_tokens, appointments, connections, notes
--   plans → plan_outcomes, plan_metrics, plan_phases
--   plan_metrics → daily_logs (FK on metric_id)
--   (chat tables have no FKs to other app tables)

-- ===========================================================================
-- Patient auth (database.py)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS users (
    username       TEXT PRIMARY KEY,
    password_hash  TEXT NOT NULL,
    salt           TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tokens (
    token       TEXT PRIMARY KEY,
    username    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_profiles (
    username           TEXT PRIMARY KEY,
    profile_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    plan_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
    doc_summary_json   JSONB,
    onboarded          BOOLEAN NOT NULL DEFAULT FALSE,
    onboarded_at       TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_docs (
    id           BIGSERIAL PRIMARY KEY,
    username     TEXT NOT NULL,
    filename     TEXT NOT NULL,
    mime_type    TEXT NOT NULL,
    uploaded_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS daily_schedules (
    username       TEXT NOT NULL,
    date           TEXT NOT NULL,
    schedule_json  JSONB NOT NULL,
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (username, date)
);

CREATE TABLE IF NOT EXISTS biomarkers (
    id            BIGSERIAL PRIMARY KEY,
    username      TEXT NOT NULL,
    name          TEXT NOT NULL,
    value         DOUBLE PRECISION NOT NULL,
    unit          TEXT NOT NULL,
    ref_low       DOUBLE PRECISION,
    ref_high      DOUBLE PRECISION,
    optimal_low   DOUBLE PRECISION,
    optimal_high  DOUBLE PRECISION,
    status        TEXT,
    source_doc    TEXT,
    measured_at   TEXT,
    extracted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ===========================================================================
-- Practitioner auth + appointments (practitioner_db.py)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS practitioners (
    id                 BIGSERIAL PRIMARY KEY,
    username           TEXT UNIQUE NOT NULL,
    password_hash      TEXT NOT NULL,
    salt               TEXT NOT NULL,
    full_name          TEXT NOT NULL,
    title              TEXT,
    specialization     TEXT,
    bio                TEXT,
    email              TEXT,
    phone              TEXT,
    years_experience   INTEGER,
    consultation_fee   DOUBLE PRECISION,
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS practitioner_tokens (
    token            TEXT PRIMARY KEY,
    practitioner_id  BIGINT NOT NULL REFERENCES practitioners(id) ON DELETE CASCADE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS appointments (
    id                BIGSERIAL PRIMARY KEY,
    patient_username  TEXT NOT NULL,
    practitioner_id   BIGINT NOT NULL REFERENCES practitioners(id) ON DELETE CASCADE,
    requested_date    TEXT NOT NULL,
    requested_time    TEXT,
    reason            TEXT,
    status            TEXT NOT NULL DEFAULT 'pending',
    patient_note      TEXT,
    practitioner_note TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS practitioner_patient_connections (
    id                       BIGSERIAL PRIMARY KEY,
    practitioner_id          BIGINT NOT NULL REFERENCES practitioners(id) ON DELETE CASCADE,
    patient_username         TEXT NOT NULL,
    established_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status                   TEXT NOT NULL DEFAULT 'active',
    ai_summary               TEXT,
    ai_summary_generated_at  TIMESTAMPTZ,
    UNIQUE (practitioner_id, patient_username)
);

CREATE TABLE IF NOT EXISTS practitioner_notes (
    id                BIGSERIAL PRIMARY KEY,
    practitioner_id   BIGINT NOT NULL REFERENCES practitioners(id) ON DELETE CASCADE,
    patient_username  TEXT NOT NULL,
    note_text         TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ===========================================================================
-- Tracking plans (plan_db.py)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS plans (
    id                BIGSERIAL PRIMARY KEY,
    patient_username  TEXT NOT NULL,
    practitioner_id   BIGINT REFERENCES practitioners(id) ON DELETE SET NULL,
    version           INTEGER NOT NULL DEFAULT 1,
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    title             TEXT,
    rationale         TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS plan_outcomes (
    id                BIGSERIAL PRIMARY KEY,
    plan_id           BIGINT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    biomarker_name    TEXT NOT NULL,
    target_value      DOUBLE PRECISION NOT NULL,
    target_direction  TEXT NOT NULL,
    target_high       DOUBLE PRECISION,
    unit              TEXT NOT NULL,
    target_date       TEXT,
    current_value     DOUBLE PRECISION,
    current_as_of     TEXT
);

CREATE TABLE IF NOT EXISTS plan_metrics (
    id            BIGSERIAL PRIMARY KEY,
    plan_id       BIGINT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    template_id   TEXT NOT NULL,
    label         TEXT NOT NULL,
    unit          TEXT NOT NULL,
    frequency     TEXT NOT NULL,
    time_of_day   TEXT,
    target_type   TEXT NOT NULL,
    target_value  DOUBLE PRECISION,
    target_high   DOUBLE PRECISION,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    phase         INTEGER,
    sort_order    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS plan_phases (
    id            BIGSERIAL PRIMARY KEY,
    plan_id       BIGINT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
    phase_number  INTEGER NOT NULL,
    name          TEXT NOT NULL,
    focus         TEXT,
    actions       JSONB NOT NULL DEFAULT '[]'::jsonb,
    day_start     INTEGER NOT NULL,
    day_end       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_drafts (
    id                BIGSERIAL PRIMARY KEY,
    patient_username  TEXT NOT NULL,
    practitioner_id   BIGINT NOT NULL,
    title             TEXT,
    rationale         TEXT,
    outcomes_json     JSONB NOT NULL DEFAULT '[]'::jsonb,
    metrics_json      JSONB NOT NULL DEFAULT '[]'::jsonb,
    phases_json       JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_published      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS plan_suggestions (
    id                BIGSERIAL PRIMARY KEY,
    patient_username  TEXT NOT NULL,
    practitioner_id   BIGINT,
    source            TEXT NOT NULL,
    suggestion_json   JSONB NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at        TIMESTAMPTZ,
    decided_by        BIGINT
);

-- ===========================================================================
-- Daily logs (depends on plan_metrics for FK on metric_id)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS daily_logs (
    username     TEXT NOT NULL,
    date         TEXT NOT NULL,
    domain       TEXT NOT NULL,
    metric_id    BIGINT REFERENCES plan_metrics(id) ON DELETE SET NULL,
    log_json     JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (username, date, domain)
);

-- ===========================================================================
-- Chat (chat_db.py)
-- ===========================================================================
CREATE TABLE IF NOT EXISTS chat_messages (
    id                BIGSERIAL PRIMARY KEY,
    conversation_id   TEXT NOT NULL,
    practitioner_id   BIGINT NOT NULL,
    patient_username  TEXT NOT NULL,
    sender            TEXT NOT NULL,
    body              TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at           TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ws_tokens (
    token            TEXT PRIMARY KEY,
    practitioner_id  BIGINT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    used             BOOLEAN NOT NULL DEFAULT FALSE
);
