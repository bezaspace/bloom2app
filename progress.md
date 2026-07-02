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
- **Wellness domain cards** — workouts, diet, meditation, medication: progress ring, quick-log, 7-day bar chart (planned vs actual); "via voice" badge when an entry was logged through the Talk tab
- **Mental health** — 1-5 mood check-in + 7-day trend line
- **Biomarkers** — structured numeric extraction from uploaded lab docs; overview grid with status pills + sparklines; detail modal with reference-range dashed lines, latest/prior/delta stats, history table
- Not-onboarded CTA; empty states throughout
- Dashboard refetches silently whenever the tab gains focus (so voice-logged entries appear without a manual pull-to-refresh)

## 5. Voice + Dashboard integration (Talk tab)
- The voice agent (Bloom) now has tools that bridge it to the dashboard data:
  - **Read tools** — `get_today_progress` (today's schedule + check-offs + per-domain actuals vs targets + mood), `get_streaks` (consecutive-day completion streaks per domain), `get_biomarker_trends` (latest vs prior reading + delta per marker). Bloom greets returning users with real progress instead of generic text.
  - **Write tools** — `log_wellness_entry` (append a voice-logged activity to `daily_logs`) and `log_mood` (record a 1-5 mood). Both read-modify-write the full entry list so they never wipe existing quick-logs/check-offs; entries are tagged `note: "via voice"`.
  - **Confirm-then-log** — Bloom repeats back what it heard and confirms before writing, so misheard speech doesn't create junk entries.
  - Domain mapping is in the agent instruction (workout/diet/meditation/medication/other + mood).
- No DB migrations needed; reuses the existing `daily_logs` and `biomarkers` tables.

## 6. Demo data seeder
- `backend/app/seed.py` creates a demo user (`demo` / `demodemo`) with a full set of test data so every dashboard + voice feature can be exercised without manual onboarding:
  - Onboarded profile + 90-day plan (day 14) + simulated lab doc summary
  - Today's AI schedule (8 timed items across all domains, partially checked off)
  - 7 days of daily logs with realistic streaks (meditation 4-day, medication 7-day, workout 2-day, mental_health 2-day)
  - 4 biomarkers with 2-3 readings each over time (HbA1c, LDL, Vitamin D, TSH) for trend deltas
- **Auto-seeds on first startup** when the DB has no onboarded demo user, gated by `SEED_ON_STARTUP` env var (default `true`); set to `false` to opt out.
- **Idempotent**: skips if the demo user is already onboarded. `--force` wipes the demo user's data across all tables (via `delete_user_cascade`) and re-seeds.
- CLI: `uv run python -m app.seed` (seed if empty), `--force` (wipe + re-seed), `--check` (status only).
- `database.py` gained a `delete_user_cascade` helper that removes a user and all associated rows from `biomarkers`, `daily_logs`, `daily_schedules`, `user_docs`, `user_profiles`, `tokens`, and `users`.

## 7. Practitioner web app + appointment booking
- **New `practitioner/` folder** — Next.js 16 (App Router) web app for practitioners to manage appointments and track connected patients' progress. Uses a BFF (Backend-for-Frontend) auth pattern: httpOnly cookie on the Next.js origin, bearer token forwarded server-side to FastAPI. The browser never talks to FastAPI directly.
  - **Auth** — self-registration + login (`/login`, `/register`); `proxy.ts` gates all `/(app)/*` routes.
  - **Dashboard** — pending appointment count, connected patients count, upcoming appointments, recent activity.
  - **Appointments** — table with filter tabs (pending/accepted/completed/declined/all); accept (auto-creates connection), decline, complete actions.
  - **Patients list** — connected patients with day-of-plan, phase, biomarker count, AI-summary badge.
  - **Patient detail** — full view: profile, plan summary, today's schedule (with check-offs), wellness domain log counts, biomarker groups with latest/prior/delta + status, health document summary, practitioner notes (add/list), AI summary card, link to per-patient AI chat.
  - **AI chat** — per-patient text chat grounded in that patient's live data (stateless per question).
  - **Settings** — edit practitioner profile (name, title, specialization, bio, contact, fee).
- **Backend extensions:**
  - `practitioner_db.py` — SQLite store for practitioners, practitioner_tokens, appointments, practitioner_patient_connections, practitioner_notes.
  - `practitioner_auth.py` — practitioner auth routes + `get_current_practitioner` dependency (separate from patient auth).
  - `practitioner_routes.py` — practitioner-facing endpoints (appointments management, connected patients, patient detail data access with connection check, notes, AI summary/chat).
  - `patient_practitioner_routes.py` — patient-facing endpoints (browse practitioners, book appointment, my appointments, cancel).
  - `practitioner_ai.py` — Gemini Flash-Lite patient progress summaries + per-patient Q&A grounded in patient data.
  - Authorization: every `/practitioner/patients/{username}/*` endpoint verifies an active `practitioner_patient_connections` row before returning data.
- **Mobile app 3rd tab** — "Practitioners" tab with: searchable practitioner list, practitioner detail, book appointment form, my appointments view (with status badges + cancel for pending).
- **Seed extension** — 3 demo practitioners (`dranya`/`drchen`/`marcop`, all password `demodemo`) + one demo appointment from the `demo` patient to `dranya` (pending). Auto-seeds alongside the demo patient.

