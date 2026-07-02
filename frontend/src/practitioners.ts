import { getToken } from "./auth";
import { HTTP_BASE } from "./config";

/** A practitioner's public profile (as seen by patients). */
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

/** An appointment booked by the patient. */
export interface Appointment {
  id: number;
  patient_username: string;
  practitioner_id: number;
  requested_date: string;
  requested_time: string | null;
  reason: string | null;
  status: "pending" | "accepted" | "declined" | "completed" | "cancelled";
  patient_note: string | null;
  practitioner_note: string | null;
  created_at: string;
  decided_at: string | null;
  completed_at: string | null;
  practitioner?: Practitioner;
}

async function _authHeaders(): Promise<HeadersInit> {
  const token = await getToken();
  if (!token) throw new Error("Not authenticated");
  return { Authorization: `Bearer ${token}` };
}

/** List all active practitioners, optionally filtered by search text. */
export async function listPractitioners(
  search?: string,
  specialization?: string,
): Promise<Practitioner[]> {
  const headers = await _authHeaders();
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (specialization) params.set("specialization", specialization);
  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${HTTP_BASE}/practitioners${qs}`, { headers });
  if (!res.ok) throw new Error(`Failed to fetch practitioners: ${res.status}`);
  const data = (await res.json()) as { practitioners: Practitioner[] };
  return data.practitioners;
}

/** Get a single practitioner's public profile. */
export async function getPractitioner(id: number): Promise<Practitioner> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/practitioners/${id}`, { headers });
  if (!res.ok) throw new Error(`Failed to fetch practitioner: ${res.status}`);
  const data = (await res.json()) as { practitioner: Practitioner };
  return data.practitioner;
}

/** Book an appointment with a practitioner. */
export async function bookAppointment(body: {
  practitioner_id: number;
  requested_date: string;
  requested_time?: string | null;
  reason?: string | null;
  patient_note?: string | null;
}): Promise<Appointment> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/practitioners/appointments`, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to book appointment: ${res.status}`);
  }
  const data = (await res.json()) as { appointment: Appointment };
  return data.appointment;
}

/** List the current patient's appointments (all statuses). */
export async function getMyAppointments(): Promise<Appointment[]> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/practitioners/appointments/mine`, {
    headers,
  });
  if (!res.ok) throw new Error(`Failed to fetch appointments: ${res.status}`);
  const data = (await res.json()) as { appointments: Appointment[] };
  return data.appointments;
}

/** Cancel a pending appointment. */
export async function cancelAppointment(
  appointmentId: number,
  reason?: string,
): Promise<Appointment> {
  const headers = await _authHeaders();
  const res = await fetch(
    `${HTTP_BASE}/practitioners/appointments/${appointmentId}/cancel`,
    {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason ?? null }),
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to cancel: ${res.status}`);
  }
  const data = (await res.json()) as { appointment: Appointment };
  return data.appointment;
}
