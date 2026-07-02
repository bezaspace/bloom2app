import { apiJson } from "@/lib/api";
import type { Practitioner } from "@/lib/types";
import { MessageThread } from "@/components/patients/MessageThread";
import Link from "next/link";

export default async function PatientMessagesPage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = await params;

  // Fetch the practitioner's own profile to get their id (needed for the
  // socket conversation_id).
  let practitioner: Practitioner | null = null;
  let loadError: string | null = null;
  try {
    const data = await apiJson<{ status: string; practitioner: Practitioner }>(
      "/practitioner/me",
    );
    practitioner = data.practitioner;
  } catch (e) {
    loadError = e instanceof Error ? e.message : String(e);
  }

  if (loadError || !practitioner) {
    return (
      <div className="space-y-4">
        <Link
          href="/messages"
          className="text-sm text-indigo-400 hover:text-indigo-300"
        >
          &larr; Back to messages
        </Link>
        <div className="rounded-lg bg-red-900/40 px-4 py-3 text-sm text-red-200">
          {loadError ?? "Could not load practitioner profile."}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col space-y-4">
      <div>
        <Link
          href="/messages"
          className="text-sm text-indigo-400 hover:text-indigo-300"
        >
          &larr; Back to messages
        </Link>
      </div>
      <MessageThread
        username={username}
        practitionerId={practitioner.id}
      />
    </div>
  );
}
