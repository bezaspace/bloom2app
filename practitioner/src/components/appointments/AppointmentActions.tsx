"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Appointment } from "@/lib/types";

export function AppointmentActions({ appointment }: { appointment: Appointment }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const act = async (action: "accept" | "decline" | "complete") => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/proxy/practitioner/appointments/${appointment.id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `Failed to ${action}`);
      }
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (appointment.status === "pending") {
    return (
      <div className="flex justify-end gap-2">
        {error && <span className="self-center text-xs text-red-400">{error}</span>}
        <button
          onClick={() => act("accept")}
          disabled={busy}
          className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
        >
          Accept
        </button>
        <button
          onClick={() => act("decline")}
          disabled={busy}
          className="rounded-md border border-red-500/50 px-3 py-1.5 text-xs font-medium text-red-400 hover:border-red-500 disabled:opacity-60"
        >
          Decline
        </button>
      </div>
    );
  }

  if (appointment.status === "accepted") {
    return (
      <div className="flex justify-end gap-2">
        {error && <span className="self-center text-xs text-red-400">{error}</span>}
        <button
          onClick={() => act("complete")}
          disabled={busy}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          Mark Complete
        </button>
      </div>
    );
  }

  return <span className="text-xs text-slate-600">—</span>;
}
