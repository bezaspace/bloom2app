/**
 * Platform-agnostic audio interface for the voice assistant.
 *
 * Two implementations exist:
 *  - `webAudioEngine.ts`   — uses the browser Web Audio API (for Expo Web dev)
 *  - `nativeAudioEngine.ts` — uses @mykin-ai/expo-audio-stream (for native iOS/Android)
 *
 * The hook picks the right one at runtime via `createAudioEngine()` in
 * `audioEngine.ts`. Both implementations produce/consume the same formats:
 *  - Input:  base64-encoded PCM 16-bit, 16kHz, mono  (sent to backend → Gemini)
 *  - Output: base64-encoded PCM 16-bit, 24kHz, mono  (received from Gemini)
 */

export interface AudioEngine {
  /** Request microphone permission from the user. */
  requestPermissions(): Promise<boolean>;

  /**
   * Start capturing microphone audio. Calls `onAudioChunk` with base64-encoded
   * 16kHz PCM16 mono chunks as they arrive.
   */
  startRecording(onAudioChunk: (base64Pcm16: string) => void): Promise<void>;

  /** Stop capturing microphone audio. */
  stopRecording(): Promise<void>;

  /**
   * Play a chunk of model audio (base64 PCM16 24kHz mono). Multiple calls
   * queue seamlessly for streaming playback.
   */
  playResponseChunk(base64Pcm16: string): Promise<void>;

  /** Stop playback immediately and clear any queued audio (e.g. on interrupt). */
  stopPlayback(): Promise<void>;

  /** Clean up all resources (called on unmount / disconnect). */
  destroy(): Promise<void>;
}
