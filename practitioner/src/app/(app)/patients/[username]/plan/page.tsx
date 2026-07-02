import Link from "next/link";
import { apiJson } from "@/lib/api";
import type { TrackingPlan, MetricTemplate, PatientDetail, PlanSuggestion } from "@/lib/types";
import { PlanDesignerClient } from "@/components/patients/PlanDesignerClient";
import { PlanSuggestionsPanel } from "@/components/patients/PlanSuggestionsPanel";

export default async function PlanDesignerPage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = await params;

  let plan: TrackingPlan | null = null;
  let templates: MetricTemplate[] = [];
  let patient: PatientDetail | null = null;
  let suggestions: PlanSuggestion[] = [];
  let loadError: string | null = null;

  try {
    const [planRes, templatesRes, patientRes, suggRes] = await Promise.all([
      apiJson<{ status: string; plan: TrackingPlan | null }>(
        `/practitioner/patients/${encodeURIComponent(username)}/plan`,
      ).catch(() => null),
      apiJson<{ status: string; templates: MetricTemplate[] }>(
        "/practitioner/plan-templates",
      ).catch(() => ({ status: "ok", templates: [] as MetricTemplate[] })),
      apiJson<PatientDetail>(
        `/practitioner/patients/${encodeURIComponent(username)}`,
      ).catch(() => null),
      apiJson<{ status: string; suggestions: PlanSuggestion[] }>(
        `/practitioner/patients/${encodeURIComponent(username)}/plan/suggestions`,
      ).catch(() => ({ status: "ok", suggestions: [] as PlanSuggestion[] })),
    ]);
    plan = planRes?.plan ?? null;
    templates = templatesRes.templates;
    patient = patientRes;
    suggestions = suggRes.suggestions;
  } catch (e) {
    loadError = e instanceof Error ? e.message : String(e);
  }

  if (loadError) {
    return (
      <div className="space-y-4">
        <Link
          href={`/patients/${encodeURIComponent(username)}`}
          className="text-sm text-indigo-400 hover:text-indigo-300"
        >
          &larr; Back to {username}
        </Link>
        <div className="rounded-lg bg-red-900/40 px-4 py-3 text-sm text-red-200">
          {loadError}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div>
        <Link
          href={`/patients/${encodeURIComponent(username)}`}
          className="text-sm text-indigo-400 hover:text-indigo-300"
        >
          &larr; Back to {username}
        </Link>
      </div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-50">
          Plan Designer — {username}
        </h1>
      </div>
      <div className="rounded-lg border border-amber-500/30 bg-amber-950/20 px-4 py-2 text-xs text-amber-300">
        Design a personalized tracking plan with AI assistance or manually.
        The plan will replace any existing active plan when published.
      </div>
      <PlanDesignerClient
        username={username}
        initialPlan={plan}
        templates={templates}
        patientProfile={patient?.profile ?? null}
        patientDocSummary={patient?.doc_summary ?? null}
      />
      {/* AI Plan Suggestions (only show if a plan is active) */}
      {plan ? (
        <PlanSuggestionsPanel username={username} initialSuggestions={suggestions} />
      ) : null}
    </div>
  );
}
