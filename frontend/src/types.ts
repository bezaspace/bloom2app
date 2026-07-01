/**
 * Types for ADK streaming Events sent from the backend over the WebSocket.
 *
 * The backend serializes events with `model_dump_json(by_alias=True)`, so field
 * names arrive in camelCase. A single event can carry audio chunks, transcripts,
 * interruption signals, or turn-completion signals. See the ADK Gemini Live API
 * Toolkit docs for the full event shape.
 */

export interface InlineData {
  mimeType: string;
  /** Base64-encoded audio (PCM 16-bit little-endian, 24kHz for model output). */
  data: string;
}

export interface EventPart {
  text?: string;
  inlineData?: InlineData;
}

export interface EventContent {
  parts?: EventPart[];
}

export interface Transcription {
  text: string;
  finished?: boolean;
}

export interface UsageMetadata {
  promptTokenCount?: number;
  candidatesTokenCount?: number;
  totalTokenCount?: number;
}

export interface AdkEvent {
  /** Who produced the event — usually "bloom2_voice_assistant" or "user". */
  author?: string;
  /** Model turn content (audio chunks + any text parts). */
  content?: EventContent;
  /** Transcript of what the user said (input audio transcription). */
  inputTranscription?: Transcription;
  /** Transcript of what the model said (output audio transcription). */
  outputTranscription?: Transcription;
  /** True when the user interrupted the model mid-speech. */
  interrupted?: boolean;
  /** True when the model finished its turn. */
  turnComplete?: boolean;
  usageMetadata?: UsageMetadata;
}

/** JSON message the client sends upstream as a text frame. */
export interface ClientTextMessage {
  type: "text";
  text: string;
}
