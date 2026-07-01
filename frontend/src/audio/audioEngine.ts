import { Platform } from "react-native";
import type { AudioEngine } from "./types";

/**
 * Create the platform-appropriate audio engine.
 *
 *  - Web (Expo Web / browser): WebAudioEngine — uses the Web Audio API
 *  - Native (iOS / Android):   NativeAudioEngine — uses @mykin-ai/expo-audio-stream
 *
 * The imports are done lazily inside the function so that the native-only
 * module is never loaded in a browser environment (and vice-versa for the
 * Web Audio API types on native).
 */
export async function createAudioEngine(): Promise<AudioEngine> {
  if (Platform.OS === "web") {
    const { WebAudioEngine } = await import("./WebAudioEngine");
    return new WebAudioEngine();
  }
  const { NativeAudioEngine } = await import("./NativeAudioEngine");
  return new NativeAudioEngine();
}
