# Bloom2 — AI Voice Assistant

A simple, natural, back-and-forth voice conversation app powered by the
**Gemini Live API**, orchestrated with **Google ADK** (Agent Development Kit),
served by a **FastAPI** backend, with a **React Native (Expo)** frontend.

Talk to Bloom like a friend — it listens, speaks, and can be interrupted
mid-sentence, just like a real conversation.

## Architecture

```
┌───────────────────────┐   WebSocket (16kHz PCM ↑ / JSON events ↓)   ┌──────────────────────┐
│  React Native (Expo)  │ <------------------------------------------> │  FastAPI + ADK        │
│  Web Audio API (web)  │                                              │  Runner.run_live()    │
│  expo-audio-stream    │                                              │  LiveRequestQueue     │
│  (native Android/iOS) │                                              │  Gemini Live API      │
└───────────────────────┘                                              └──────────────────────┘
```

- **Frontend** (`frontend/`) — Expo SDK 57 / React Native. Captures microphone
  audio as 16kHz PCM chunks, streams them over a WebSocket, and plays back the
  24kHz PCM audio chunks returned by the model. Shows live transcripts of both
  sides of the conversation. Uses a platform-aware audio layer: the **Web Audio
  API** when running in a browser (Expo Web), and `@mykin-ai/expo-audio-stream`
  on native Android/iOS.
- **Backend** (`backend/`) — FastAPI server using ADK's `Runner.run_live()` to
  bridge the WebSocket to the Gemini Live API. The agent ("Bloom") is defined
  with ADK's `Agent` class and uses the `gemini-3.1-flash-live-preview`
  native-audio live model for low-latency spoken responses.

## Prerequisites

- **Node.js** 22+ and npm
- **uv** (Python package manager) — install from https://docs.astral.sh/uv/
- **A Gemini API key** — get one at https://aistudio.google.com/apikey

## Setup

### 1. Backend

```bash
cd backend
uv sync                       # install Python dependencies
```

Add your Gemini API key to `backend/.env` (a template is already there):

```
GOOGLE_API_KEY=your_key_here
```

### 2. Frontend

```bash
cd frontend
npm install                   # install JS dependencies
```

## Running

You need both the backend and the frontend running simultaneously — in two
separate terminals.

### Quick start with launcher scripts

From the project root:

```bash
./sb          # starts the backend  (terminal 1)
./sf          # starts the frontend  (terminal 2, web mode — opens browser)
```

`./sf` defaults to **web mode** for development. You can also pass a platform:

```bash
./sf web       # Expo Web — opens in your browser (default)
./sf android   # Expo Android — opens Android emulator
./sf ios       # Expo iOS — opens iOS simulator (macOS only)
```

`./sb` accepts an optional port argument:

```bash
./sb           # port 8000 (default)
./sb 9000      # custom port
```

### What the scripts do

- **`./sb`** — runs `uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
  in the `backend/` directory. Warns if the API key is still the placeholder.
- **`./sf`** — runs `npx expo start --web` (or `--android` / `--ios`) in the
  `frontend/` directory.

### Manual start (without scripts)

```bash
# Terminal 1 — backend
cd backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — frontend (web)
cd frontend
npx expo start --web
```

Verify the backend is up: `curl http://localhost:8000/health` → `{"status":"ok",...}`

### Web development workflow

During development, run `./sf` (web mode). Expo serves the app in your browser
at `http://localhost:8081`. The browser's Web Audio API handles microphone
capture and audio playback — no native build required. This lets you iterate
fast on the UI, transcript, WebSocket flow, and agent behavior without a phone
or emulator.

> **Browser mic permission**: When you tap the mic button, the browser will
> prompt for microphone access. Use headphones to avoid echo feedback during
> testing.

> **Physical device later?** When you're ready to test on a phone, run
> `./sf android` (or `./sf ios`). Edit `frontend/src/config.ts` and set
> `BACKEND_HOST` to your computer's LAN IP (e.g. `192.168.1.50`). Both devices
> must be on the same network.

## How to use

1. Open the app (browser or device) and tap **Connect**.
2. Tap the **mic button** and start talking — Bloom listens and responds by
   voice. Tap again to stop sending audio.
3. You can interrupt Bloom while it's speaking by tapping the mic and talking.
4. You can also type a message using the text input at the bottom.

## Project structure

```
bloom2app/
├── sb                          ← start backend script
├── sf                          ← start frontend script (web/android/ios)
├── backend/
│   ├── .env                    ← put your Gemini API key here
│   ├── .env.example
│   ├── pyproject.toml
│   └── app/
│       ├── main.py             ← FastAPI + WebSocket + ADK run_live()
│       └── voice_agent/
│           └── agent.py        ← ADK Agent definition (Bloom)
└── frontend/
    ├── App.tsx                 ← Voice assistant UI
    ├── app.json                ← Expo config (mic permission)
    └── src/
        ├── config.ts           ← backend host/port
        ├── types.ts            ← ADK event types
        ├── useVoiceAssistant.ts    ← WebSocket + audio orchestration hook
        └── audio/
            ├── types.ts        ← AudioEngine interface (shared)
            ├── audioEngine.ts  ← platform-aware factory
            ├── WebAudioEngine.ts    ← browser impl (Web Audio API)
            └── NativeAudioEngine.ts ← native impl (expo-audio-stream)
```

## Platform notes

- **Web (browser)**: Used for development via Expo Web. The `WebAudioEngine`
  uses the browser's Web Audio API (`getUserMedia` + `ScriptProcessorNode` for
  capture, `AudioBufferSourceNode` for streaming playback). Works in Chrome,
  Edge, and Firefox. Use headphones to avoid echo.
- **Android**: Fully supported (primary native target). `NativeAudioEngine`
  uses `@mykin-ai/expo-audio-stream` (Android `AudioTrack`/`AudioRecord`) with
  voice processing (echo cancellation, noise reduction).
- **iOS**: Also supported by the same native library (uses `AVFoundation`).
  The `NSMicrophoneUsageDescription` permission is set in `app.json`.

## Tech stack

| Layer      | Technology                                              |
|------------|---------------------------------------------------------|
| Frontend   | React Native 0.86, Expo SDK 57, TypeScript              |
| Audio (web)  | Web Audio API (getUserMedia, AudioBufferSourceNode)   |
| Audio (native) | @mykin-ai/expo-audio-stream (AudioTrack/AudioRecord) |
| Backend    | FastAPI, Uvicorn, uv                                    |
| Agent      | Google ADK (Agent Development Kit) Python               |
| Model      | Gemini Live API — `gemini-3.1-flash-live-preview`       |
| Transport  | WebSocket (bidirectional, binary audio + JSON events)   |
