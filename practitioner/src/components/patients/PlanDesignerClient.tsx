"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Plus, Trash2, Check, Sparkles, FileText } from "lucide-react";
import type {
  TrackingPlan,
  PlanMetric,
  PlanOutcome,
  PlanPhase,
  MetricTemplate,
  DesignAgentResponse,
} from "@/lib/types";

interface PlanDesignerClientProps {
  username: string;
  initialPlan: TrackingPlan | null;
  templates: MetricTemplate[];
  patientProfile: Record<string, unknown> | null;
  patientDocSummary: Record<string, unknown> | null;
}

type Tab = "ai" | "manual";

export function PlanDesignerClient({
  username,
  initialPlan,
  templates,
  patientProfile,
  patientDocSummary,
}: PlanDesignerClientProps) {
  const [tab, setTab] = useState<Tab>("ai");
  const [plan, setPlan] = useState<TrackingPlan | null>(initialPlan);
  const [draftId, setDraftId] = useState<number | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [publishMsg, setPublishMsg] = useState<string | null>(null);

  const handlePublish = async () => {
    if (!plan) return;
    setPublishing(true);
    setPublishMsg(null);
    try {
      const res = await fetch(
        `/api/proxy/practitioner/patients/${encodeURIComponent(username)}/plan/publish`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plan_data: plan, draft_id: draftId }),
        },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Failed to publish plan");
      }
      const data = await res.json();
      setPlan(data.plan);
      setPublishMsg("Plan published successfully! It is now active for this patient.");
    } catch (e) {
      setPublishMsg(`Error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Tab switcher */}
      <div className="flex gap-2">
        <button
          onClick={() => setTab("ai")}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition ${
            tab === "ai"
              ? "bg-indigo-600 text-white"
              : "bg-slate-800 text-slate-400 hover:text-slate-200"
          }`}
        >
          <Sparkles size={16} /> AI Chat
        </button>
        <button
          onClick={() => setTab("manual")}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition ${
            tab === "manual"
              ? "bg-indigo-600 text-white"
              : "bg-slate-800 text-slate-400 hover:text-slate-200"
          }`}
        >
          <FileText size={16} /> Manual Builder
        </button>
      </div>

      {/* Draft preview (shared) */}
      {plan ? (
        <DraftPreview plan={plan} onPublish={handlePublish} publishing={publishing} publishMsg={publishMsg} />
      ) : (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-center text-sm text-slate-500">
          No draft yet. {tab === "ai" ? "Start chatting with the AI to design a plan." : "Add metrics and outcomes below to build a plan."}
        </div>
      )}

      {/* Tab content */}
      {tab === "ai" ? (
        <AIChatTab
          username={username}
          plan={plan}
          draftId={draftId}
          onDraftUpdate={(p, id) => {
            setPlan(p);
            setDraftId(id);
          }}
          patientProfile={patientProfile}
          patientDocSummary={patientDocSummary}
        />
      ) : (
        <ManualBuilderTab
          username={username}
          plan={plan}
          templates={templates}
          onPlanChange={setPlan}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Draft preview
// ---------------------------------------------------------------------------
function DraftPreview({
  plan,
  onPublish,
  publishing,
  publishMsg,
}: {
  plan: TrackingPlan;
  onPublish: () => void;
  publishing: boolean;
  publishMsg: string | null;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-100">Draft Preview</h2>
        <button
          onClick={onPublish}
          disabled={publishing}
          className="flex items-center gap-2 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-500 disabled:opacity-60"
        >
          <Check size={16} /> {publishing ? "Publishing…" : "Publish Plan"}
        </button>
      </div>

      {publishMsg ? (
        <div
          className={`rounded-lg px-3 py-2 text-sm ${
            publishMsg.startsWith("Error")
              ? "bg-red-900/40 text-red-200"
              : "bg-green-900/40 text-green-200"
          }`}
        >
          {publishMsg}
        </div>
      ) : null}

      {plan.title ? (
        <div>
          <h3 className="text-base font-medium text-slate-200">{plan.title}</h3>
          {plan.rationale ? (
            <p className="mt-1 text-sm text-slate-400">{plan.rationale}</p>
          ) : null}
        </div>
      ) : null}

      {/* Metrics */}
      <div>
        <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">
          Metrics ({plan.metrics.length})
        </h4>
        <div className="flex flex-wrap gap-2">
          {plan.metrics.map((m) => (
            <span
              key={m.id || m.template_id}
              className="rounded-md bg-slate-800 px-3 py-1 text-xs text-slate-300"
            >
              {m.label}: {m.target_value ?? "—"} {m.unit} ({m.frequency})
            </span>
          ))}
        </div>
      </div>

      {/* Outcomes */}
      {plan.outcomes.length > 0 ? (
        <div>
          <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">
            Outcome Targets ({plan.outcomes.length})
          </h4>
          <div className="flex flex-wrap gap-2">
            {plan.outcomes.map((o, i) => (
              <span
                key={i}
                className="rounded-md bg-indigo-950/40 px-3 py-1 text-xs text-indigo-300"
              >
                {o.biomarker_name} {o.target_direction} {o.target_value} {o.unit}
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {/* Phases */}
      {plan.phases.length > 0 ? (
        <div>
          <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">
            Phases ({plan.phases.length})
          </h4>
          <div className="space-y-2">
            {plan.phases.map((p) => (
              <div key={p.id || p.phase_number} className="rounded-md bg-slate-800/50 px-3 py-2">
                <div className="text-sm font-medium text-slate-300">
                  {p.name} (Days {p.day_start}–{p.day_end})
                </div>
                {p.focus ? <div className="text-xs text-slate-500">{p.focus}</div> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AI Chat tab
// ---------------------------------------------------------------------------
interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

function AIChatTab({
  username,
  plan,
  draftId,
  onDraftUpdate,
  patientProfile,
  patientDocSummary,
}: {
  username: string;
  plan: TrackingPlan | null;
  draftId: number | null;
  onDraftUpdate: (plan: TrackingPlan, draftId: number | null) => void;
  patientProfile: Record<string, unknown> | null;
  patientDocSummary: Record<string, unknown> | null;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || busy) return;
    const message = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: message }]);
    setBusy(true);
    try {
      const res = await fetch(
        `/api/proxy/practitioner/patients/${encodeURIComponent(username)}/plan/design`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            draft_id: draftId,
            patient_profile: patientProfile,
            doc_summary: patientDocSummary,
          }),
        },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Failed to get response");
      }
      const data: DesignAgentResponse = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", text: data.reply }]);
      if (data.draft) {
        onDraftUpdate(data.draft, data.draft_id);
      }
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `Error: ${e instanceof Error ? e.message : String(e)}` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900" style={{ height: "500px" }}>
      <div className="border-b border-slate-800 px-4 py-2 text-xs text-slate-500">
        Chat with the AI plan design agent. Tell it what you want to track, target
        values, and outcome goals. It will build and refine the draft plan above.
      </div>
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <p className="text-sm text-slate-500">
                Start designing a plan for {username}.
              </p>
              <p className="mt-1 text-xs text-slate-600">
                e.g. &ldquo;Create a plan for metabolic health: track steps (8000/day),
                sleep (7h), meditation (15 min). Outcome: HbA1c below 5.6%.&rdquo;
              </p>
            </div>
          </div>
        ) : null}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-2.5 text-sm ${
                m.role === "user"
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-800 text-slate-200"
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}
        {busy ? (
          <div className="flex justify-start">
            <div className="rounded-lg bg-slate-800 px-4 py-2.5 text-sm text-slate-400">
              Thinking…
            </div>
          </div>
        ) : null}
      </div>
      <div className="flex gap-2 border-t border-slate-800 p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), send())}
          placeholder="Describe what you want to track…"
          className="flex-1 rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-200 placeholder-slate-500 outline-none focus:ring-2 focus:ring-indigo-500"
          disabled={busy}
        />
        <button
          onClick={send}
          disabled={busy || !input.trim()}
          className="rounded-lg bg-indigo-600 p-2.5 text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Manual builder tab
// ---------------------------------------------------------------------------
function ManualBuilderTab({
  username,
  plan,
  templates,
  onPlanChange,
}: {
  username: string;
  plan: TrackingPlan | null;
  templates: MetricTemplate[];
  onPlanChange: (plan: TrackingPlan) => void;
}) {
  // Initialize a blank plan if none exists.
  const ensurePlan = useCallback((): TrackingPlan => {
    if (plan) return plan;
    return {
      id: 0,
      patient_username: username,
      practitioner_id: null,
      version: 1,
      is_active: false,
      title: "",
      rationale: "",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      outcomes: [],
      metrics: [],
      phases: [],
    };
  }, [plan, username]);

  const updatePlan = (updater: (p: TrackingPlan) => TrackingPlan) => {
    onPlanChange(updater(ensurePlan()));
  };

  const addMetricFromTemplate = (tpl: MetricTemplate) => {
    updatePlan((p) => ({
      ...p,
      metrics: [
        ...p.metrics,
        {
          id: Date.now() + Math.random(),
          plan_id: 0,
          template_id: tpl.template_id,
          label: tpl.label,
          unit: tpl.unit,
          frequency: tpl.default_frequency,
          time_of_day: "morning",
          target_type: tpl.default_target_type,
          target_value: tpl.default_target_value,
          target_high: null,
          is_active: true,
          phase: null,
          sort_order: p.metrics.length,
        },
      ],
    }));
  };

  const updateMetric = (index: number, patch: Partial<PlanMetric>) => {
    updatePlan((p) => ({
      ...p,
      metrics: p.metrics.map((m, i) => (i === index ? { ...m, ...patch } : m)),
    }));
  };

  const removeMetric = (index: number) => {
    updatePlan((p) => ({
      ...p,
      metrics: p.metrics.filter((_, i) => i !== index),
    }));
  };

  const addOutcome = () => {
    updatePlan((p) => ({
      ...p,
      outcomes: [
        ...p.outcomes,
        {
          id: Date.now() + Math.random(),
          plan_id: 0,
          biomarker_name: "",
          target_value: 0,
          target_direction: "below",
          target_high: null,
          unit: "",
          target_date: null,
          current_value: null,
          current_as_of: null,
        },
      ],
    }));
  };

  const updateOutcome = (index: number, patch: Partial<PlanOutcome>) => {
    updatePlan((p) => ({
      ...p,
      outcomes: p.outcomes.map((o, i) => (i === index ? { ...o, ...patch } : o)),
    }));
  };

  const removeOutcome = (index: number) => {
    updatePlan((p) => ({
      ...p,
      outcomes: p.outcomes.filter((_, i) => i !== index),
    }));
  };

  const addPhase = () => {
    updatePlan((p) => ({
      ...p,
      phases: [
        ...p.phases,
        {
          id: Date.now() + Math.random(),
          plan_id: 0,
          phase_number: p.phases.length + 1,
          name: `Phase ${p.phases.length + 1}`,
          focus: "",
          actions: [],
          day_start: p.phases.length * 30 + 1,
          day_end: (p.phases.length + 1) * 30,
        },
      ],
    }));
  };

  const updatePhase = (index: number, patch: Partial<PlanPhase>) => {
    updatePlan((p) => ({
      ...p,
      phases: p.phases.map((ph, i) => (i === index ? { ...ph, ...patch } : ph)),
    }));
  };

  const removePhase = (index: number) => {
    updatePlan((p) => ({
      ...p,
      phases: p.phases.filter((_, i) => i !== index),
    }));
  };

  const currentPlan = ensurePlan();

  return (
    <div className="space-y-6">
      {/* Title + rationale */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
        <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">Plan Details</h3>
        <input
          value={currentPlan.title ?? ""}
          onChange={(e) => updatePlan((p) => ({ ...p, title: e.target.value }))}
          placeholder="Plan title (e.g. Metabolic Health & Sleep — 90 Days)"
          className="w-full rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-200 placeholder-slate-500 outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <textarea
          value={currentPlan.rationale ?? ""}
          onChange={(e) => updatePlan((p) => ({ ...p, rationale: e.target.value }))}
          placeholder="Rationale — why this plan, what it targets, clinical reasoning…"
          rows={3}
          className="w-full rounded-lg bg-slate-800 px-4 py-2 text-sm text-slate-200 placeholder-slate-500 outline-none focus:ring-2 focus:ring-indigo-500"
        />
      </div>

      {/* Metrics */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">
            Metrics ({currentPlan.metrics.length})
          </h3>
        </div>
        {/* Template picker */}
        {templates.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {templates.map((tpl) => (
              <button
                key={tpl.template_id}
                onClick={() => addMetricFromTemplate(tpl)}
                className="flex items-center gap-1 rounded-md bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700"
                title={tpl.description}
              >
                <Plus size={12} /> {tpl.label}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-xs text-slate-600">No templates loaded — add custom metrics below.</p>
        )}
        {/* Metric list */}
        <div className="space-y-2">
          {currentPlan.metrics.map((m, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-800/50 p-3">
              <input
                value={m.label}
                onChange={(e) => updateMetric(i, { label: e.target.value })}
                placeholder="Label"
                className="w-32 rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <input
                value={m.unit}
                onChange={(e) => updateMetric(i, { unit: e.target.value })}
                placeholder="Unit"
                className="w-20 rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <select
                value={m.frequency}
                onChange={(e) => updateMetric(i, { frequency: e.target.value })}
                className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none"
              >
                <option value="daily">daily</option>
                <option value="weekly">weekly</option>
                <option value="per_meal">per_meal</option>
                <option value="as_needed">as_needed</option>
              </select>
              <select
                value={m.target_type}
                onChange={(e) => updateMetric(i, { target_type: e.target.value })}
                className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none"
              >
                <option value="minimum">minimum</option>
                <option value="maximum">maximum</option>
                <option value="count">count</option>
                <option value="range">range</option>
                <option value="exact">exact</option>
                <option value="none">none</option>
              </select>
              <input
                type="number"
                value={m.target_value ?? ""}
                onChange={(e) => updateMetric(i, { target_value: e.target.value ? Number(e.target.value) : null })}
                placeholder="Target"
                className="w-20 rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <select
                value={m.time_of_day ?? ""}
                onChange={(e) => updateMetric(i, { time_of_day: e.target.value || null })}
                className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none"
              >
                <option value="">any time</option>
                <option value="morning">morning</option>
                <option value="afternoon">afternoon</option>
                <option value="evening">evening</option>
                <option value="night">night</option>
              </select>
              <button
                onClick={() => removeMetric(i)}
                className="ml-auto rounded p-1 text-red-400 hover:bg-red-900/30"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {currentPlan.metrics.length === 0 ? (
            <p className="text-xs text-slate-600">No metrics yet. Add from templates above.</p>
          ) : null}
        </div>
      </div>

      {/* Outcomes */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">
            Outcome Targets ({currentPlan.outcomes.length})
          </h3>
          <button
            onClick={addOutcome}
            className="flex items-center gap-1 rounded-md bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700"
          >
            <Plus size={12} /> Add outcome
          </button>
        </div>
        <div className="space-y-2">
          {currentPlan.outcomes.map((o, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2 rounded-lg bg-slate-800/50 p-3">
              <input
                value={o.biomarker_name}
                onChange={(e) => updateOutcome(i, { biomarker_name: e.target.value })}
                placeholder="Biomarker (e.g. HbA1c)"
                className="w-32 rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <select
                value={o.target_direction}
                onChange={(e) => updateOutcome(i, { target_direction: e.target.value })}
                className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none"
              >
                <option value="below">below</option>
                <option value="above">above</option>
                <option value="range">in range</option>
              </select>
              <input
                type="number"
                value={o.target_value ?? ""}
                onChange={(e) => updateOutcome(i, { target_value: Number(e.target.value) || 0 })}
                placeholder="Target"
                className="w-20 rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <input
                value={o.unit}
                onChange={(e) => updateOutcome(i, { unit: e.target.value })}
                placeholder="Unit"
                className="w-20 rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <button
                onClick={() => removeOutcome(i)}
                className="ml-auto rounded p-1 text-red-400 hover:bg-red-900/30"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
          {currentPlan.outcomes.length === 0 ? (
            <p className="text-xs text-slate-600">No outcome targets yet.</p>
          ) : null}
        </div>
      </div>

      {/* Phases */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold uppercase tracking-wide text-slate-500">
            Phases ({currentPlan.phases.length})
          </h3>
          <button
            onClick={addPhase}
            className="flex items-center gap-1 rounded-md bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700"
          >
            <Plus size={12} /> Add phase
          </button>
        </div>
        <div className="space-y-2">
          {currentPlan.phases.map((ph, i) => (
            <div key={i} className="space-y-2 rounded-lg bg-slate-800/50 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={ph.name}
                  onChange={(e) => updatePhase(i, { name: e.target.value })}
                  placeholder="Phase name"
                  className="w-40 rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <label className="text-xs text-slate-500">Days</label>
                <input
                  type="number"
                  value={ph.day_start}
                  onChange={(e) => updatePhase(i, { day_start: Number(e.target.value) || 1 })}
                  className="w-16 rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none"
                />
                <span className="text-xs text-slate-500">to</span>
                <input
                  type="number"
                  value={ph.day_end}
                  onChange={(e) => updatePhase(i, { day_end: Number(e.target.value) || 30 })}
                  className="w-16 rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none"
                />
                <button
                  onClick={() => removePhase(i)}
                  className="ml-auto rounded p-1 text-red-400 hover:bg-red-900/30"
                >
                  <Trash2 size={14} />
                </button>
              </div>
              <input
                value={ph.focus ?? ""}
                onChange={(e) => updatePhase(i, { focus: e.target.value })}
                placeholder="Phase focus"
                className="w-full rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
          ))}
          {currentPlan.phases.length === 0 ? (
            <p className="text-xs text-slate-600">No phases yet. Add phases to structure the plan over time.</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
