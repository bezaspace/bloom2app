import { apiJson } from "@/lib/api";
import type { ConnectedPatient } from "@/lib/types";
import Link from "next/link";
import { Users } from "lucide-react";

export default async function PatientsPage() {
  let patients: ConnectedPatient[] = [];
  let loadError: string | null = null;
  try {
    const data = await apiJson<{ patients: ConnectedPatient[] }>("/practitioner/patients");
    patients = data.patients;
  } catch (e) {
    loadError = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-50">Connected Patients</h1>

      {loadError && (
        <div className="rounded-lg bg-red-900/40 px-4 py-3 text-sm text-red-200">
          Failed to load: {loadError}
        </div>
      )}

      {patients.length === 0 && !loadError && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-12 text-center">
          <Users className="mx-auto mb-3 h-10 w-10 text-slate-600" />
          <p className="text-slate-400">No connected patients yet.</p>
          <p className="mt-1 text-sm text-slate-500">
            Accept an appointment request to establish a connection with a patient.
          </p>
          <Link
            href="/appointments"
            className="mt-4 inline-block rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
          >
            Go to Appointments
          </Link>
        </div>
      )}

      {patients.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {patients.map((p) => (
            <Link
              key={p.username}
              href={`/patients/${p.username}`}
              className="rounded-xl border border-slate-800 bg-slate-900 p-5 transition hover:border-slate-700"
            >
              <p className="text-lg font-semibold text-slate-100">{p.username}</p>
              {p.onboarded ? (
                <>
                  <p className="mt-1 text-sm text-indigo-400">Day {p.day_of_plan} of 90-day plan</p>
                  <p className="mt-1 text-xs text-slate-500 line-clamp-2">{p.phase}</p>
                </>
              ) : (
                <p className="mt-1 text-sm text-slate-500">Not onboarded yet</p>
              )}
              <div className="mt-3 flex gap-4 text-xs text-slate-400">
                <span>{p.biomarker_count} biomarkers</span>
                <span>Connected {new Date(p.established_at).toLocaleDateString()}</span>
              </div>
              {p.has_ai_summary && (
                <span className="mt-2 inline-block rounded-full bg-indigo-500/15 px-2 py-0.5 text-xs text-indigo-400">
                  AI summary available
                </span>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
