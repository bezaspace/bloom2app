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

## 8. Practitioner-Designed Tracking Plans

Replaces the hardcoded 6-domain wellness tracking with practitioner-authored,
per-patient tracking plans. Each plan specifies **behavioral levers** (daily/
weekly metrics like steps, sleep, meditation) and **outcome targets** (biomarker
goals like HbA1c < 5.6%). The AI's role is to connect the two — helping the
patient see how daily behaviors move long-term outcomes.

### Data model (`plan_db.py`, `metric_templates.py`)
- **`plans`** — per-patient plan with version, title, rationale, is_active flag.
- **`plan_metrics`** — tracked metrics (template_id, label, unit, frequency,
  time_of_day, target_type, target_value, target_high, is_active, phase,
  sort_order).
- **`plan_outcomes`** — biomarker outcome targets (biomarker_name,
  target_value, target_direction, unit, target_date, current_value).
- **`plan_phases`** — time-boxed phases (phase_number, name, focus, actions,
  day_start, day_end).
- **`plan_drafts`** — in-progress drafts (status: draft/published/archived).
- **`plan_suggestions`** — AI-proposed plan adjustments for practitioner review.
- **`metric_templates`** — 25+ pre-built metric templates across categories
  (activity, sleep, nutrition, mental health, vitals, medication, symptoms).
- Migration runs automatically on startup (`run_plan_migration`).

### Backend API (`plan_routes.py` — 24 endpoints)
- **Plan CRUD**: `GET /plan`, `GET/POST/PUT/DELETE .../plan/draft`,
  `POST .../plan/draft/publish`, `GET .../plan` (practitioner).
- **Logging**: `POST /logs`, `GET /logs/today`, `GET /logs/recent` — all
  keyed by `metric_id`.
- **Analytics**: `GET /analytics/adherence` (per-metric + overall, single-date
  or N-day summary), `GET /analytics/trends` (direction + magnitude per
  metric), `GET /analytics/correlations`, `GET /analytics/biomarker-progress`
  (outcome target progress with on-track flags).
- **AI insights**: `GET /insights/weekly-report` (narrative + highlights +
  concerns), `GET /insights/trend-alerts` (severity-tagged alerts),
  `POST /insights/plan-suggestion`.
- **Plan suggestions**: `GET .../plan/suggestions`,
  `POST .../plan/suggestions/generate`,
  `POST .../plan/suggestions/{id}/decide` (approve applies to plan).
- **Metric templates**: `GET /metric-templates`,
  `GET /practitioner/plan-templates`.
- **Plan design agent**: `POST .../plan/design/start`,
  `POST .../plan/design/send`, `GET .../plan/design/history`.

### Schedule generator (`generator.py`)
- When a tracking plan is active, the daily schedule is built deterministically
  from the plan's metrics (no AI call needed — the plan IS the schedule).
  Each schedule item carries a `metric_id` for log matching.
- Falls back to the legacy AI-generated schedule when no plan is active.

### Plan Design Agent (`plan_design_agent/`)
- ADK agent (`agent.py`) with 9 tools (`tools.py`) for iterative plan editing:
  `add_metric`, `remove_metric`, `update_metric_target`, `add_outcome`,
  `remove_outcome`, `add_phase`, `update_plan_title`, `update_plan_rationale`,
  `get_current_draft`.
- `runner.py` wraps ADK `Runner` + `InMemorySessionService` for stateful
  multi-turn design conversations.
- Practitioner chats naturally ("track steps at 8000/day, target HbA1c below
  5.6%") and the agent calls tools to modify the draft plan in the DB.

### Voice agent update (`voice_agent/tools.py`, `agent.py`)
- 3 new plan-aware tools: `get_plan_progress` (today's adherence with speakable
  summary), `log_metric` (logs by label match against the plan),
  `get_plan_outcomes` (biomarker goals + current values).
- Agent instruction updated to prefer `log_metric` over `log_wellness_entry`
  when a plan is active, and to greet returning users with plan-based progress.

### AI insights (`plan_insights.py`)
- `generate_weekly_report` — Gemini Flash-Lite narrative summarizing the past
  week's adherence, trends, and outcome progress.
- `generate_trend_alerts` — flags metrics with concerning trends (severity:
  info/warning/critical).
- `generate_plan_suggestion` — proposes a plan adjustment based on adherence
  gaps (e.g. "lower step target to 6000 — patient averaging 4500").
- `apply_suggestion_to_plan` — applies an approved suggestion by creating a
  new plan version.
- `practitioner_ai.py` updated to include plan adherence data in patient
  summaries and Q&A context.

### Mobile app (`frontend/src/`)
- **`dashboard.ts`** — added all plan types + API functions (`getPlan`,
  `logMetric`, `getTodayMetricLogs`, `getAdherence`, `getTrends`,
  `getBiomarkerProgress`, `getWeeklyReport`, `getTrendAlerts`).
- **`MetricCard.tsx`** (new) — plan-aware metric card: progress ring, quick-log
  button, 7-day bar/line chart (bar for cumulative, line for point-in-time),
  "via voice" badge, template-based color coding.
- **`PlanOverviewCard.tsx`** (new) — plan title, rationale, overall adherence
  badge, current phase focus, outcome target progress rows with on-track/delta.
- **`InsightsCard.tsx`** (new) — AI weekly report (narrative + highlights +
  concerns) + trend alerts with severity badges; manual refresh.
- **`DashboardScreen.tsx`** — renders `PlanOverviewCard` + `MetricCard`s +
  `InsightsCard` when a tracking plan is active; falls back to legacy
  `WellnessDomainCard`s + `MentalHealthCard` when no plan is active.
- `ScheduleItem` and `LogEntry` types updated with optional `metric_id`.

### Practitioner web app (`practitioner/src/`)
- **Plan Designer** (`/patients/[username]/plan`):
  - **AI Chat tab** — conversational plan design via the ADK plan design agent;
    draft updates live in the preview above.
  - **Manual Builder tab** — template picker (click to add metric), inline
    editors for metrics/outcomes/phases with all fields (target type, frequency,
    time_of_day, etc.).
  - **Draft Preview** — shared between both tabs; shows metrics, outcomes,
    phases; "Publish Plan" button activates the plan for the patient.
- **Analytics dashboard** (`/patients/[username]/analytics`):
  - 30-day overall adherence % header.
  - Per-metric adherence bars (color-coded: green ≥80%, orange ≥50%, red <50%).
  - Trend cards (direction arrow + recent vs prior avg + magnitude).
  - Outcome target progress rows (target, current, delta, on-track bar).
  - Phase timeline showing current/past/future phases.
- **AI Plan Suggestions** — panel on the Plan Designer page: "Generate
  suggestion" button triggers AI analysis, pending suggestions show with
  approve/dismiss buttons (approve applies the change to the plan).
- **`types.ts`** — hand-mirrored all plan/analytics/suggestion types.
- Patient detail page gains "Design Tracking Plan" + "View Analytics" links.

### Seed update (`seed.py`)
- Demo patient now gets a practitioner-designed tracking plan authored by
  Dr. Anya Sharma: "Metabolic Health & Sleep Optimization — 90 Days" with
  6 metrics (steps, sleep, meditation, mood, BP, lisinopril), 3 outcome
  targets (HbA1c < 5.6%, LDL < 100, Vitamin D ≥ 30), 3 phases.
- Existing domain logs are re-pointed to the new metric IDs on seed.
- `--force` re-seeds the plan (idempotent check via `_has_active_plan_sync`).

## 9. Patient ↔ Practitioner Real-Time Text Chat

WhatsApp-style 1:1 text messaging between a patient and their connected
practitioner. Both sides see a chat thread with message bubbles, send
messages in real time, load conversation history on open, and get typing
indicators + read receipts. Messages persist in SQLite.

### Transport: Socket.io on FastAPI
- One `python-socketio` **AsyncServer** mounted on the FastAPI app at
  `/chat-ws` (served at `/chat-ws/socket.io/`). Both clients connect to it
  directly.
- **Patient mobile app** authenticates with its bearer token in the socket
  handshake `auth` payload.
- **Practitioner web app** keeps the BFF for all REST calls. For the socket,
  a new BFF route handler `POST /api/auth/ws-token` mints a short-lived,
  single-use WS token (60s TTL) via `POST /practitioner/ws-token`. The
  browser uses that token for the socket handshake — the long-lived bearer
  never reaches browser JS.
- Rooms: one per conversation (`f"{practitioner_id}:{patient_username}"`).
  On connect, the socket joins every room for which the user has an active
  connection.
- Auto-reconnect with backoff; polling fallback if WebSockets are blocked.

### Data model (`chat_db.py`)
- **`chat_messages`** — id, conversation_id, practitioner_id,
  patient_username, sender (`patient`|`practitioner`), body, created_at,
  read_at. Indexed on (conversation_id, id) for pagination.
- **`ws_tokens`** — short-lived single-use tokens for practitioner socket
  auth (token, practitioner_id, created_at, used). TTL 60s.
- Conversation list queries return last message preview + unread count.
- Migration runs automatically on startup (`_init_chat_db_sync`).

### Backend API (`chat_routes.py`)
- **Patient-facing** (`/chat`): `GET /conversations`,
  `GET /conversations/{practitioner_id}/messages` (cursor pagination via
  `before` param), `POST .../messages` (send, REST fallback),
  `POST .../read` (mark read).
- **Practitioner-facing** (`/practitioner/chat`): same shape, keyed by
  patient username.
- All endpoints verify an active `practitioner_patient_connections` row.
- Sending via REST also emits over the socket for real-time delivery.

### Socket events (`chat_socket.py`)
- `message` (client→server): persist + broadcast to room.
- `typing` (client→server): broadcast typing indicator (not persisted).
- `message_read` (client→server): mark other party's messages read + emit
  `read` to room.
- `message` / `typing` / `read` (server→client): the live events.

### Mobile app (`frontend/src/`)
- **`chat.ts`** — API client: `listConversations`, `getMessages`,
  `sendMessage`, `markConversationRead` + `ChatMessage` / `Conversation`
  types.
- **`useChatSocket.ts`** — React hook managing the Socket.io connection:
  connection status, `sendMessage`, `sendTyping`, `markRead`, `onMessage`,
  `onTyping`, `onRead` callbacks.
- **`ChatScreen.tsx`** — two views: conversation list (inbox with unread
  badges, last message preview, avatar) + WhatsApp-style thread (message
  bubbles left/right, auto-scroll, load-older on scroll-up, typing
  indicator, read receipts ✓/✓✓, optimistic send, keyboard-aware input
  bar).
- **`MainTabs.tsx`** — new 4th bottom tab "Messages" (💬).

### Practitioner web app (`practitioner/src/`)
- **`/api/auth/ws-token/route.ts`** — BFF route that mints the short-lived
  WS token (forwards to `/practitioner/ws-token` with the bearer from the
  httpOnly cookie).
- **`/messages`** — inbox page: lists all connected patients with last
  message preview, timestamp, unread badge. Patients without messages yet
  show a "Start a conversation" prompt.
- **`/patients/[username]/messages`** — thread page: renders
  `MessageThread` (full-height WhatsApp-style chat with bubbles, typing
  indicator, read receipts, load-older, optimistic send).
- **`MessageThread.tsx`** — `"use client"` component: fetches history via
  BFF proxy, connects to FastAPI Socket.io with the short-lived WS token,
  sends via socket + REST fallback.
- **Sidebar** — new "Messages" nav item (MessageSquare icon).
- **Patient detail page** — new "Message {username}" link (green,
  MessagesSquare icon) alongside the existing "Ask AI about this patient"
  link (indigo). Clearly distinguishes real messaging from AI Q&A.
- **`env.ts`** — `PUBLIC_BACKEND_URL` (NEXT_PUBLIC_) so the browser knows
  where to connect the socket.
- **`types.ts`** — `ChatMessage` + `PractitionerConversation` types.

### Seed update
- Demo patient (`demo`) and Dr. Anya Sharma (`dranya`) now have a seeded
  6-message conversation about sleep plans. The seeder establishes an
  active connection (simulating appointment acceptance) before seeding
  messages. Idempotent (skips if messages already exist). `--force` wipes
  chat data too.

### Dependencies
- Backend: `python-socketio` (added via `uv add`).
- Frontend + Practitioner: `socket.io-client` (added via `npm install`).

