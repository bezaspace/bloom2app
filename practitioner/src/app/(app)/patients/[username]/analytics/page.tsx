import Link from "next/link";
import { apiJson } from "@/lib/api";
import type {
  TrackingPlan,
  AdherenceSummaryResponse,
  TrendsResponse,
  BiomarkerProgressResponse,
  PatientDetail,
} from "@/lib/types";
import { AnalyticsDashboard } from "@/components/patients/AnalyticsDashboard";

export default async function AnalyticsPage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = await params;

  let plan: TrackingPlan | null = null;
  let adherence: AdherenceSummaryResponse | null = null;
  let trends: TrendsResponse | null = null;
  let outcomes: BiomarkerProgressResponse | null = null;
  let patient: PatientDetail | null = null;
  let loadError: string | null = null;

  try {
    const [planRes, adRes, trendRes, outcomeRes, patientRes] = await Promise.all([
      apiJson<{ status: string; plan: TrackingPlan | null }>(
        `/practitioner/patients/${encodeURIComponent(username)}/plan`,
      ).catch(() => null),
      apiJson<AdherenceSummaryResponse>(
        `/practitioner/patients/${encodeURIComponent(username)}/analytics/adherence?days=30`,
      ).catch(() => null),
      apiJson<TrendsResponse>(
        `/practitioner/patients/${encodeURIComponent(username)}/analytics/trends?days=30`,
      ).catch(() => null),
      apiJson<BiomarkerProgressResponse>(
        `/practitioner/patients/${encodeURIComponent(username)}/analytics/biomarker-progress`,
      ).catch(() => null),
      apiJson<PatientDetail>(
        `/practitioner/patients/${encodeURIComponent(username)}`,
      ).catch(() => null),
    ]);
    plan = planRes?.plan ?? null;
    adherence = adRes;
    trends = trendRes;
    outcomes = outcomeRes;
    patient = patientRes;
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
      <h1 className="text-xl font-bold text-slate-50">
        Analytics — {username}
      </h1>
      {!plan ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-center text-sm text-slate-500">
          No tracking plan active for this patient.{" "}
          <Link
            href={`/patients/${encodeURIComponent(username)}/plan`}
            className="text-indigo-400 hover:text-indigo-300"
          >
            Design a plan →
          </Link>
        </div>
      ) : (
        <AnalyticsDashboard
          username={username}
          plan={plan}
          adherence={adherence}
          trends={trends}
          outcomes={outcomes}
          dayOfPlan={patient?.schedule?.day_of_plan ?? 1}
        />
      )}
    </div>
  );
}
