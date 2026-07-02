# Progress

High-level feature map of what's been built in Bloom2 so far.

## 1. Auth
- Username/password login + register (SQLite, PBKDF2)
- Bearer-token sessions; token stored client-side in AsyncStorage

## 2. Voice Assistant (Talk tab)
- Bidirectional WebSocket streaming 16kHz PCM ↔ Gemini Live API (`gemini-3.1-flash-live-preview`)
- ADK `Runner.run_live()` orchestration on the backend
- Platform-aware audio: Web Audio API (web) + `expo-audio-stream` (native)
- Live transcript, mic toggle, text input, interruption support

## 3. Onboarding
- Conversational onboarding via the voice agent (≤5 questions)
- Optional health-document upload (PDF/PNG/JPEG/WEBP)
- Document processing: Gemini Flash-Lite extracts a structured clinical summary (`DocumentSummary`)
- `finalize_onboarding` persists profile + 90-day wellness plan
- Plan viewable in-app (phases, focus, actions, weekly rhythm)

## 4. Dashboard (Dashboard tab)
- Bottom-tab navigation: Dashboard | Talk
- **Plan summary** — current phase, day-of-plan, focus
- **AI daily schedule** — generated on-demand per day via Flash-Lite, cached, regeneratable; timed items with tap-to-check-off
- **Wellness domain cards** — workouts, diet, meditation, medication: progress ring, quick-log, 7-day bar chart (planned vs actual)
- **Mental health** — 1-5 mood check-in + 7-day trend line
- **Biomarkers** — structured numeric extraction from uploaded lab docs; overview grid with status pills + sparklines; detail modal with reference-range dashed lines, latest/prior/delta stats, history table
- Not-onboarded CTA; empty states throughout
