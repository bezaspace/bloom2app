"use client";

import { useState, useRef, useEffect } from "react";
import { Send } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  text: string;
}

export function ChatClient({ username }: { username: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || busy) return;
    const question = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setBusy(true);
    try {
      const res = await fetch(
        `/api/proxy/practitioner/patients/${encodeURIComponent(username)}/ai-chat`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question }),
        },
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Failed to get answer");
      }
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", text: data.answer }]);
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
    <div className="flex flex-1 flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-center">
            <div>
              <p className="text-sm text-slate-500">Ask a question about {username}&apos;s progress.</p>
              <p className="mt-1 text-xs text-slate-600">
                e.g. &ldquo;How is their HbA1c trending?&rdquo; or &ldquo;Have they been meditating consistently?&rdquo;
              </p>
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] rounded-lg px-4 py-2.5 text-sm ${
                m.role === "user"
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-800 text-slate-200"
              }`}
            >
              {m.text}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex justify-start">
            <div className="rounded-lg bg-slate-800 px-4 py-2.5 text-sm text-slate-400">
              Thinking...
            </div>
          </div>
        )}
      </div>
      <div className="flex gap-2 border-t border-slate-800 p-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about this patient..."
          className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
          disabled={busy}
        />
        <button
          onClick={send}
          disabled={busy || !input.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2.5 text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          <Send className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
