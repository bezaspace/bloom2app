import { apiJson } from "@/lib/api";
import type { Appointment, AppointmentStatus } from "@/lib/types";
import { AppointmentActions } from "@/components/appointments/AppointmentActions";

const STATUS_STYLES: Record<AppointmentStatus, string> = {
  pending: "bg-amber-500/15 text-amber-400",
  accepted: "bg-emerald-500/15 text-emerald-400",
  declined: "bg-red-500/15 text-red-400",
  completed: "bg-indigo-500/15 text-indigo-400",
  cancelled: "bg-slate-500/15 text-slate-400",
};

export default async function AppointmentsPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string }>;
}) {
  const { status } = await searchParams;
  const filter = status && ["pending", "accepted", "declined", "completed", "cancelled"].includes(status)
    ? `?status=${status}`
    : "";

  let appointments: Appointment[] = [];
  let loadError: string | null = null;
  try {
    const data = await apiJson<{ appointments: Appointment[] }>(
      `/practitioner/appointments${filter}`,
    );
    appointments = data.appointments;
  } catch (e) {
    loadError = e instanceof Error ? e.message : String(e);
  }

  const FILTERS: { label: string; value: string | undefined }[] = [
    { label: "All", value: undefined },
    { label: "Pending", value: "pending" },
    { label: "Accepted", value: "accepted" },
    { label: "Completed", value: "completed" },
    { label: "Declined", value: "declined" },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-50">Appointments</h1>

      {loadError && (
        <div className="rounded-lg bg-red-900/40 px-4 py-3 text-sm text-red-200">
          Failed to load: {loadError}
        </div>
      )}

      <div className="flex gap-2">
        {FILTERS.map((f) => {
          const active = (status ?? undefined) === f.value;
          const href = f.value ? `/appointments?status=${f.value}` : "/appointments";
          return (
            <a
              key={f.label}
              href={href}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                active
                  ? "bg-indigo-600 text-white"
                  : "border border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-200"
              }`}
            >
              {f.label}
            </a>
          );
        })}
      </div>

      {appointments.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-12 text-center">
          <p className="text-slate-500">No appointments to show.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-800 bg-slate-800/50 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">Patient</th>
                <th className="px-4 py-3 font-medium">Date / Time</th>
                <th className="px-4 py-3 font-medium">Reason</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {appointments.map((a) => (
                <tr key={a.id} className="hover:bg-slate-800/30">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-200">{a.patient_username}</div>
                    {a.patient_note && (
                      <div className="mt-0.5 max-w-xs truncate text-xs text-slate-500" title={a.patient_note}>
                        &ldquo;{a.patient_note}&rdquo;
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {a.requested_date}
                    {a.requested_time && <div className="text-xs text-slate-500">{a.requested_time}</div>}
                  </td>
                  <td className="max-w-xs px-4 py-3 text-slate-400">
                    {a.reason ? <span className="truncate">{a.reason}</span> : <span className="text-slate-600">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2.5 py-1 text-xs font-semibold uppercase ${STATUS_STYLES[a.status]}`}>
                      {a.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <AppointmentActions appointment={a} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
