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
│  (patient mobile app) │                                              │  Runner.run_live()    │
│  Dashboard | Talk |   │   REST (bearer token)                        │  LiveRequestQueue     │
│  Practitioners |      │ <------------------------------------------> │  Gemini Live API      │
│  Messages             │   Socket.io (bearer token auth)              │  + practitioner API   │
└───────────────────────┘ <------------------------------------------> │  + appointment API    │
                                                                       │  + practitioner AI    │
┌───────────────────────┐   REST (httpOnly cookie → BFF → bearer)      │  + chat (Socket.io)   │
│  Next.js 16 (web)     │ <------------------------------------------> │                       │
│  (practitioner app)   │   Socket.io (short-lived WS token via BFF)   └──────────────────────┘
│  Dashboard | Appts |  │ <------------------------------------------> 
│  Patients | Messages  │
│  Settings             │
└───────────────────────┘
```

- **Frontend** (`frontend/`) — Expo SDK 57 / React Native. The patient-facing
  mobile app. Captures microphone audio as 16kHz PCM chunks, streams them over
  a WebSocket, and plays back the 24kHz PCM audio chunks returned by the model.
  Shows live transcripts of both sides of the conversation. Three tabs:
  **Dashboard** (wellness progress), **Talk** (voice assistant), and
  **Practitioners** (browse/book appointments). Uses a platform-aware audio
  layer: the **Web Audio API** when running in a browser (Expo Web), and
  `@mykin-ai/expo-audio-stream` on native Android/iOS.
- **Backend** (`backend/`) — FastAPI server. Serves the patient voice
  assistant via ADK's `Runner.run_live()` bridging the WebSocket to the Gemini
  Live API (agent "Bloom" uses `gemini-3.1-flash-live-preview`). Also serves
  the patient dashboard REST API, the practitioner directory + appointment
  booking API, the practitioner-facing patient-data API (with connection-based
  authorization), and the practitioner AI features (Gemini Flash-Lite patient
  summaries + per-patient chat).
- **Practitioner** (`practitioner/`) — Next.js 16 (App Router) web app for
  practitioners. Self-registration + login, appointment management (accept/
  decline/complete), connected-patient tracking (schedule, logs, biomarkers,
  notes), AI patient summaries, and per-patient AI chat. Uses a **BFF** auth
  pattern: httpOnly cookie on the Next.js origin, bearer token forwarded
  server-side to FastAPI — the browser never talks to FastAPI directly.

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

### 3. Practitioner web app

```bash
cd practitioner
npm install                   # install JS dependencies
```

The practitioner app reads `PRACTITIONER_BACKEND_URL` from `practitioner/.env.local`
(defaults to `http://localhost:8000`). No changes needed for local development.

## Running

You need the backend running, plus whichever frontend(s) you want to use.
The patient mobile app and the practitioner web app can run simultaneously
against the same backend.

### Quick start with launcher scripts

From the project root:

```bash
./sb          # starts the backend  (terminal 1)
./sf          # starts the frontend  (terminal 2, web mode — opens browser)
```

To start the practitioner web app (terminal 3):

```bash
cd practitioner
npm run dev   # http://localhost:3000
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

## Demo data (seed)

The backend auto-seeds demo data on first startup (when the database is
empty), so you can immediately test all features without manual onboarding.

**Demo patient** — has an onboarded profile, a 90-day plan (day 14), today's
schedule, 7 days of logs (with streaks), and biomarker trends.

- **Demo patient login**: `demo` / `demodemo`

**Demo practitioners** — 3 practitioner accounts for testing the practitioner
web app, plus one pending appointment from the demo patient to Dr. Anya Sharma.

- **Demo practitioner login**: `dranya` / `demodemo` (also `drchen`, `marcop`)

To control seeding manually:

```bash
cd backend
uv run python -m app.seed              # seed if not already seeded
uv run python -m app.seed --force      # wipe demo data and re-seed
uv run python -m app.seed --check      # print seed status without modifying
```

Auto-seeding on startup is controlled by the `SEED_ON_STARTUP` env var
(default `true`). Set `SEED_ON_STARTUP=false` in `backend/.env` to disable it.

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
│       ├── auth.py             ← patient auth routes & dependency (SQLite)
│       ├── database.py         ← SQLite patient store (users/tokens/logs/biomarkers)
│       ├── seed.py             ← demo data seeder (patient + practitioners)
│       ├── document_processor.py ← Gemini Flash-Lite doc summary extraction
│       ├── practitioner_db.py  ← SQLite practitioner/appointment/connection store
│       ├── practitioner_auth.py ← practitioner auth routes & dependency
│       ├── practitioner_routes.py ← practitioner API (appts, patients, AI, notes)
│       ├── patient_practitioner_routes.py ← patient API (browse/book appts)
│       ├── practitioner_ai.py  ← Gemini Flash-Lite patient summaries + chat
│       ├── chat_db.py          ← SQLite chat message + WS token store
│       ├── chat_socket.py      ← Socket.io server (real-time chat)
│       ├── chat_routes.py      ← chat REST endpoints (history, send, read)
│       ├── dashboard/          ← AI schedule generator + biomarker extraction
│       └── voice_agent/
│           ├── agent.py        ← ADK Agent definition (Bloom)
│           └── tools.py        ← 8 tools: onboarding + progress reads + voice logs
├── frontend/
│   ├── App.tsx                 ← Root navigator
│   ├── app.json                ← Expo config (mic permission)
│   └── src/
│       ├── auth.ts             ← login/register API + token storage
│       ├── config.ts           ← backend host/port
│       ├── types.ts            ← ADK event types
│       ├── dashboard.ts        ← dashboard API client
│       ├── practitioners.ts    ← practitioner/appointment API client
│       ├── chat.ts             ← chat API client (conversations, messages)
│       ├── useVoiceAssistant.ts ← WebSocket + audio orchestration hook
│       ├── useChatSocket.ts    ← Socket.io hook for real-time chat
│       ├── navigation/         ← RootNavigator + MainTabs (4 tabs)
│       ├── screens/            ← Auth, Dashboard, VoiceAssistant, Practitioners, Chat
│       └── audio/              ← platform-aware audio engine
└── practitioner/               ← Next.js 16 practitioner web app
    ├── AGENTS.md               ← architecture & conventions
    ├── .env.local              ← PRACTITIONER_BACKEND_URL
    ├── src/
    │   ├── proxy.ts            ← auth gate (redirects unauthed to /login)
    │   ├── lib/                ← env, session (cookie), api (BFF fetch), types
    │   ├── app/
    │   │   ├── (auth)/         ← login + register pages
    │   │   ├── (app)/          ← auth-gated: dashboard, appointments, patients, messages, settings
    │   │   └── api/            ← BFF route handlers (auth + ws-token + catch-all proxy)
    │   └── components/         ← layout (sidebar/topbar), appointments, patients (incl. MessageThread)
    └── package.json
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

| Layer         | Technology                                              |
|---------------|---------------------------------------------------------|
| Patient app   | React Native 0.86, Expo SDK 57, TypeScript              |
| Audio (web)   | Web Audio API (getUserMedia, AudioBufferSourceNode)     |
| Audio (native)| @mykin-ai/expo-audio-stream (AudioTrack/AudioRecord)    |
| Practitioner  | Next.js 16 (App Router), React 19, TypeScript, Tailwind v4 |
| Backend       | FastAPI, Uvicorn, uv                                    |
| Agent         | Google ADK (Agent Development Kit) Python               |
| Voice model   | Gemini Live API — `gemini-3.1-flash-live-preview`       |
| AI (docs/prac)| Gemini `gemini-3.1-flash-lite` (structured output)      |
| Transport     | WebSocket (voice) + REST (dashboard/practitioner) + Socket.io (chat) |
| Real-time chat| python-socketio (server) + socket.io-client (both apps) |
| Auth          | Bearer tokens (patient) + BFF httpOnly cookie (practitioner) |
