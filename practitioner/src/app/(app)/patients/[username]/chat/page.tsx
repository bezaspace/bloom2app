import Link from "next/link";
import { ChatClient } from "@/components/patients/ChatClient";

export default async function ChatPage({
  params,
}: {
  params: Promise<{ username: string }>;
}) {
  const { username } = await params;
  return (
    <div className="mx-auto flex h-[calc(100vh-8rem)] max-w-3xl flex-col space-y-4">
      <div>
        <Link
          href={`/patients/${encodeURIComponent(username)}`}
          className="text-sm text-indigo-400 hover:text-indigo-300"
        >
          &larr; Back to {username}
        </Link>
      </div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-slate-50">AI Chat — {username}</h1>
      </div>
      <div className="rounded-lg border border-amber-500/30 bg-amber-950/20 px-4 py-2 text-xs text-amber-300">
        Answers are AI-generated from {username}&apos;s current data. Not a medical diagnosis.
      </div>
      <ChatClient username={username} />
    </div>
  );
}
