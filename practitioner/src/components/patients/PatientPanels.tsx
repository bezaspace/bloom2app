"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Sparkles, MessageSquare, Plus, ClipboardList, BarChart3 } from "lucide-react";
import type { AISummary, PractitionerNote } from "@/lib/types";

// ---------------------------------------------------------------------------
// AI Summary card
// ---------------------------------------------------------------------------
export function AISummaryCard({ username }: { username: string }) {
  const router = useRouter();
  const [summary, setSummary] = useState<AISummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/proxy/practitioner/patients/${encodeURIComponent(username)}/ai-summary`,
        { method: "POST" },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Failed to generate summary");
      }
      const data = await res.json();
      setSummary(data.summary);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-semibold text-slate-200">
          <Sparkles className="h-4 w-4 text-indigo-400" />
          AI Patient Summary
        </h2>
        <button
          onClick={generate}
          disabled={loading}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {loading ? "Generating..." : summary ? "Regenerate" : "Generate"}
        </button>
      </div>
      {error && <p className="mb-2 text-sm text-red-400">{error}</p>}
      {summary ? (
        <div className="space-y-3">
          <p className="text-sm text-slate-300">{summary.summary}</p>
          {summary.notable_items.length > 0 && (
            <ul className="space-y-1">
              {summary.notable_items.map((item, i) => (
                <li key={i} className="flex gap-2 text-sm text-slate-400">
                  <span className="text-indigo-400">•</span>
                  {item}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p className="text-sm text-slate-500">
          Click &ldquo;Generate&rdquo; to create an AI summary of this patient&apos;s progress, trends, and notable biomarker changes.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Notes panel
// ---------------------------------------------------------------------------
export function NotesPanel({
  username,
  notes: initialNotes,
}: {
  username: string;
  notes: PractitionerNote[];
}) {
  const [notes, setNotes] = useState(initialNotes);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const addNote = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/proxy/practitioner/patients/${encodeURIComponent(username)}/notes`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note_text: text }),
        },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Failed to add note");
      }
      const data = await res.json();
      setNotes((prev) => [data.note, ...prev]);
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h2 className="mb-4 font-semibold text-slate-200">My Notes</h2>
      <div className="mb-4 flex gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="Add a note about this patient..."
          className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 outline-none focus:border-indigo-500"
        />
        <button
          onClick={addNote}
          disabled={busy || !text.trim()}
          className="self-start rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
      {error && <p className="mb-2 text-sm text-red-400">{error}</p>}
      {notes.length === 0 ? (
        <p className="text-sm text-slate-500">No notes yet.</p>
      ) : (
        <ul className="space-y-3">
          {notes.map((n) => (
            <li key={n.id} className="rounded-lg bg-slate-800/40 p-3">
              <p className="text-sm text-slate-300">{n.note_text}</p>
              <p className="mt-1 text-xs text-slate-500">
                {new Date(n.created_at).toLocaleString()}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Chat link
// ---------------------------------------------------------------------------
export function ChatLink({ username }: { username: string }) {
  return (
    <Link
      href={`/patients/${encodeURIComponent(username)}/chat`}
      className="flex items-center justify-center gap-2 rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-4 text-sm font-medium text-indigo-300 transition hover:bg-indigo-950/40"
    >
      <MessageSquare className="h-4 w-4" />
      Ask AI about this patient
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Plan Designer link
// ---------------------------------------------------------------------------
export function PlanDesignerLink({ username }: { username: string }) {
  return (
    <Link
      href={`/patients/${encodeURIComponent(username)}/plan`}
      className="flex items-center justify-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4 text-sm font-medium text-emerald-300 transition hover:bg-emerald-950/40"
    >
      <ClipboardList className="h-4 w-4" />
      Design Tracking Plan
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Analytics link
// ---------------------------------------------------------------------------
export function AnalyticsLink({ username }: { username: string }) {
  return (
    <Link
      href={`/patients/${encodeURIComponent(username)}/analytics`}
      className="flex items-center justify-center gap-2 rounded-xl border border-sky-500/30 bg-sky-950/20 p-4 text-sm font-medium text-sky-300 transition hover:bg-sky-950/40"
    >
      <BarChart3 className="h-4 w-4" />
      View Analytics
    </Link>
  );
}
