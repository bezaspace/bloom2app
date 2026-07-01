import {
  ExpoPlayAudioStream,
  EncodingTypes,
  PlaybackModes,
  type Subscription,
} from "@mykin-ai/expo-audio-stream";
import type { AudioEngine } from "./types";

/**
 * Native (iOS/Android) audio engine using @mykin-ai/expo-audio-stream.
 *
 *  - Recording: startMicrophone() with voice processing (echo cancellation,
 *    noise reduction). The library provides a data16kHz field — exactly the
 *    16kHz PCM16 mono Gemini expects as input.
 *  - Playback: playSound() with PCM_S16LE encoding. The library supports
 *    16000/44100/48000 Hz playback, so we upsample Gemini's 24kHz output to
 *    48kHz (trivial 2x — each 16-bit sample is duplicated).
 */

const PLAYBACK_SAMPLE_RATE = 48000;
const PLAYBACK_TURN_ID = "bloom-response";

export class NativeAudioEngine implements AudioEngine {
  private micSubscription: Subscription | null = null;

  async requestPermissions(): Promise<boolean> {
    const result = await ExpoPlayAudioStream.requestPermissionsAsync();
    return result.granted;
  }

  async startRecording(
    onAudioChunk: (base64Pcm16: string) => void
  ): Promise<void> {
    // Configure playback for voice processing (reduces echo/feedback during
    // simultaneous record + playback).
    await ExpoPlayAudioStream.setSoundConfig({
      sampleRate: PLAYBACK_SAMPLE_RATE,
      playbackMode: PlaybackModes.VOICE_PROCESSING,
    });

    const { subscription } = await ExpoPlayAudioStream.startMicrophone({
      sampleRate: 16000,
      channels: 1,
      encoding: "pcm_16bit",
      interval: 100,
      enableProcessing: true,
      onAudioStream: async (event) => {
        // Prefer the library's native 16kHz resampled output; fall back to
        // the raw data if data16kHz isn't provided.
        const base16 = event.data16kHz ?? event.data;
        if (typeof base16 === "string") {
          onAudioChunk(base16);
        }
      },
    });
    this.micSubscription = subscription ?? null;
  }

  async stopRecording(): Promise<void> {
    this.micSubscription?.remove();
    this.micSubscription = null;
    await ExpoPlayAudioStream.stopMicrophone();
  }

  async playResponseChunk(base64Pcm16: string): Promise<void> {
    // Gemini outputs 24kHz; the playback engine supports 48kHz, so upsample 2x.
    const upsampled = upsample24kTo48k(base64Pcm16);
    await ExpoPlayAudioStream.playSound(
      upsampled,
      PLAYBACK_TURN_ID,
      EncodingTypes.PCM_S16LE
    );
  }

  async stopPlayback(): Promise<void> {
    await ExpoPlayAudioStream.interruptSound();
    await ExpoPlayAudioStream.clearSoundQueueByTurnId(PLAYBACK_TURN_ID);
  }

  async destroy(): Promise<void> {
    await this.stopRecording();
    await this.stopPlayback();
  }
}

/**
 * Upsample 24kHz PCM16 to 48kHz PCM16 by duplicating each 16-bit sample.
 * Returns a base64 string.
 */
function upsample24kTo48k(base64: string): string {
  // Gemini/ADK sends base64url-encoded data; convert to standard base64 first.
  const standard = base64.replace(/-/g, "+").replace(/_/g, "/");
  const padded = standard + "=".repeat((4 - (standard.length % 4)) % 4);
  const binary = atob(padded);
  const srcLen = binary.length;
  const out = new Uint8Array(srcLen * 2);
  for (let i = 0; i < srcLen; i += 2) {
    const lo = binary.charCodeAt(i);
    const hi = binary.charCodeAt(i + 1);
    out[i * 2] = lo;
    out[i * 2 + 1] = hi;
    out[i * 2 + 2] = lo;
    out[i * 2 + 3] = hi;
  }
  let result = "";
  const chunk = 0x8000;
  for (let i = 0; i < out.length; i += chunk) {
    result += btoa(
      String.fromCharCode.apply(
        null,
        Array.from(out.subarray(i, i + chunk))
      )
    );
  }
  return result;
}
