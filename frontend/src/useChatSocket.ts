import { useEffect, useRef, useState, useCallback } from "react";
import { io, Socket } from "socket.io-client";
import { getToken } from "./auth";
import { BACKEND_ORIGIN } from "./config";
import type { ChatMessage } from "./chat";

/**
 * Connection status of the chat socket.
 */
export type ChatConnectionStatus =
  | "connecting"
  | "connected"
  | "disconnected"
  | "error";

/**
 * React hook that manages a single Socket.io connection to the backend for
 * real-time chat. The socket authenticates with the patient's bearer token.
 *
 * Returns the connection status plus helpers to send messages, emit typing
 * indicators, mark conversations read, and register callbacks for incoming
 * messages / typing / read events.
 *
 * The socket is shared across all conversations (one connection per patient).
 * Use `conversationId` to filter events in your callbacks.
 */
export function useChatSocket() {
  const socketRef = useRef<Socket | null>(null);
  const [status, setStatus] = useState<ChatConnectionStatus>("connecting");

  useEffect(() => {
    let cancelled = false;
    let sock: Socket | null = null;

    (async () => {
      const token = await getToken();
      if (!token || cancelled) {
        setStatus("disconnected");
        return;
      }

      // Connect to the Socket.io server. The path matches the backend mount.
      // Use the proxy/backend ORIGIN (not HTTP_BASE, which may carry an /api
      // prefix in the Dockerized web build) — Socket.io connects to
      // /chat-ws/socket.io directly, not under /api.
      const origin = BACKEND_ORIGIN;
      sock = io(origin, {
        path: "/chat-ws/socket.io",
        auth: { token },
        transports: ["websocket", "polling"],
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
      });
      socketRef.current = sock;

      sock.on("connect", () => !cancelled && setStatus("connected"));
      sock.on("disconnect", () => !cancelled && setStatus("disconnected"));
      sock.on("connect_error", () => !cancelled && setStatus("error"));
      sock.io.on("reconnect_attempt", () => !cancelled && setStatus("connecting"));
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

  /** Emit a chat message. The server persists + broadcasts to the room. */
  const sendMessage = useCallback(
    (
      practitionerId: number,
      patientUsername: string,
      body: string,
    ) => {
      socketRef.current?.emit("message", {
        practitioner_id: practitionerId,
        patient_username: patientUsername,
        body,
      });
    },
    [],
  );

  /** Emit a typing indicator. */
  const sendTyping = useCallback(
    (
      practitionerId: number,
      patientUsername: string,
      isTyping: boolean,
    ) => {
      socketRef.current?.emit("typing", {
        practitioner_id: practitionerId,
        patient_username: patientUsername,
        is_typing: isTyping,
      });
    },
    [],
  );

  /** Mark a conversation as read (server emits a `read` event to the room). */
  const markRead = useCallback(
    (practitionerId: number, patientUsername: string) => {
      socketRef.current?.emit("message_read", {
        practitioner_id: practitionerId,
        patient_username: patientUsername,
      });
    },
    [],
  );

  /** Register a callback for incoming messages. Returns an unsubscribe fn. */
  const onMessage = useCallback((cb: (msg: ChatMessage) => void) => {
    const sock = socketRef.current;
    if (!sock) return () => {};
    sock.on("message", cb);
    return () => sock.off("message", cb);
  }, []);

  /** Register a callback for typing indicators. */
  const onTyping = useCallback(
    (
      cb: (data: {
        conversation_id: string;
        sender: string;
        is_typing: boolean;
      }) => void,
    ) => {
      const sock = socketRef.current;
      if (!sock) return () => {};
      sock.on("typing", cb);
      return () => sock.off("typing", cb);
    },
    [],
  );

  /** Register a callback for read receipts. */
  const onRead = useCallback(
    (
      cb: (data: { conversation_id: string; reader: string }) => void,
    ) => {
      const sock = socketRef.current;
      if (!sock) return () => {};
      sock.on("read", cb);
      return () => sock.off("read", cb);
    },
    [],
  );

  return {
    status,
    sendMessage,
    sendTyping,
    markRead,
    onMessage,
    onTyping,
    onRead,
  };
}
