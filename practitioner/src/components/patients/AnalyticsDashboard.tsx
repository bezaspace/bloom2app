"use client";

import { useMemo } from "react";
import type {
  TrackingPlan,
  AdherenceSummaryResponse,
  TrendsResponse,
  BiomarkerProgressResponse,
  AdherenceSummaryMetric,
  TrendEntry,
  OutcomeProgress,
} from "@/lib/types";

interface AnalyticsDashboardProps {
  username: string;
  plan: TrackingPlan;
  adherence: AdherenceSummaryResponse | null;
  trends: TrendsResponse | null;
  outcomes: BiomarkerProgressResponse | null;
  dayOfPlan: number;
}

export function AnalyticsDashboard({
  username,
  plan,
  adherence,
  trends,
  outcomes,
  dayOfPlan,
}: AnalyticsDashboardProps) {
  const metrics = adherence?.metrics ?? [];
  const trendEntries = trends?.trends ?? [];
  const outcomeProgress = outcomes?.outcomes ?? [];
  const overall = adherence?.overall;

  return (
    <div className="space-y-6">
      {/* Summary header */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">{plan.title}</h2>
            <p className="mt-1 text-sm text-slate-400">
              Day {dayOfPlan} · {plan.metrics.length} metrics · {plan.outcomes.length} outcome targets
            </p>
          </div>
          {overall !== null && overall !== undefined ? (
            <div className="text-right">
              <div className="text-3xl font-bold text-indigo-400">
                {Math.round(overall * 100)}%
              </div>
              <div className="text-xs text-slate-500">30-day adherence</div>
            </div>
          ) : null}
        </div>
      </div>

      {/* Per-metric adherence bars */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
        <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">
          Metric Adherence (30 days)
        </h3>
        {metrics.length === 0 ? (
          <p className="text-sm text-slate-600">No adherence data yet.</p>
        ) : (
          <div className="space-y-3">
            {metrics.map((m) => (
              <MetricAdherenceBar key={m.metric_id} metric={m} />
            ))}
          </div>
        )}
      </div>

      {/* Trends */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
        <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">
          Trends (30 days)
        </h3>
        {trendEntries.length === 0 ? (
          <p className="text-sm text-slate-600">No trend data yet.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {trendEntries.map((t) => (
              <TrendCard key={t.metric_id} trend={t} />
            ))}
          </div>
        )}
      </div>

      {/* Outcome progress */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
        <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">
          Outcome Target Progress
        </h3>
        {outcomeProgress.length === 0 ? (
          <p className="text-sm text-slate-600">No outcome targets in this plan.</p>
        ) : (
          <div className="space-y-3">
            {outcomeProgress.map((o, i) => (
              <OutcomeProgressRow key={i} outcome={o} />
            ))}
          </div>
        )}
      </div>

      {/* Phase progress */}
      {plan.phases.length > 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">
            Plan Phases
          </h3>
          <div className="space-y-2">
            {plan.phases.map((ph) => {
              const isCurrent = ph.day_start <= dayOfPlan && dayOfPlan <= ph.day_end;
              const isPast = dayOfPlan > ph.day_end;
              return (
                <div
                  key={ph.id || ph.phase_number}
                  className={`rounded-lg p-3 ${
                    isCurrent
                      ? "border border-indigo-500/40 bg-indigo-950/20"
                      : "bg-slate-800/50"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-slate-200">{ph.name}</span>
                    <span
                      className={`text-xs ${
                        isCurrent
                          ? "text-indigo-400"
                          : isPast
                          ? "text-slate-600"
                          : "text-slate-500"
                      }`}
                    >
                      Days {ph.day_start}–{ph.day_end}
                      {isCurrent ? " (current)" : isPast ? " (complete)" : ""}
                    </span>
                  </div>
                  {ph.focus ? (
                    <p className="mt-1 text-xs text-slate-500">{ph.focus}</p>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function MetricAdherenceBar({ metric }: { metric: AdherenceSummaryMetric }) {
  const pct = metric.adherence_avg !== null && metric.adherence_avg !== undefined
    ? Math.round(metric.adherence_avg * 100)
    : null;
  const color =
    pct === null ? "#64748b" : pct >= 80 ? "#22c55e" : pct >= 50 ? "#f97316" : "#ef4444";

  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-300">{metric.label}</span>
        <span className="text-slate-500">
          {pct !== null ? `${pct}%` : "—"} · {metric.days_with_data}d data
        </span>
      </div>
      <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-slate-800">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${pct ?? 0}%`,
            backgroundColor: color,
          }}
        />
      </div>
    </div>
  );
}

function TrendCard({ trend }: { trend: TrendEntry }) {
  const arrow =
    trend.direction === "up" ? "↑" : trend.direction === "down" ? "↓" : trend.direction === "steady" ? "→" : "?";
  const color =
    trend.direction === "up" ? "text-green-400"
    : trend.direction === "down" ? "text-blue-400"
    : trend.direction === "steady" ? "text-slate-400"
    : "text-slate-600";

  return (
    <div className="rounded-lg bg-slate-800/50 p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-200">{trend.label}</span>
        <span className={`text-lg font-bold ${color}`}>{arrow}</span>
      </div>
      <div className="mt-1 text-xs text-slate-500">
        Recent avg: {trend.recent_avg !== null ? formatVal(trend.recent_avg) : "—"} {trend.unit}
        {trend.prior_avg !== null ? ` vs ${formatVal(trend.prior_avg)}` : ""}
      </div>
      {trend.magnitude !== null ? (
        <div className="text-xs text-slate-600">
          Change: {trend.magnitude > 0 ? "+" : ""}{formatVal(trend.magnitude)} {trend.unit}
        </div>
      ) : null}
    </div>
  );
}

function OutcomeProgressRow({ outcome }: { outcome: OutcomeProgress }) {
  const onTrack = outcome.on_track;
  const current = outcome.current_value;
  const delta = outcome.delta;
  const target = outcome.target_value;
  const direction = outcome.target_direction;

  // Progress: how close to target (0..1).
  let progress = 0;
  if (current !== null && current !== undefined) {
    if (direction === "below") {
      progress = current <= target ? 1 : Math.max(0, target / current);
    } else if (direction === "above") {
      progress = current >= target ? 1 : Math.max(0, current / target);
    } else if (direction === "range" && outcome.target_high !== null) {
      const low = target;
      const high = outcome.target_high;
      progress = current >= low && current <= high ? 1 : 0.5;
    }
  }

  return (
    <div className="rounded-lg bg-slate-800/50 p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-200">{outcome.biomarker_name}</span>
        <span
          className={`rounded px-2 py-0.5 text-xs font-bold ${
            onTrack === true
              ? "bg-green-900/40 text-green-400"
              : onTrack === false
              ? "bg-orange-900/40 text-orange-400"
              : "bg-slate-700 text-slate-400"
          }`}
        >
          {onTrack === true ? "On track" : onTrack === false ? "Working on it" : "No data"}
        </span>
      </div>
      <div className="mt-2 flex items-center gap-4 text-xs text-slate-500">
        <span>
          Target: {direction} {target} {outcome.unit}
        </span>
        <span>
          Current: {current !== null && current !== undefined ? `${formatVal(current)} ${outcome.unit}` : "—"}
        </span>
        {delta !== null && delta !== undefined ? (
          <span className={delta > 0 ? "text-orange-400" : delta < 0 ? "text-green-400" : "text-slate-400"}>
            Δ: {delta > 0 ? "+" : ""}{formatVal(delta)}
          </span>
        ) : null}
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-700">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${Math.round(progress * 100)}%`,
            backgroundColor: onTrack === true ? "#22c55e" : onTrack === false ? "#f97316" : "#64748b",
          }}
        />
      </div>
    </div>
  );
}

function formatVal(v: number): string {
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(2).replace(/\.?0+$/, "");
}
