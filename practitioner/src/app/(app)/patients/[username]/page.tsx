import { apiJson } from "@/lib/api";
import type { PatientDetail, BiomarkerGroup, PractitionerNote } from "@/lib/types";
import Link from "next/link";
import { ChatLink, AISummaryCard, NotesPanel, PlanDesignerLink, AnalyticsLink, MessagePatientLink } from "@/components/patients/PatientPanels";

export default async function PatientDetailPage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = await params;

  let patient: PatientDetail | null = null;
  let biomarkers: BiomarkerGroup[] = [];
  let notes: PractitionerNote[] = [];
  let loadError: string | null = null;

  try {
    const [patientData, bioData, notesData] = await Promise.all([
      apiJson<PatientDetail>(`/practitioner/patients/${encodeURIComponent(username)}`),
      apiJson<{ groups: BiomarkerGroup[] }>(
        `/practitioner/patients/${encodeURIComponent(username)}/biomarkers`,
      ),
      apiJson<{ notes: PractitionerNote[] }>(
        `/practitioner/patients/${encodeURIComponent(username)}/notes`,
      ),
    ]);
    patient = patientData;
    biomarkers = bioData.groups;
    notes = notesData.notes;
  } catch (e) {
    loadError = e instanceof Error ? e.message : String(e);
  }

  if (loadError) {
    return (
      <div className="space-y-4">
        <Link href="/patients" className="text-sm text-indigo-400 hover:text-indigo-300">
          &larr; Back to patients
        </Link>
        <div className="rounded-lg bg-red-900/40 px-4 py-3 text-sm text-red-200">
          {loadError}
        </div>
      </div>
    );
  }

  if (!patient) return null;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/patients" className="text-sm text-indigo-400 hover:text-indigo-300">
          &larr; Back to patients
        </Link>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h1 className="text-2xl font-bold text-slate-50">{patient.username}</h1>
        {patient.onboarded ? (
          <p className="mt-1 text-sm text-indigo-400">
            Day {patient.schedule?.day_of_plan ?? "?"} of 90-day plan · {patient.schedule?.phase ?? ""}
          </p>
        ) : (
          <p className="mt-1 text-sm text-slate-500">Not onboarded yet</p>
        )}
        {patient.plan?.summary && (
          <p className="mt-3 text-sm text-slate-300">{patient.plan.summary}</p>
        )}
        {patient.schedule?.focus_today && (
          <p className="mt-2 text-sm text-slate-400">
            <span className="font-medium text-slate-300">Today&apos;s focus:</span> {patient.schedule.focus_today}
          </p>
        )}
      </div>

      {!patient.onboarded && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-8 text-center text-slate-500">
          This patient hasn&apos;t completed onboarding yet. Check back later.
        </div>
      )}

      {patient.onboarded && (
        <>
          <AISummaryCard username={username} />

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <h2 className="mb-4 font-semibold text-slate-200">Today&apos;s Schedule</h2>
            {patient.schedule?.items?.length ? (
              <ul className="space-y-2">
                {patient.schedule.items.map((item, i) => {
                  const logEntries = patient!.logs[item.domain] ?? [];
                  const done = logEntries.some((e) => e.key === item.title && e.completed);
                  return (
                    <li
                      key={i}
                      className="flex items-center gap-3 rounded-lg bg-slate-800/40 px-4 py-2.5"
                    >
                      <span className="w-12 text-xs font-mono text-slate-400">{item.time}</span>
                      <span
                        className={`h-2 w-2 rounded-full ${done ? "bg-emerald-500" : "bg-slate-600"}`}
                      />
                      <span className="flex-1 text-sm text-slate-200">{item.title}</span>
                      <span className="text-xs text-slate-500">{item.domain}</span>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm text-slate-500">No schedule generated for today.</p>
            )}
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <h2 className="mb-4 font-semibold text-slate-200">Wellness Domain Logs (Today)</h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {["workout", "diet", "meditation", "medication", "mental_health", "other"].map((domain) => {
                const entries = patient!.logs[domain] ?? [];
                const count = entries.length;
                const completed = entries.filter((e) => e.completed).length;
                return (
                  <div key={domain} className="rounded-lg bg-slate-800/40 p-3">
                    <p className="text-xs font-medium uppercase text-slate-400">{domain}</p>
                    <p className="mt-1 text-lg font-semibold text-slate-100">
                      {completed}/{count}
                    </p>
                    <p className="text-xs text-slate-500">entries done</p>
                  </div>
                );
              })}
            </div>
          </div>

          {biomarkers.length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <h2 className="mb-4 font-semibold text-slate-200">Biomarkers</h2>
              <div className="space-y-4">
                {biomarkers.map((g) => {
                  const latest = g.readings[g.readings.length - 1];
                  const prior = g.readings.length > 1 ? g.readings[g.readings.length - 2] : null;
                  const delta = prior ? latest.value - prior.value : null;
                  return (
                    <div key={g.name} className="rounded-lg bg-slate-800/40 p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="font-medium text-slate-200">{g.name}</p>
                          <p className="text-xs text-slate-500">
                            Latest: {latest.value} {g.unit}
                            {delta !== null && (
                              <span className={delta < 0 ? "text-emerald-400" : delta > 0 ? "text-amber-400" : "text-slate-400"}>
                                {" "}({delta > 0 ? "+" : ""}{delta.toFixed(2)})
                              </span>
                            )}
                          </p>
                        </div>
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-semibold uppercase ${
                            latest.status === "normal"
                              ? "bg-emerald-500/15 text-emerald-400"
                              : latest.status === "low"
                              ? "bg-amber-500/15 text-amber-400"
                              : latest.status === "high"
                              ? "bg-red-500/15 text-red-400"
                              : "bg-slate-500/15 text-slate-400"
                          }`}
                        >
                          {latest.status}
                        </span>
                      </div>
                      {g.ref_low !== null && g.ref_high !== null && (
                        <p className="mt-1 text-xs text-slate-500">
                          Ref: {g.ref_low}–{g.ref_high} {g.unit}
                        </p>
                      )}
                      <p className="mt-1 text-xs text-slate-500">
                        {g.readings.length} reading{g.readings.length !== 1 ? "s" : ""}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {patient.doc_summary && Object.keys(patient.doc_summary).length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <h2 className="mb-3 font-semibold text-slate-200">Health Document Summary</h2>
              <DocSummaryView summary={patient.doc_summary} />
            </div>
          )}

          <NotesPanel username={username} notes={notes} />

          <ChatLink username={username} />
          <MessagePatientLink username={username} />
          <PlanDesignerLink username={username} />
          <AnalyticsLink username={username} />
        </>
      )}
    </div>
  );
}

function DocSummaryView({ summary }: { summary: Record<string, unknown> }) {
  const conditions = (summary.conditions as string[] | undefined) ?? [];
  const medications = (summary.medications as string[] | undefined) ?? [];
  const allergies = (summary.allergies as string[] | undefined) ?? [];
  const freeText = (summary.free_text_summary as string | undefined) ?? "";
  return (
    <div className="space-y-2 text-sm text-slate-300">
      {conditions.length > 0 && (
        <p><span className="text-slate-500">Conditions:</span> {conditions.join(", ")}</p>
      )}
      {medications.length > 0 && (
        <p><span className="text-slate-500">Medications:</span> {medications.join(", ")}</p>
      )}
      {allergies.length > 0 && (
        <p><span className="text-slate-500">Allergies:</span> {allergies.join(", ")}</p>
      )}
      {freeText && <p className="italic text-slate-400">{freeText}</p>}
    </div>
  );
}
