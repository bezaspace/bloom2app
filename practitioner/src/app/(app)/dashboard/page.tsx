import { apiJson } from "@/lib/api";
import type { Appointment, ConnectedPatient } from "@/lib/types";
import Link from "next/link";
import { Calendar, Users, Clock } from "lucide-react";

export default async function DashboardPage() {
  let pending: Appointment[] = [];
  let patients: ConnectedPatient[] = [];
  let allAppointments: Appointment[] = [];
  let loadError: string | null = null;

  try {
    const [apptData, patientData] = await Promise.all([
      apiJson<{ appointments: Appointment[] }>("/practitioner/appointments"),
      apiJson<{ patients: ConnectedPatient[] }>("/practitioner/patients"),
    ]);
    allAppointments = apptData.appointments;
    pending = allAppointments.filter((a) => a.status === "pending");
    patients = patientData.patients;
  } catch (e) {
    loadError = e instanceof Error ? e.message : String(e);
  }

  const accepted = allAppointments.filter((a) => a.status === "accepted");
  const completed = allAppointments.filter((a) => a.status === "completed");

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-50">Dashboard</h1>

      {loadError && (
        <div className="rounded-lg bg-red-900/40 px-4 py-3 text-sm text-red-200">
          Failed to load: {loadError}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          icon={<Calendar className="h-5 w-5" />}
          label="Pending Requests"
          value={pending.length}
          accent="text-amber-400"
          href="/appointments"
        />
        <StatCard
          icon={<Users className="h-5 w-5" />}
          label="Connected Patients"
          value={patients.length}
          accent="text-indigo-400"
          href="/patients"
        />
        <StatCard
          icon={<Clock className="h-5 w-5" />}
          label="Upcoming (Accepted)"
          value={accepted.length}
          accent="text-emerald-400"
          href="/appointments"
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold text-slate-200">Pending Appointment Requests</h2>
            <Link href="/appointments" className="text-xs text-indigo-400 hover:text-indigo-300">
              View all
            </Link>
          </div>
          {pending.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-500">No pending requests.</p>
          ) : (
            <ul className="space-y-3">
              {pending.slice(0, 5).map((a) => (
                <li key={a.id} className="flex items-center justify-between rounded-lg bg-slate-800/50 px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-slate-200">{a.patient_username}</p>
                    <p className="text-xs text-slate-400">
                      {a.requested_date}{a.requested_time ? ` at ${a.requested_time}` : ""}
                    </p>
                  </div>
                  <Link
                    href="/appointments"
                    className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
                  >
                    Review
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold text-slate-200">Connected Patients</h2>
            <Link href="/patients" className="text-xs text-indigo-400 hover:text-indigo-300">
              View all
            </Link>
          </div>
          {patients.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-500">
              No connected patients yet. Accept an appointment to connect.
            </p>
          ) : (
            <ul className="space-y-3">
              {patients.slice(0, 5).map((p) => (
                <li key={p.username} className="flex items-center justify-between rounded-lg bg-slate-800/50 px-4 py-3">
                  <div>
                    <p className="text-sm font-medium text-slate-200">{p.username}</p>
                    <p className="text-xs text-slate-400">
                      {p.onboarded ? `Day ${p.day_of_plan} of plan` : "Not onboarded"} · {p.biomarker_count} biomarkers
                    </p>
                  </div>
                  <Link
                    href={`/patients/${p.username}`}
                    className="rounded-md border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:border-slate-600"
                  >
                    View
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {completed.length > 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <h2 className="mb-4 font-semibold text-slate-200">Recent Completed Appointments</h2>
          <ul className="space-y-2">
            {completed.slice(0, 5).map((a) => (
              <li key={a.id} className="flex items-center justify-between text-sm">
                <span className="text-slate-300">{a.patient_username}</span>
                <span className="text-slate-500">{a.requested_date}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  accent,
  href,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  accent: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="rounded-xl border border-slate-800 bg-slate-900 p-5 transition hover:border-slate-700"
    >
      <div className={`mb-2 ${accent}`}>{icon}</div>
      <p className="text-3xl font-bold text-slate-50">{value}</p>
      <p className="mt-1 text-sm text-slate-400">{label}</p>
    </Link>
  );
}
