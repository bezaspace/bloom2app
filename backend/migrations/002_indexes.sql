-- 002_indexes.sql
-- All secondary indexes for Bloom2.

-- biomarkers
CREATE INDEX IF NOT EXISTS idx_biomarkers_user_name
    ON biomarkers (username, name, measured_at);

-- appointments
CREATE INDEX IF NOT EXISTS idx_appointments_patient
    ON appointments (patient_username, status);
CREATE INDEX IF NOT EXISTS idx_appointments_practitioner
    ON appointments (practitioner_id, status);

-- practitioner_notes
CREATE INDEX IF NOT EXISTS idx_practitioner_notes
    ON practitioner_notes (practitioner_id, patient_username, created_at);

-- plans
CREATE INDEX IF NOT EXISTS idx_plans_patient_active
    ON plans (patient_username, is_active);

-- plan_metrics
CREATE INDEX IF NOT EXISTS idx_plan_metrics_plan
    ON plan_metrics (plan_id, sort_order);

-- plan_drafts
CREATE INDEX IF NOT EXISTS idx_plan_drafts_patient_unpublished
    ON plan_drafts (patient_username, is_published);

-- plan_suggestions
CREATE INDEX IF NOT EXISTS idx_plan_suggestions_patient
    ON plan_suggestions (patient_username, status);

-- chat_messages
CREATE INDEX IF NOT EXISTS idx_chat_conv_id
    ON chat_messages (conversation_id, id);
CREATE INDEX IF NOT EXISTS idx_chat_practitioner
    ON chat_messages (practitioner_id, patient_username, id);
CREATE INDEX IF NOT EXISTS idx_chat_patient
    ON chat_messages (patient_username, id);
