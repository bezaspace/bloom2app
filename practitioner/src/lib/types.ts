/** Hand-mirrored backend types for the practitioner app. Keep in sync with
 * the FastAPI response shapes in backend/app/practitioner_db.py and
 * backend/app/practitioner_routes.py. */

export interface Practitioner {
  id: number;
  username: string;
  full_name: string;
  title: string | null;
  specialization: string | null;
  bio: string | null;
  email: string | null;
  phone: string | null;
  years_experience: number | null;
  consultation_fee: number | null;
  is_active: boolean;
  created_at: string;
}

export type AppointmentStatus =
  | "pending"
  | "accepted"
  | "declined"
  | "completed"
  | "cancelled";

export interface Appointment {
  id: number;
  patient_username: string;
  practitioner_id: number;
  requested_date: string;
  requested_time: string | null;
  reason: string | null;
  status: AppointmentStatus;
  patient_note: string | null;
  practitioner_note: string | null;
  created_at: string;
  decided_at: string | null;
  completed_at: string | null;
}

export interface ConnectedPatient {
  username: string;
  onboarded: boolean;
  day_of_plan: number;
  phase: string;
  biomarker_count: number;
  established_at: string;
  has_ai_summary: boolean;
}

export interface ScheduleItem {
  time: string;
  title: string;
  domain: string;
  duration_min?: number | null;
  detail?: string;
  target?: Record<string, number> | null;
}

export interface DailySchedule {
  date: string;
  day_of_plan: number;
  phase: string;
  focus_today: string;
  items: ScheduleItem[];
  daily_targets: Record<string, number>;
  motivation_note: string;
}

export interface LogEntry {
  key: string;
  completed?: boolean;
  value?: number | null;
  note?: string | null;
}

export interface PatientDetail {
  status: string;
  username: string;
  onboarded: boolean;
  onboarded_at: string | null;
  profile: Record<string, unknown> | null;
  plan: {
    summary?: string;
    phases?: { name: string; focus: string; actions: string[] }[];
    weekly_rhythm?: string;
  } | null;
  doc_summary: Record<string, unknown> | null;
  date: string;
  schedule: DailySchedule | null;
  logs: Record<string, LogEntry[]>;
  biomarker_count: number;
}

export interface BiomarkerReading {
  id: number;
  name: string;
  value: number;
  unit: string;
  ref_low: number | null;
  ref_high: number | null;
  optimal_low: number | null;
  optimal_high: number | null;
  status: "low" | "normal" | "high" | "unknown";
  source_doc: string;
  measured_at: string | null;
  extracted_at: string;
}

export interface BiomarkerGroup {
  name: string;
  unit: string;
  ref_low: number | null;
  ref_high: number | null;
  optimal_low: number | null;
  optimal_high: number | null;
  readings: BiomarkerReading[];
}

export interface RecentLogsResponse {
  status: string;
  domain: string;
  days: number;
  logs: { date: string; entries: LogEntry[] }[];
}

export interface PractitionerNote {
  id: number;
  practitioner_id: number;
  patient_username: string;
  note_text: string;
  created_at: string;
}

export interface AISummary {
  summary: string;
  notable_items: string[];
  generated_for_date: string;
}

// ---------------------------------------------------------------------------
// Tracking plan types (mirrors backend/app/plan_db.py)
// ---------------------------------------------------------------------------
export interface PlanMetric {
  id: number;
  plan_id: number;
  template_id: string;
  label: string;
  unit: string;
  frequency: string;
  time_of_day: string | null;
  target_type: string;
  target_value: number | null;
  target_high: number | null;
  is_active: boolean;
  phase: number | null;
  sort_order: number;
}

export interface PlanOutcome {
  id: number;
  plan_id: number;
  biomarker_name: string;
  target_value: number;
  target_direction: string;
  target_high: number | null;
  unit: string;
  target_date: string | null;
  current_value: number | null;
  current_as_of: string | null;
}

export interface PlanPhase {
  id: number;
  plan_id: number;
  phase_number: number;
  name: string;
  focus: string | null;
  actions: string[];
  day_start: number;
  day_end: number;
}

export interface TrackingPlan {
  id: number;
  patient_username: string;
  practitioner_id: number | null;
  version: number;
  is_active: boolean;
  title: string | null;
  rationale: string | null;
  created_at: string;
  updated_at: string;
  outcomes: PlanOutcome[];
  metrics: PlanMetric[];
  phases: PlanPhase[];
}

export interface PlanDraft {
  id: number;
  patient_username: string;
  practitioner_id: number | null;
  status: "draft" | "published" | "archived";
  draft_data: TrackingPlan;
  created_at: string;
  updated_at: string;
}

export interface MetricTemplate {
  template_id: string;
  label: string;
  category: string;
  unit: string;
  default_target_type: string;
  default_target_value: number | null;
  default_frequency: string;
  description: string;
}

export interface AdherenceMetric {
  metric_id: number;
  label: string;
  template_id: string;
  unit: string;
  frequency: string;
  target_type: string;
  target: number | null;
  target_high: number | null;
  actual: number | null;
  adherence: number | null;
  phase: number | null;
}

export interface AdherenceResponse {
  status: string;
  date: string;
  plan_id?: number;
  plan_title?: string | null;
  metrics: AdherenceMetric[];
  overall?: number | null;
}

export interface AdherenceSummaryMetric {
  metric_id: number;
  label: string;
  template_id: string;
  unit: string;
  target_type: string;
  target: number | null;
  adherence_avg: number | null;
  days_with_data: number;
}

export interface AdherenceSummaryResponse {
  status: string;
  days: number;
  metrics: AdherenceSummaryMetric[];
  overall?: number | null;
}

export interface TrendEntry {
  metric_id: number;
  label: string;
  template_id: string;
  unit: string;
  direction: "up" | "down" | "steady" | "unknown";
  magnitude: number | null;
  recent_avg: number | null;
  prior_avg: number | null;
  slope: number | null;
  n_points: number;
}

export interface TrendsResponse {
  status: string;
  days: number;
  trends: TrendEntry[];
}

export interface OutcomeProgress {
  biomarker_name: string;
  target_value: number;
  target_direction: string;
  target_high: number | null;
  unit: string;
  target_date: string | null;
  current_value: number | null;
  current_as_of: string | null;
  prior_value: number | null;
  delta: number | null;
  on_track: boolean | null;
  n_readings: number;
}

export interface BiomarkerProgressResponse {
  status: string;
  outcomes: OutcomeProgress[];
}

export interface DesignAgentMessage {
  role: "user" | "assistant";
  text: string;
}

export interface DesignAgentResponse {
  status: string;
  reply: string;
  draft: TrackingPlan | null;
  draft_id: number | null;
}

// ---------------------------------------------------------------------------
// Plan suggestions (AI-proposed adjustments for practitioner approval)
// ---------------------------------------------------------------------------
export interface PlanSuggestion {
  id: number;
  patient_username: string;
  practitioner_id: number | null;
  source: string;
  suggestion: {
    type?: string;
    title?: string;
    description?: string;
    rationale?: string;
    metric?: Partial<PlanMetric>;
    outcome?: Partial<PlanOutcome>;
    action?: string;
    [key: string]: unknown;
  };
  status: "pending" | "approved" | "dismissed";
  created_at: string;
  decided_at: string | null;
  decided_by: number | null;
}
