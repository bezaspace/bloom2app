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
