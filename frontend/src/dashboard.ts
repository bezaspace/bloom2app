import { getToken } from "./auth";
import { HTTP_BASE } from "./config";

/** Wellness domains tracked across the dashboard. */
export const WELLNESS_DOMAINS = [
  "workout",
  "diet",
  "medication",
  "mental_health",
  "meditation",
  "other",
] as const;
export type WellnessDomain = (typeof WELLNESS_DOMAINS)[number];

/** A single timed entry in the user's day. */
export interface ScheduleItem {
  time: string;
  title: string;
  domain: WellnessDomain | string;
  metric_id?: number | null;
  duration_min?: number | null;
  detail?: string;
  target?: Record<string, number> | null;
}

/** The full AI-generated plan for a single day. */
export interface DailySchedule {
  date: string;
  day_of_plan: number;
  phase: string;
  focus_today: string;
  items: ScheduleItem[];
  daily_targets: Record<string, number>;
  motivation_note: string;
}

/** A single user log entry within a domain for a day. */
export interface LogEntry {
  key: string;
  completed?: boolean;
  value?: number | null;
  note?: string | null;
  metric_id?: number | null;
}

/** A biomarker reading extracted from a lab document. */
export interface BiomarkerReading {
  id: number;
  name: string;
  value: number;
  unit: string;
  ref_low?: number | null;
  ref_high?: number | null;
  optimal_low?: number | null;
  optimal_high?: number | null;
  status: "low" | "normal" | "high" | "unknown";
  source_doc: string;
  measured_at?: string | null;
  extracted_at: string;
}

/** A grouped biomarker (one per marker name) for the overview grid. */
export interface BiomarkerGroup {
  name: string;
  unit: string;
  ref_low?: number | null;
  ref_high?: number | null;
  optimal_low?: number | null;
  optimal_high?: number | null;
  readings: BiomarkerReading[];
}

/** Response from GET /dashboard/today. */
export interface DashboardToday {
  date: string;
  onboarded: boolean;
  day_of_plan: number;
  phase: string;
  plan_summary?: string | null;
  plan_phase_focus?: string | null;
  schedule?: DailySchedule | null;
  logs: Record<string, LogEntry[]>;
  biomarker_count: number;
}

/** Response from GET /dashboard/logs/recent. */
export interface RecentLogsResponse {
  status: "success" | "error";
  domain: string;
  days: number;
  logs: { date: string; entries: LogEntry[] }[];
}

/** Response from GET /dashboard/biomarkers. */
export interface BiomarkersResponse {
  status: "success" | "error";
  groups: BiomarkerGroup[];
}

async function _authHeaders(): Promise<HeadersInit> {
  const token = await getToken();
  if (!token) throw new Error("Not authenticated");
  return { Authorization: `Bearer ${token}` };
}

/** Fetch the dashboard data for today (schedule, logs, plan summary, biomarker count). */
export async function getDashboardToday(): Promise<DashboardToday> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/dashboard/today`, { headers });
  if (!res.ok) throw new Error(`Failed to fetch dashboard: ${res.status}`);
  return (await res.json()) as DashboardToday;
}

/** Force regeneration of today's schedule. */
export async function regenerateSchedule(): Promise<DailySchedule> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/dashboard/schedule/regenerate`, {
    method: "POST",
    headers,
  });
  if (!res.ok) throw new Error(`Failed to regenerate schedule: ${res.status}`);
  const data = await res.json();
  return data.schedule as DailySchedule;
}

/** Upsert a per-domain daily log (replaces prior entries for that domain on that date). */
export async function saveDailyLog(
  date: string,
  domain: string,
  entries: LogEntry[],
): Promise<void> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/dashboard/log`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({ date, domain, entries }),
  });
  if (!res.ok) throw new Error(`Failed to save log: ${res.status}`);
}

/** Fetch the last `days` days of logs for a single domain (for 7-day bar charts). */
export async function getRecentLogs(
  domain: string,
  days = 7,
): Promise<RecentLogsResponse> {
  const headers = await _authHeaders();
  const res = await fetch(
    `${HTTP_BASE}/dashboard/logs/recent?domain=${encodeURIComponent(domain)}&days=${days}`,
    { headers },
  );
  if (!res.ok) throw new Error(`Failed to fetch recent logs: ${res.status}`);
  return (await res.json()) as RecentLogsResponse;
}

/** Fetch all biomarker readings grouped by marker name. */
export async function getBiomarkers(): Promise<BiomarkerGroup[]> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/dashboard/biomarkers`, { headers });
  if (!res.ok) throw new Error(`Failed to fetch biomarkers: ${res.status}`);
  const data = (await res.json()) as BiomarkersResponse;
  return data.groups;
}

/** Re-run biomarker extraction over all uploaded lab documents. */
export async function refreshBiomarkersFromDocs(): Promise<{
  extracted: number;
  skipped: number;
}> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/dashboard/biomarkers/refresh-from-docs`, {
    method: "POST",
    headers,
  });
  if (!res.ok) throw new Error(`Failed to refresh biomarkers: ${res.status}`);
  return (await res.json()) as { extracted: number; skipped: number };
}

// ---------------------------------------------------------------------------
// Tracking plan types + API functions
// ---------------------------------------------------------------------------
/** A metric in a practitioner-designed tracking plan. */
export interface PlanMetric {
  id: number;
  plan_id: number;
  template_id: string;
  label: string;
  unit: string;
  frequency: string;
  time_of_day?: string | null;
  target_type: string;
  target_value?: number | null;
  target_high?: number | null;
  is_active: boolean;
  phase?: number | null;
  sort_order: number;
}

/** An outcome target (biomarker goal) in a tracking plan. */
export interface PlanOutcome {
  id: number;
  plan_id: number;
  biomarker_name: string;
  target_value: number;
  target_direction: string;
  target_high?: number | null;
  unit: string;
  target_date?: string | null;
  current_value?: number | null;
  current_as_of?: string | null;
}

/** A phase in a tracking plan. */
export interface PlanPhase {
  id: number;
  plan_id: number;
  phase_number: number;
  name: string;
  focus?: string;
  actions: string[];
  day_start: number;
  day_end: number;
}

/** A practitioner-designed tracking plan. */
export interface TrackingPlan {
  id: number;
  patient_username: string;
  practitioner_id?: number | null;
  version: number;
  is_active: boolean;
  title?: string | null;
  rationale?: string | null;
  created_at: string;
  updated_at: string;
  outcomes: PlanOutcome[];
  metrics: PlanMetric[];
  phases: PlanPhase[];
}

/** Response from GET /plan. */
export interface PlanResponse {
  status: "success";
  plan: TrackingPlan | null;
}

/** Response from GET /analytics/adherence (single date). */
export interface AdherenceMetric {
  metric_id: number;
  label: string;
  template_id: string;
  unit: string;
  frequency: string;
  target_type: string;
  target?: number | null;
  target_high?: number | null;
  actual?: number | null;
  adherence?: number | null;
  phase?: number | null;
}

export interface AdherenceResponse {
  status: "success";
  date: string;
  plan_id?: number;
  plan_title?: string | null;
  metrics: AdherenceMetric[];
  overall?: number | null;
}

/** Response from GET /analytics/adherence (summary over N days). */
export interface AdherenceSummaryMetric {
  metric_id: number;
  label: string;
  template_id: string;
  unit: string;
  target_type: string;
  target?: number | null;
  adherence_avg?: number | null;
  days_with_data: number;
}

export interface AdherenceSummaryResponse {
  status: "success";
  days: number;
  metrics: AdherenceSummaryMetric[];
  overall?: number | null;
}

/** Response from GET /analytics/trends. */
export interface TrendEntry {
  metric_id: number;
  label: string;
  template_id: string;
  unit: string;
  direction: "up" | "down" | "steady" | "unknown";
  magnitude?: number | null;
  recent_avg?: number | null;
  prior_avg?: number | null;
  slope?: number | null;
  n_points: number;
}

export interface TrendsResponse {
  status: "success";
  days: number;
  trends: TrendEntry[];
}

/** Response from GET /analytics/biomarker-progress. */
export interface OutcomeProgress {
  biomarker_name: string;
  target_value: number;
  target_direction: string;
  target_high?: number | null;
  unit: string;
  target_date?: string | null;
  current_value?: number | null;
  current_as_of?: string | null;
  prior_value?: number | null;
  delta?: number | null;
  on_track?: boolean | null;
  n_readings: number;
}

export interface BiomarkerProgressResponse {
  status: "success";
  outcomes: OutcomeProgress[];
}

/** Response from GET /insights/weekly-report. */
export interface WeeklyReport {
  narrative: string;
  highlights: string[];
  concerns: string[];
  generated_for_week: string;
}

/** Response from GET /insights/trend-alerts. */
export interface TrendAlert {
  metric: string;
  severity: "info" | "warning" | "critical";
  message: string;
}

/** Response from GET /logs/today. */
export interface TodayLogsResponse {
  status: "success";
  date: string;
  logs: Record<string, LogEntry[]>;
}

/** Response from GET /logs/recent. */
export interface RecentMetricLogsResponse {
  status: "success";
  metric_id: number;
  days: number;
  logs: { date: string; entries: LogEntry[] }[];
}

/** Fetch the current user's active tracking plan. */
export async function getPlan(): Promise<TrackingPlan | null> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/plan`, { headers });
  if (!res.ok) throw new Error(`Failed to fetch plan: ${res.status}`);
  const data = (await res.json()) as PlanResponse;
  return data.plan;
}

/** Log a metric value (appends to today's entries for the metric). */
export async function logMetric(
  metricId: number,
  value?: number | null,
  note?: string | null,
  completed = true,
  logDate?: string,
): Promise<void> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/logs`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({
      metric_id: metricId,
      value: value ?? null,
      note: note ?? null,
      completed,
      date: logDate,
    }),
  });
  if (!res.ok) throw new Error(`Failed to log metric: ${res.status}`);
}

/** Fetch today's logs for all active metrics (keyed by metric_id as string). */
export async function getTodayMetricLogs(): Promise<Record<string, LogEntry[]>> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/logs/today`, { headers });
  if (!res.ok) throw new Error(`Failed to fetch today logs: ${res.status}`);
  const data = (await res.json()) as TodayLogsResponse;
  return data.logs;
}

/** Fetch the last `days` days of logs for a single metric. */
export async function getRecentMetricLogs(
  metricId: number,
  days = 7,
): Promise<{ date: string; entries: LogEntry[] }[]> {
  const headers = await _authHeaders();
  const res = await fetch(
    `${HTTP_BASE}/logs/recent?metric_id=${metricId}&days=${days}`,
    { headers },
  );
  if (!res.ok) throw new Error(`Failed to fetch recent metric logs: ${res.status}`);
  const data = (await res.json()) as RecentMetricLogsResponse;
  return data.logs;
}

/** Fetch per-metric adherence for today (or a summary over N days). */
export async function getAdherence(date?: string): Promise<AdherenceResponse>;
export async function getAdherence(days: number): Promise<AdherenceSummaryResponse>;
export async function getAdherence(
  dateOrDays?: string | number,
): Promise<AdherenceResponse | AdherenceSummaryResponse> {
  const headers = await _authHeaders();
  const url =
    typeof dateOrDays === "number"
      ? `${HTTP_BASE}/analytics/adherence?days=${dateOrDays}`
      : `${HTTP_BASE}/analytics/adherence${dateOrDays ? `?date=${dateOrDays}` : ""}`;
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`Failed to fetch adherence: ${res.status}`);
  return (await res.json()) as AdherenceResponse | AdherenceSummaryResponse;
}

/** Fetch trend analysis for the last N days. */
export async function getTrends(days = 14): Promise<TrendEntry[]> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/analytics/trends?days=${days}`, { headers });
  if (!res.ok) throw new Error(`Failed to fetch trends: ${res.status}`);
  const data = (await res.json()) as TrendsResponse;
  return data.trends;
}

/** Fetch outcome target progress (biomarker goals). */
export async function getBiomarkerProgress(): Promise<OutcomeProgress[]> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/analytics/biomarker-progress`, { headers });
  if (!res.ok) throw new Error(`Failed to fetch biomarker progress: ${res.status}`);
  const data = (await res.json()) as BiomarkerProgressResponse;
  return data.outcomes;
}

/** Fetch the AI weekly report. */
export async function getWeeklyReport(): Promise<WeeklyReport> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/insights/weekly-report`, { headers });
  if (!res.ok) throw new Error(`Failed to fetch weekly report: ${res.status}`);
  const data = (await res.json()) as { status: string; report: WeeklyReport };
  return data.report;
}

/** Fetch AI trend alerts. */
export async function getTrendAlerts(): Promise<TrendAlert[]> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/insights/trend-alerts`, { headers });
  if (!res.ok) throw new Error(`Failed to fetch trend alerts: ${res.status}`);
  const data = (await res.json()) as { status: string; alerts: TrendAlert[] };
  return data.alerts;
}
