import { useCallback, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import { WS_BASE, HTTP_BASE } from "./config";
import type { AdkEvent, ClientTextMessage } from "./types";
import { createAudioEngine } from "./audio/audioEngine";
import type { AudioEngine } from "./audio/types";
import { getToken } from "./auth";

export type ConnectionStatus = "disconnected" | "connecting" | "connected";

export interface TranscriptEntry {
  id: string;
  role: "user" | "assistant";
  text: string;
  /** Still being streamed in. */
  partial: boolean;
}

interface UseVoiceAssistantResult {
  status: ConnectionStatus;
  isSpeaking: boolean;
  isListening: boolean;
  transcript: TranscriptEntry[];
  error: string | null;
  connect: () => Promise<void>;
  disconnect: () => void;
  startTalking: () => Promise<void>;
  stopTalking: () => Promise<void>;
  sendText: (text: string) => void;
}

let idCounter = 0;
const nextId = () => `id-${++idCounter}`;

export function useVoiceAssistant(): UseVoiceAssistantResult {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const audioEngineRef = useRef<AudioEngine | null>(null);
  const playbackStartedRef = useRef(false);

  // Refs for the current partial transcript bubbles so we can append to them.
  const currentUserBubbleId = useRef<string | null>(null);
  const currentAssistantBubbleId = useRef<string | null>(null);

  /** Lazily create the platform-appropriate audio engine. */
  const getAudioEngine = useCallback(async (): Promise<AudioEngine> => {
    if (!audioEngineRef.current) {
      audioEngineRef.current = await createAudioEngine();
    }
    return audioEngineRef.current;
  }, []);

  // ---- transcript helpers -------------------------------------------------
  const resetBubbles = useCallback(() => {
    currentUserBubbleId.current = null;
    currentAssistantBubbleId.current = null;
  }, []);

  const appendUserText = useCallback((text: string, partial: boolean) => {
    setTranscript((prev) => {
      const id = currentUserBubbleId.current;
      const existing = id ? prev.find((t) => t.id === id) : null;
      if (existing) {
        return prev.map((t) =>
          t.id === id ? { ...t, text: existing.text + text, partial } : t,
        );
      }
      const newId = nextId();
      currentUserBubbleId.current = newId;
      return [...prev, { id: newId, role: "user", text, partial }];
    });
  }, []);

  const appendAssistantText = useCallback((text: string, partial: boolean) => {
    setTranscript((prev) => {
      const id = currentAssistantBubbleId.current;
      const existing = id ? prev.find((t) => t.id === id) : null;
      if (existing) {
        return prev.map((t) =>
          t.id === id ? { ...t, text: existing.text + text, partial } : t,
        );
      }
      const newId = nextId();
      currentAssistantBubbleId.current = newId;
      return [...prev, { id: newId, role: "assistant", text, partial }];
    });
  }, []);

  const finalizeBubbles = useCallback(() => {
    setTranscript((prev) => prev.map((t) => ({ ...t, partial: false })));
    resetBubbles();
  }, [resetBubbles]);

  // ---- WebSocket message handling ----------------------------------------
  const handleEvent = useCallback(
    async (event: AdkEvent) => {
      const engine = audioEngineRef.current;

      // Interruption: the user spoke over the model. Stop playback + mark the
      // partial assistant bubble as interrupted so the new turn starts fresh.
      if (event.interrupted) {
        await engine?.stopPlayback();
        playbackStartedRef.current = false;
        setIsSpeaking(false);
        if (currentAssistantBubbleId.current) {
          setTranscript((prev) =>
            prev.map((t) =>
              t.id === currentAssistantBubbleId.current
                ? { ...t, text: t.text + " …(interrupted)", partial: false }
                : t,
            ),
          );
        }
        resetBubbles();
        return;
      }

      // Input transcription (what the user said).
      if (event.inputTranscription?.text) {
        appendUserText(
          event.inputTranscription.text,
          !event.inputTranscription.finished,
        );
      }

      // Output transcription (what the model said).
      if (event.outputTranscription?.text) {
        appendAssistantText(
          event.outputTranscription.text,
          !event.outputTranscription.finished,
        );
      }

      // Audio chunks from the model turn.
      if (event.content?.parts) {
        for (const part of event.content.parts) {
          if (
            part.inlineData?.data &&
            part.inlineData.mimeType?.startsWith("audio/pcm")
          ) {
            if (!playbackStartedRef.current) {
              setIsSpeaking(true);
              playbackStartedRef.current = true;
            }
            await engine?.playResponseChunk(part.inlineData.data);
          }
        }
      }

      // Turn complete: stop playback and reset bubble tracking.
      if (event.turnComplete) {
        setIsSpeaking(false);
        playbackStartedRef.current = false;
        finalizeBubbles();
      }
    },
    [appendAssistantText, appendUserText, finalizeBubbles, resetBubbles],
  );

  // ---- connection --------------------------------------------------------
  const connect = useCallback(async () => {
    if (wsRef.current) return;
    setStatus("connecting");
    setError(null);

    try {
      // Eagerly create the audio engine so it's ready when the user taps talk.
      await getAudioEngine();

      // Ask the backend for a fresh user/session id pair.
      const token = await getToken();
      if (!token) throw new Error("Not authenticated");

      const res = await fetch(`${HTTP_BASE}/new-session`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok)
        throw new Error(`backend /new-session failed: ${res.status}`);
      const { user_id, session_id } = await res.json();

      const ws = new WebSocket(
        `${WS_BASE}/ws/${user_id}/${session_id}?token=${encodeURIComponent(token)}`,
      );
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
        setError(null);
      };

      ws.onmessage = (ev) => {
        try {
          const event = JSON.parse(ev.data) as AdkEvent;
          void handleEvent(event);
        } catch (e) {
          console.warn("Failed to parse event:", e);
        }
      };

      ws.onerror = (e) => {
        console.error("WebSocket error:", e);
        setError("WebSocket connection error");
      };

      ws.onclose = () => {
        setStatus("disconnected");
        wsRef.current = null;
        setIsSpeaking(false);
        setIsListening(false);
      };
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("disconnected");
    }
  }, [getAudioEngine, handleEvent]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("disconnected");
    void audioEngineRef.current?.stopPlayback();
  }, []);

  // ---- talking (mic streaming) ------------------------------------------
  const startTalking = useCallback(async () => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      setError("Not connected to the server");
      return;
    }

    const engine = await getAudioEngine();
    const granted = await engine.requestPermissions();
    if (!granted) {
      setError("Microphone permission denied");
      return;
    }

    setError(null);
    setIsListening(true);

    await engine.startRecording((base64Pcm16) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      // Send as a binary frame: decode base64 → raw 16kHz PCM16 bytes.
      const raw = base64ToArrayBuffer(base64Pcm16);
      ws.send(raw);
    });
  }, [getAudioEngine]);

  const stopTalking = useCallback(async () => {
    await audioEngineRef.current?.stopRecording();
    setIsListening(false);
  }, []);

  // ---- text input --------------------------------------------------------
  const sendText = useCallback(
    (text: string) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      const message: ClientTextMessage = { type: "text", text };
      ws.send(JSON.stringify(message));
      // Show the user's text immediately in the transcript.
      appendUserText(text, false);
    },
    [appendUserText],
  );

  // ---- cleanup on unmount ------------------------------------------------
  useEffect(() => {
    return () => {
      wsRef.current?.close();
      void audioEngineRef.current?.destroy();
    };
  }, []);

  return {
    status,
    isSpeaking,
    isListening,
    transcript,
    error,
    connect,
    disconnect,
    startTalking,
    stopTalking,
    sendText,
  };
}

/** Decode a base64 string into an ArrayBuffer (raw PCM bytes). */
function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}
