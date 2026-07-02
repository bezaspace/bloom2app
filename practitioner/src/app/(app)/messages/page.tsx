import { apiJson } from "@/lib/api";
import type { PractitionerConversation, ConnectedPatient } from "@/lib/types";
import Link from "next/link";
import { MessageSquare } from "lucide-react";

export default async function MessagesPage() {
  let conversations: PractitionerConversation[] = [];
  let patients: ConnectedPatient[] = [];
  let loadError: string | null = null;

  try {
    const [convData, patientsData] = await Promise.all([
      apiJson<{ status: string; conversations: PractitionerConversation[] }>(
        "/practitioner/chat/conversations",
      ),
      apiJson<{ status: string; patients: ConnectedPatient[] }>(
        "/practitioner/patients",
      ),
    ]);
    conversations = convData.conversations;
    patients = patientsData.patients;
  } catch (e) {
    loadError = e instanceof Error ? e.message : String(e);
  }

  if (loadError) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-slate-50">Messages</h1>
        <div className="rounded-lg bg-red-900/40 px-4 py-3 text-sm text-red-200">
          {loadError}
        </div>
      </div>
    );
  }

  // Build a map of patient_username -> conversation for quick lookup.
  const convByPatient = new Map(
    conversations.map((c) => [c.patient_username, c]),
  );

  // Show all connected patients (even those without messages yet) so the
  // practitioner can start a conversation.
  const rows = patients.map((p) => ({
    username: p.username,
    conversation: convByPatient.get(p.username) ?? null,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-slate-50">Messages</h1>

      {rows.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-8 text-center text-slate-500">
          No connected patients yet. Accept an appointment to start messaging.
        </div>
      ) : (
        <div className="space-y-2">
          {rows.map((row) => {
            const conv = row.conversation;
            const last = conv?.last_message;
            const unread = conv?.unread_count ?? 0;
            return (
              <Link
                key={row.username}
                href={`/patients/${encodeURIComponent(row.username)}/messages`}
                className="flex items-center gap-4 rounded-xl border border-slate-800 bg-slate-900 p-4 transition hover:border-slate-700 hover:bg-slate-800/60"
              >
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-base font-bold text-white">
                  {row.username.charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate font-semibold text-slate-100">
                      {row.username}
                    </p>
                    {last && (
                      <span className="shrink-0 text-xs text-slate-500">
                        {formatTime(last.created_at)}
                      </span>
                    )}
                  </div>
                  <p className="truncate text-sm text-slate-400">
                    {last
                      ? `${last.sender === "practitioner" ? "You: " : ""}${last.body}`
                      : "Start a conversation"}
                  </p>
                </div>
                {unread > 0 && (
                  <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-indigo-600 px-2 text-xs font-bold text-white">
                    {unread}
                  </span>
                )}
                {!last && (
                  <MessageSquare className="h-5 w-5 shrink-0 text-slate-600" />
                )}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}
