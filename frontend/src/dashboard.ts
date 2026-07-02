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
