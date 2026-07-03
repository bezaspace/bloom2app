"use client";

import { useState, useCallback } from "react";
import { Sparkles, Check, X, RefreshCw, Plus } from "lucide-react";
import type { PlanSuggestion } from "@/lib/types";
import { withBasePath } from "@/lib/basePath";

interface PlanSuggestionsPanelProps {
  username: string;
  initialSuggestions: PlanSuggestion[];
}

export function PlanSuggestionsPanel({
  username,
  initialSuggestions,
}: PlanSuggestionsPanelProps) {
  const [suggestions, setSuggestions] = useState<PlanSuggestion[]>(initialSuggestions);
  const [generating, setGenerating] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(
        withBasePath(`/api/proxy/practitioner/patients/${encodeURIComponent(username)}/plan/suggestions`),
      );
      if (!res.ok) throw new Error("Failed to fetch suggestions");
      const data = await res.json();
      setSuggestions(data.suggestions ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [username]);

  const generate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const res = await fetch(
        withBasePath(`/api/proxy/practitioner/patients/${encodeURIComponent(username)}/plan/suggestions/generate`),
        { method: "POST" },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Failed to generate suggestions");
      }
      const data = await res.json();
      // Refresh the list to include the new suggestion.
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setGenerating(false);
    }
  };

  const decide = async (id: number, decision: "approve" | "dismiss") => {
    setBusy(id);
    setError(null);
    try {
      const res = await fetch(
        withBasePath(`/api/proxy/practitioner/patients/${encodeURIComponent(username)}/plan/suggestions/${id}/decide`),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision }),
        },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Failed to decide");
      }
      // Update local state.
      setSuggestions((prev) =>
        prev.map((s) =>
          s.id === id
            ? { ...s, status: decision === "approve" ? "approved" : "dismissed", decided_at: new Date().toISOString() }
            : s,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const pending = suggestions.filter((s) => s.status === "pending");
  const decided = suggestions.filter((s) => s.status !== "pending");

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wide text-slate-500">
          <Sparkles size={16} /> AI Plan Suggestions
        </h3>
        <button
          onClick={generate}
          disabled={generating}
          className="flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {generating ? (
            <RefreshCw size={12} className="animate-spin" />
          ) : (
            <Plus size={12} />
          )}
          {generating ? "Generating…" : "Generate suggestion"}
        </button>
      </div>

      {error ? (
        <div className="rounded-lg bg-red-900/40 px-3 py-2 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      {/* Pending suggestions */}
      {pending.length === 0 && decided.length === 0 ? (
        <p className="text-sm text-slate-600">
          No suggestions yet. Click &ldquo;Generate suggestion&rdquo; to ask the AI
          for plan adjustments based on {username}&apos;s recent data.
        </p>
      ) : null}

      <div className="space-y-3">
        {pending.map((s) => (
          <SuggestionCard
            key={s.id}
            suggestion={s}
            onDecide={(d) => decide(s.id, d as "approve" | "dismiss")}
            busy={busy === s.id}
          />
        ))}
      </div>

      {/* Decided suggestions (collapsed) */}
      {decided.length > 0 ? (
        <details className="text-sm">
          <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-400">
            {decided.length} decided suggestion{decided.length !== 1 ? "s" : ""}
          </summary>
          <div className="mt-2 space-y-2">
            {decided.map((s) => (
              <div
                key={s.id}
                className="rounded-lg bg-slate-800/30 p-3 text-xs text-slate-500"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-400">
                    {s.suggestion.title ?? s.suggestion.type ?? "Suggestion"}
                  </span>
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-bold ${
                      s.status === "approved"
                        ? "bg-green-900/40 text-green-400"
                        : "bg-red-900/40 text-red-400"
                    }`}
                  >
                    {s.status}
                  </span>
                </div>
                {s.suggestion.description ? (
                  <p className="mt-1">{s.suggestion.description}</p>
                ) : null}
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
}

function SuggestionCard({
  suggestion,
  onDecide,
  busy,
}: {
  suggestion: PlanSuggestion;
  onDecide: (decision: "approve" | "dismiss") => void;
  busy: boolean;
}) {
  const s = suggestion.suggestion;
  return (
    <div className="rounded-lg border border-indigo-500/20 bg-indigo-950/10 p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="text-sm font-medium text-slate-200">
            {s.title ?? s.type ?? "Suggestion"}
          </div>
          {s.rationale ? (
            <p className="mt-1 text-xs text-slate-400">{s.rationale}</p>
          ) : null}
          {s.description ? (
            <p className="mt-1 text-xs text-slate-500">{s.description}</p>
          ) : null}
          {/* Show metric details if present */}
          {s.metric ? (
            <div className="mt-2 rounded bg-slate-800/50 px-2 py-1.5 text-xs text-slate-400">
              Metric: {s.metric.label ?? "—"} · target: {s.metric.target_value ?? "—"} {s.metric.unit ?? ""}
            </div>
          ) : null}
          {/* Show outcome details if present */}
          {s.outcome ? (
            <div className="mt-2 rounded bg-slate-800/50 px-2 py-1.5 text-xs text-slate-400">
              Outcome: {s.outcome.biomarker_name ?? "—"} {s.outcome.target_direction ?? ""} {s.outcome.target_value ?? "—"} {s.outcome.unit ?? ""}
            </div>
          ) : null}
        </div>
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => onDecide("approve")}
          disabled={busy}
          className="flex items-center gap-1 rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-500 disabled:opacity-60"
        >
          <Check size={12} /> Approve & Apply
        </button>
        <button
          onClick={() => onDecide("dismiss")}
          disabled={busy}
          className="flex items-center gap-1 rounded-md bg-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-600 disabled:opacity-60"
        >
          <X size={12} /> Dismiss
        </button>
      </div>
      <div className="text-xs text-slate-600">
        Source: {suggestion.source} · {new Date(suggestion.created_at).toLocaleDateString()}
      </div>
    </div>
  );
}
