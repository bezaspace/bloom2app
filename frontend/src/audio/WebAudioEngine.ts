import type { AudioEngine } from "./types";

/**
 * Web (browser) audio engine using the Web Audio API.
 *
 *  - Recording: getUserMedia → AudioWorklet captures 16kHz PCM16 mono chunks,
 *    base64-encodes them, and hands them to the callback.
 *  - Playback:  base64 PCM16 24kHz chunks are decoded into Float32Array
 *    samples and scheduled on an AudioBufferSourceNode at 24kHz for gap-free
 *    streaming playback.
 *
 * This runs only in a browser (Expo Web). On native, the native engine is used
 * instead. The Platform.OS check in audioEngine.ts guarantees this is never
 * instantiated outside a browser.
 */

const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;

// ScriptProcessor is deprecated but has the widest browser support and is
// adequate for development. A worklet would be ideal but adds a separate
// file/asset-pipeline complication that isn't worth it for an MVP.
const SCRIPT_BUFFER_SIZE = 4096;

export class WebAudioEngine implements AudioEngine {
  private audioContext: AudioContext | null = null;
  private mediaStream: MediaStream | null = null;
  private mediaStreamSource: MediaStreamAudioSourceNode | null = null;
  private scriptProcessor: ScriptProcessorNode | null = null;
  private isRecording = false;

  // Playback state
  private playbackContext: AudioContext | null = null;
  private nextPlaybackTime = 0;
  private readonly playbackQueue: Array<{
    samples: Float32Array;
    startTime: number;
  }> = [];

  async requestPermissions(): Promise<boolean> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: INPUT_SAMPLE_RATE,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      // Release immediately — we'll re-acquire in startRecording.
      stream.getTracks().forEach((t) => t.stop());
      return true;
    } catch {
      return false;
    }
  }

  async startRecording(
    onAudioChunk: (base64Pcm16: string) => void
  ): Promise<void> {
    if (this.isRecording) return;

    this.audioContext = new AudioContext({ sampleRate: INPUT_SAMPLE_RATE });
    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: INPUT_SAMPLE_RATE,
        echoCancellation: true,
        noiseSuppression: true,
      },
    });
    this.mediaStreamSource = this.audioContext.createMediaStreamSource(
      this.mediaStream
    );

    // ScriptProcessor gives us raw Float32 samples at the context rate.
    this.scriptProcessor = this.audioContext.createScriptProcessor(
      SCRIPT_BUFFER_SIZE,
      1,
      1
    );

    this.scriptProcessor.onaudioprocess = (e) => {
      if (!this.isRecording) return;
      const input = e.inputBuffer.getChannelData(0);
      // Convert Float32 [-1,1] → 16-bit PCM, then base64-encode.
      const pcm16 = float32ToInt16(input);
      const base64 = arrayBufferToBase64(pcm16.buffer as ArrayBuffer);
      onAudioChunk(base64);
    };

    this.mediaStreamSource.connect(this.scriptProcessor);
    // ScriptProcessor requires a destination connection to fire onaudioprocess.
    this.scriptProcessor.connect(this.audioContext.destination);
    this.isRecording = true;
  }

  async stopRecording(): Promise<void> {
    this.isRecording = false;
    this.scriptProcessor?.disconnect();
    this.mediaStreamSource?.disconnect();
    this.mediaStream?.getTracks().forEach((t) => t.stop());
    await this.audioContext?.close();
    this.audioContext = null;
    this.mediaStream = null;
    this.mediaStreamSource = null;
    this.scriptProcessor = null;
  }

  async playResponseChunk(base64Pcm16: string): Promise<void> {
    if (!this.playbackContext) {
      this.playbackContext = new AudioContext({
        sampleRate: OUTPUT_SAMPLE_RATE,
      });
      this.nextPlaybackTime = this.playbackContext.currentTime;
    }

    const ctx = this.playbackContext;
    const pcm16 = base64ToArrayBuffer(base64Pcm16);
    const float32 = int16ToFloat32(new Int16Array(pcm16));

    const buffer = ctx.createBuffer(1, float32.length, OUTPUT_SAMPLE_RATE);
    buffer.copyToChannel(float32 as Float32Array<ArrayBuffer>, 0);

    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);

    // Schedule seamlessly after any previously queued audio.
    const startAt = Math.max(ctx.currentTime, this.nextPlaybackTime);
    source.start(startAt);
    this.nextPlaybackTime = startAt + buffer.duration;
  }

  async stopPlayback(): Promise<void> {
    // The simplest reliable way to stop queued audio is to close the context.
    // The next playResponseChunk call will create a fresh one.
    if (this.playbackContext) {
      await this.playbackContext.close();
      this.playbackContext = null;
      this.nextPlaybackTime = 0;
    }
  }

  async destroy(): Promise<void> {
    await this.stopRecording();
    await this.stopPlayback();
  }
}

// ---- encoding helpers ----------------------------------------------------

function float32ToInt16(float32: Float32Array): Int16Array {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const clamped = Math.max(-1, Math.min(1, float32[i]));
    out[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return out;
}

function int16ToFloat32(int16: Int16Array): Float32Array {
  const out = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    out[i] = int16[i] / 0x8000;
  }
  return out;
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(
      null,
      Array.from(bytes.subarray(i, i + chunk))
    );
  }
  return btoa(binary);
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  // Gemini/ADK sends base64url-encoded data (uses - and _ instead of + and /,
  // and omits padding). The browser's atob() requires standard base64, so
  // convert first.
  const standard = base64.replace(/-/g, "+").replace(/_/g, "/");
  const padded = standard + "=".repeat((4 - (standard.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}
