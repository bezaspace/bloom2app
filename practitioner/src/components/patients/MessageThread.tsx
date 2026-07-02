"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { io, Socket } from "socket.io-client";
import { Send, ArrowLeft } from "lucide-react";
import { PUBLIC_BACKEND_URL } from "@/lib/env";
import type { ChatMessage } from "@/lib/types";

interface MessageThreadProps {
  username: string;
  practitionerId: number;
  onBack?: () => void;
}

type ConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

export function MessageThread({
  username,
  practitionerId,
  onBack,
}: MessageThreadProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connStatus, setConnStatus] = useState<ConnectionStatus>("connecting");
  const [otherTyping, setOtherTyping] = useState(false);
  const [optimisticMsgs, setOptimisticMsgs] = useState<ChatMessage[]>([]);

  const socketRef = useRef<Socket | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isTypingRef = useRef(false);

  const conversationId = `${practitionerId}:${username}`;

  // --- Load history via REST (through the BFF proxy) ---
  const loadHistory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/proxy/practitioner/chat/conversations/${encodeURIComponent(username)}/messages?limit=50`,
      );
      if (!res.ok) throw new Error("Failed to load messages");
      const data = await res.json();
      setMessages(data.messages);
      setHasMore(data.has_more);
      // Mark as read on open.
      await fetch(
        `/api/proxy/practitioner/chat/conversations/${encodeURIComponent(username)}/read`,
        { method: "POST" },
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [username]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  // --- Socket.io connection ---
  useEffect(() => {
    let cancelled = false;
    let sock: Socket | null = null;

    (async () => {
      // Mint a short-lived WS token via the BFF.
      let wsToken: string;
      try {
        const res = await fetch("/api/auth/ws-token", { method: "POST" });
        if (!res.ok) throw new Error("Failed to get WS token");
        const data = await res.json();
        wsToken = data.token;
      } catch (e) {
        if (!cancelled) setConnStatus("error");
        return;
      }
      if (cancelled) return;

      sock = io(PUBLIC_BACKEND_URL, {
        path: "/chat-ws/socket.io",
        auth: { token: wsToken },
        transports: ["websocket", "polling"],
        reconnection: true,
        reconnectionAttempts: 5,
        reconnectionDelay: 1000,
      });
      socketRef.current = sock;

      sock.on("connect", () => !cancelled && setConnStatus("connected"));
      sock.on("disconnect", () => !cancelled && setConnStatus("disconnected"));
      sock.on("connect_error", () => !cancelled && setConnStatus("error"));
    })();

    return () => {
      cancelled = true;
      if (sock) {
        sock.removeAllListeners();
        sock.disconnect();
      }
      socketRef.current = null;
    };
  }, []);

  // --- Incoming message handler ---
  useEffect(() => {
    const sock = socketRef.current;
    if (!sock) return;

    const onMessage = (msg: ChatMessage) => {
      if (msg.conversation_id !== conversationId) return;
      // Clear optimistic placeholder.
      setOptimisticMsgs((prev) =>
        prev.filter((m) => !(m.body === msg.body && m.sender === msg.sender)),
      );
      setMessages((prev) => {
        if (prev.some((m) => m.id === msg.id)) return prev;
        return [...prev, msg];
      });
      // If from patient, mark read.
      if (msg.sender === "patient") {
        void fetch(
          `/api/proxy/practitioner/chat/conversations/${encodeURIComponent(username)}/read`,
          { method: "POST" },
        );
        sock.emit("message_read", {
          practitioner_id: practitionerId,
          patient_username: username,
        });
      }
    };

    const onTyping = (data: {
      conversation_id: string;
      sender: string;
      is_typing: boolean;
    }) => {
      if (data.conversation_id !== conversationId) return;
      if (data.sender === "patient") setOtherTyping(data.is_typing);
    };

    const onRead = (data: { conversation_id: string; reader: string }) => {
      if (data.conversation_id !== conversationId) return;
      if (data.reader === "patient") {
        setMessages((prev) =>
          prev.map((m) =>
            m.sender === "practitioner" && m.read_at === null
              ? { ...m, read_at: new Date().toISOString() }
              : m,
          ),
        );
      }
    };

    sock.on("message", onMessage);
    sock.on("typing", onTyping);
    sock.on("read", onRead);
    return () => {
      sock.off("message", onMessage);
      sock.off("typing", onTyping);
      sock.off("read", onRead);
    };
  }, [conversationId, practitionerId, username]);

  // Auto-scroll to bottom on new messages.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, optimisticMsgs, otherTyping]);

  // Clear typing after timeout.
  useEffect(() => {
    if (!otherTyping) return;
    const t = setTimeout(() => setOtherTyping(false), 4000);
    return () => clearTimeout(t);
  }, [otherTyping]);

  // --- Load older messages ---
  const handleLoadMore = useCallback(async () => {
    if (loadingMore || !hasMore || messages.length === 0) return;
    setLoadingMore(true);
    try {
      const oldestId = messages[0].id;
      const res = await fetch(
        `/api/proxy/practitioner/chat/conversations/${encodeURIComponent(username)}/messages?before=${oldestId}&limit=50`,
      );
      if (!res.ok) throw new Error("Failed to load older messages");
      const data = await res.json();
      setMessages((prev) => [...data.messages, ...prev]);
      setHasMore(data.has_more);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, hasMore, messages, username]);

  // --- Send message ---
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);

    // Stop typing indicator.
    if (isTypingRef.current) {
      socketRef.current?.emit("typing", {
        practitioner_id: practitionerId,
        patient_username: username,
        is_typing: false,
      });
      isTypingRef.current = false;
    }

    // Optimistic echo.
    const tempId = -Date.now();
    const optimistic: ChatMessage = {
      id: tempId,
      conversation_id: conversationId,
      practitioner_id: practitionerId,
      patient_username: username,
      sender: "practitioner",
      body: text,
      created_at: new Date().toISOString(),
      read_at: null,
    };
    setOptimisticMsgs((prev) => [...prev, optimistic]);

    try {
      // Send via socket (primary).
      socketRef.current?.emit("message", {
        practitioner_id: practitionerId,
        patient_username: username,
        body: text,
      });
      // REST fallback to ensure persistence + get the real id.
      const res = await fetch(
        `/api/proxy/practitioner/chat/conversations/${encodeURIComponent(username)}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ body: text }),
        },
      );
      if (!res.ok) throw new Error("Failed to send");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setOptimisticMsgs((prev) => prev.filter((m) => m.id !== tempId));
      setInput(text);
    } finally {
      setSending(false);
    }
  }, [input, sending, practitionerId, username, conversationId]);

  const handleInputChange = useCallback(
    (text: string) => {
      setInput(text);
      if (!isTypingRef.current && text.length > 0) {
        isTypingRef.current = true;
        socketRef.current?.emit("typing", {
          practitioner_id: practitionerId,
          patient_username: username,
          is_typing: true,
        });
      }
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = setTimeout(() => {
        if (isTypingRef.current) {
          socketRef.current?.emit("typing", {
            practitioner_id: practitionerId,
            patient_username: username,
            is_typing: false,
          });
          isTypingRef.current = false;
        }
      }, 2000);
    },
    [practitionerId, username],
  );

  useEffect(() => {
    return () => {
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    };
  }, []);

  const allMessages = [...messages, ...optimisticMsgs];

  return (
    <div className="flex flex-1 flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
      {/* Thread header */}
      <div className="flex items-center gap-3 border-b border-slate-800 px-4 py-3">
        {onBack && (
          <button
            onClick={onBack}
            className="text-slate-400 hover:text-slate-200"
            aria-label="Back"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
        )}
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-600 text-sm font-bold text-white">
          {username.charAt(0).toUpperCase()}
        </div>
        <div className="flex-1">
          <p className="font-semibold text-slate-100">{username}</p>
          <p className="text-xs text-slate-500">
            {otherTyping
              ? "typing..."
              : connStatus === "connected"
                ? "online"
                : connStatus === "connecting"
                  ? "connecting..."
                  : connStatus}
          </p>
        </div>
      </div>

      {error && (
        <p className="px-4 py-2 text-sm text-red-400">{error}</p>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
        {loading ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            Loading messages...
          </div>
        ) : (
          <>
            {hasMore && (
              <div className="py-2 text-center">
                <button
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  className="text-xs font-medium text-indigo-400 hover:text-indigo-300 disabled:opacity-60"
                >
                  {loadingMore ? "Loading..." : "Load older messages"}
                </button>
              </div>
            )}
            {allMessages.length === 0 && !loading && (
              <div className="flex h-full items-center justify-center text-center">
                <p className="text-sm text-slate-500">
                  No messages yet. Start the conversation!
                </p>
              </div>
            )}
            {allMessages.map((m) => {
              const isMe = m.sender === "practitioner";
              const isOptimistic = m.id < 0;
              return (
                <div
                  key={m.id}
                  className={`flex ${isMe ? "justify-end" : "justify-start"}`}
                >
                  <div className="max-w-[75%]">
                    <div
                      className={`rounded-lg px-4 py-2.5 text-sm ${
                        isMe
                          ? "bg-indigo-600 text-white"
                          : "bg-slate-800 text-slate-200"
                      }`}
                    >
                      {m.body}
                    </div>
                    <div
                      className={`mt-1 flex items-center gap-1.5 text-xs text-slate-500 ${
                        isMe ? "justify-end" : "justify-start"
                      }`}
                    >
                      <span>{formatTime(m.created_at)}</span>
                      {isMe && !isOptimistic && (
                        <span className="text-indigo-400">
                          {m.read_at ? "✓✓" : "✓"}
                        </span>
                      )}
                      {isMe && isOptimistic && (
                        <span className="text-slate-600">...</span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            {otherTyping && (
              <div className="flex justify-start">
                <div className="rounded-lg bg-slate-800 px-4 py-2.5 text-sm text-slate-400">
                  ...
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Input */}
      <div className="flex gap-2 border-t border-slate-800 p-3">
        <input
          type="text"
          value={input}
          onChange={(e) => handleInputChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder="Type a message..."
          className="flex-1 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
          disabled={sending}
        />
        <button
          onClick={handleSend}
          disabled={sending || !input.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2.5 text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          {sending ? (
            <span className="text-xs">...</span>
          ) : (
            <Send className="h-4 w-4" />
          )}
        </button>
      </div>
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
