# Progress

High-level feature map of what's been built in Bloom2 so far.

## 1. Auth
- Username/password login + register (PostgreSQL via psycopg3 async, PBKDF2)
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
  - `practitioner_db.py` — PostgreSQL store for practitioners, practitioner_tokens, appointments, practitioner_patient_connections, practitioner_notes.
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
- Migration runs automatically on startup (`run_plan_migration`); schema
  migrations applied via the versioned SQL migration runner in `app/db.py`.

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
- `--force` re-seeds the plan (idempotent check via `has_active_plan`).

## 9. Patient ↔ Practitioner Real-Time Text Chat

WhatsApp-style 1:1 text messaging between a patient and their connected
practitioner. Both sides see a chat thread with message bubbles, send
messages in real time, load conversation history on open, and get typing
indicators + read receipts. Messages persist in PostgreSQL.

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
- Schema created by the versioned SQL migration runner in `app/db.py`
  (no per-module sync init needed).

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

## 10. PostgreSQL Migration (SQLite → psycopg3 async)

Migrated the entire persistence layer from SQLite (sync `sqlite3` +
`threading.Lock`) to PostgreSQL via `psycopg3` async with a shared connection
pool. All four DB modules (`database.py`, `practitioner_db.py`, `chat_db.py`,
`plan_db.py`) were rewritten; every sync `_*_sync` helper was removed in favor
of natively async functions.

### Connection pool + migrations (`app/db.py`)
- `AsyncConnectionPool` from `psycopg.pool`, initialized on FastAPI startup
  (`init_pool`) and closed on shutdown (`close_pool`).
- `DATABASE_URL` env var (default `postgresql://bloom:bloom@localhost:5432/bloom2`).
- Query helpers: `fetchone`, `fetchall`, `execute`, `get_conn` (context
  manager for multi-statement transactions), `now` (timezone-aware UTC).
- **Versioned SQL migration runner** — reads `backend/migrations/*.sql` in
  order, tracks applied scripts in `_schema_migrations` table, idempotent.

### Schema (`backend/migrations/`)
- `001_initial_schema.sql` — all 20 tables with PostgreSQL-native types:
  `BIGSERIAL` IDs, `BOOLEAN` flags, `TIMESTAMPTZ` timestamps, `JSONB` for
  flexible blob columns (profile_json, plan_json, log_json, actions,
  outcomes_json, metrics_json, phases_json, suggestion_json), `TEXT` for
  free-form strings. Foreign keys with proper ordering (plan tables before
  daily_logs).
- `002_indexes.sql` — all secondary indexes for query performance.

### SQL conversions applied
- `?` placeholders → `%s`
- `INTEGER` 0/1 booleans → native `BOOLEAN` (with `bool()` wrapping on read)
- `AUTOINCREMENT` → `BIGSERIAL` / `RETURNING id` (no more `lastrowid`)
- `LIKE` → `ILIKE` for case-insensitive search
- `IS ?` → `IS NOT DISTINCT FROM %s` for nullable-equality upserts
- `INSERT OR IGNORE` / `INSERT OR REPLACE` → `INSERT ... ON CONFLICT ... DO UPDATE/NOTHING`
- `threading.Lock` serialization → async connection pool (no locks needed)
- JSONB columns return Python objects directly (no manual `json.loads` on read)
- `onboarded_at` changed from `TEXT` to `TIMESTAMPTZ`; `get_profile` converts
  back to ISO string for backward compat with downstream string parsing.

### Files touched
- `app/db.py` (new) — pool, migration runner, helpers
- `app/database.py` — full rewrite (patient auth, profiles, docs, schedules,
  logs, biomarkers, cascade delete)
- `app/practitioner_db.py` — full rewrite (practitioners, appointments,
  connections, notes, tokens)
- `app/chat_db.py` — full rewrite (messages, WS tokens)
- `app/plan_db.py` — full rewrite (plans, metrics, outcomes, phases, drafts,
  suggestions, metric logs, default-plan migration)
- `app/seed.py` — updated to use async DB functions; pool lifecycle managed
  in `main()` wrapper
- `app/main.py` — `init_pool()`/`close_pool()` added to startup/shutdown
- `app/plan_design_agent/tools.py` — removed dead sync helper stubs
- `backend/.env.example` — added `DATABASE_URL`
- `backend/pyproject.toml` — added `psycopg[binary,pool]>=3.2`
- `backend/AGENTS.md` (new) — DB setup documentation

### Verification
- All 4 DB modules import cleanly.
- Comprehensive integration test passed: user auth (register/verify/dedup/
  token lifecycle), profiles, docs, schedules, daily logs, biomarkers (with
  dedup), practitioners (register/verify/search/update/token), appointments
  (create/list/status transitions), connections (ensure/has/list/save AI
  summary), notes, chat (save/list/mark read/unread/conversations/WS token
  single-use + TTL), plans (create with child rows/get active/metric IDs),
  metric logs, drafts (create/get/update/replace/publish), suggestions
  (add/list/decide), cascade delete.
- Full seed script ran successfully against a local PostgreSQL 17 container:
  1 user, 1 profile, 3 practitioners, 1 appointment, 1 plan (6 metrics, 3
  outcomes, 3 phases), 22 daily logs (17 re-pointed to metric IDs), 10
  biomarkers, 6 chat messages, 1 connection.
- Idempotency verified (re-run skips; `--force` wipes and re-seeds).
- JSONB data verified queryable with `->>` operator.


## 11. Backend Dockerization (Phase 2 of staging plan)

Multi-stage Docker build for the backend, following the official uv Docker
guide (https://docs.astral.sh/uv/guides/integration/docker/).

### What was built
- `backend/Dockerfile` — two-stage build:
  - **Builder:** `ghcr.io/astral-sh/uv:0.9.18-python3.12-trixie` creates a
    self-contained `.venv` from the lockfile. Dependencies are installed
    first (cacheable layer) then the project itself. `UV_COMPILE_BYTECODE=1`
    pre-compiles `.pyc`, `UV_LINK_MODE=copy` makes the venv relocatable,
    `UV_NO_DEV=1` skips dev deps, `UV_PROJECT_ENVIRONMENT=/app/.venv` pins
    the venv path that gets copied to the runtime stage.
  - **Runtime:** `python:3.12-slim`, no build toolchain. Runs as a
    non-root `bloom` user (uid 1001). `/app/uploads` is created and owned
    by that user so the Compose volume mount persists uploaded health
    documents. The venv is on `PATH` so `uvicorn` resolves directly.
    Production CMD is `uvicorn app.main:app --host 0.0.0.0 --port 8000`
    (no `--reload`, single worker — in-memory ADK session state is not
    shared across workers).
- `backend/.dockerignore` — excludes `.venv/`, `__pycache__/`, `auth.db`,
  `uploads/`, `.env`, editor/OS noise so the build context stays small
  and the local venv never leaks into the image.

### Design notes
- The service is **internal-only** by design — no host port is published
  in the Compose stack. It is reached via the nginx reverse proxy
  (Phase 5). The verification run below mapped a host port only for
  manual testing.
- `DATABASE_URL` defaults to localhost in `.env.example` for local dev;
  the Compose service overrides it to `postgresql://...@postgres:5432/...`
  at runtime. No code change needed.
- Health check uses the existing `GET /health` endpoint.
- The `useradd` warning about uid 1001 > SYS_UID_MAX 999 is benign — the
  user is created correctly and the container runs as `bloom`.

### Verification
- Image built successfully: `bloom2-backend:phase2` (353MB disk, 80.2MB
  content).
- Ran against a throwaway `postgres:17-alpine` container on a shared
  Docker network with `DATABASE_URL` pointed at `bloom2-pg:5432`:
  - Pool initialized, both migrations applied, demo data seeded
    (1 user, 3 practitioners, plan, logs, biomarkers, chat).
  - `GET /health` → `{"status":"ok","model":"gemini-3.1-flash-live-preview"}`.
  - Patient login `demo`/`demodemo` → bearer token returned.
  - Practitioner login `dranya`/`demodemo` → bearer token + profile returned.
  - Container runs as non-root `bloom` user; `/app/uploads` is writable.

## 12. Frontend (Expo Web) Dockerization (Phase 3 of staging plan)

Containerized the React Native patient app as an Expo web (SPA) build served
by nginx, so it can be tested in a browser alongside the rest of the stack.

### What was built
- `frontend/src/config.ts` — rewritten to support build-time `EXPO_PUBLIC_*`
  env vars while preserving the local-dev defaults:
  - `EXPO_PUBLIC_BACKEND_ORIGIN` — the proxy origin the browser talks to
    (e.g. `http://localhost:8080`). Falls back to `localhost:8000` /
    `10.0.2.2:8000` (Android emulator) when unset.
  - `EXPO_PUBLIC_API_PREFIX` — the REST API path prefix the proxy strips
    (e.g. `/api`). When set, `HTTP_BASE = ${ORIGIN}${PREFIX}`; when unset,
    `HTTP_BASE` is the bare origin (current local-dev behavior).
  - New export `BACKEND_ORIGIN` — the raw origin used for the voice
    WebSocket (`WS_BASE`) and the Socket.io chat connection. `WS_BASE` is
    derived from it by swapping the scheme to `ws://`.
- `frontend/src/useChatSocket.ts` — Socket.io now connects to
  `BACKEND_ORIGIN` (not `HTTP_BASE`), since it talks to
  `/chat-ws/socket.io` directly and must NOT carry the `/api` prefix in
  the Dockerized build.
- `frontend/package.json` — added `export:web` script (`expo export -p web`).
- `frontend/app.json` — added `web.output: "single"` (SPA mode: one
  `index.html` + hashed assets, no per-route static HTML).
- `frontend/Dockerfile` — multi-stage build:
  - **Builder:** `node:20-alpine`, `npm ci` from the lockfile, then
    `npx expo export -p web`. `EXPO_PUBLIC_BACKEND_ORIGIN` and
    `EXPO_PUBLIC_API_PREFIX` are `ARG`s (defaulted to
    `http://localhost:8080` / `/api` for the standard proxy stack) exported
    as `ENV` so Metro inlines them into the JS bundle at build time.
  - **Runtime:** `nginx:alpine` serves the static `dist/` with an SPA
    fallback. Internal-only (port 80 in-container); the Phase 5 reverse
    proxy routes `/` to it.
- `frontend/nginx.conf` — SPA serving: long-lived `Cache-Control:
  immutable` for hashed JS/CSS/image assets, `try_files $uri $uri/
  /index.html` fallback for client-side routing, gzip on.
- `frontend/.dockerignore` — excludes `node_modules/`, `.expo/`, `dist/`,
  native folders, editor/OS noise.

### Design notes
- Local dev (`./sf`) is unaffected: with no `EXPO_PUBLIC_*` vars set,
  `config.ts` resolves to the same `http://localhost:8000` /
  `ws://localhost:8000` it always did. Verified with `tsc --noEmit`.
- The Socket.io origin split is the key subtlety the staging plan called
  out: Socket.io connects to `/chat-ws/socket.io` directly on the proxy
  origin, NOT under `/api`. Using `HTTP_BASE` for it would have produced
  `http://localhost:8080/api/chat-ws/socket.io` (wrong).

### Verification
- Image built: `bloom2-frontend:phase3` (95.6MB).
- `expo export -p web` succeeded in the builder: 662 modules →
  `dist/index.html` (1.2KB) + 3 JS bundles (1.4MB main, 25KB + 2.8KB
  audio engines) + 11 assets.
- Ran the container on port 18080:
  - `GET /` → 200, serves `index.html` (text/html).
  - `GET /some/deep/client/route` → 200 (SPA fallback to index.html).
  - JS asset → 200, 1.4MB, `application/javascript`.
- Inspected the inlined bundle: `BACKEND_ORIGIN="http://localhost:8080"`,
  `HTTP_BASE=`${BACKEND_ORIGIN}/api``, `WS_BASE=BACKEND_ORIGIN.replace(/^http/,
  "ws")` — exactly as designed.
- `npx tsc --noEmit` passes (local dev config path still type-checks).

## 13. Practitioner (Next.js) Dockerization (Phase 4 of staging plan)

Containerized the Next.js 16 practitioner web app with `output: "standalone"`
and a `basePath: "/practitioner"` so it is served at `/practitioner/` behind
the nginx reverse proxy.

### What was built
- `practitioner/next.config.ts` — set `output: "standalone"` and a
  build-time `basePath` driven by the `PRACTITIONER_BASE_PATH` env var.
  When unset (local dev), basePath is `""` and the app is served at `/`
  as before. Also exposes `NEXT_PUBLIC_BASE_PATH` to client bundles.
- `practitioner/src/lib/basePath.ts` (new) — `withBasePath()` helper for
  manual `fetch()` calls in client components. Next.js auto-prefixes
  `<Link>`, `router.push()`, `redirect()`, and route handler paths with
  the basePath, but raw `fetch()` calls are NOT auto-prefixed. The helper
  reads `NEXT_PUBLIC_BASE_PATH` (inlined at build time) and prepends it.
  In local dev it's a no-op (basePath is `""`).
- **All client-side `fetch()` calls updated** to use `withBasePath()`:
  - `src/components/layout/LogoutButton.tsx` — `/api/auth/logout`
  - `src/components/appointments/AppointmentActions.tsx` — appointment actions
  - `src/components/patients/PatientPanels.tsx` — AI summary + notes
  - `src/components/patients/ChatClient.tsx` — AI chat
  - `src/components/patients/SettingsForm.tsx` — profile update
  - `src/components/patients/PlanDesignerClient.tsx` — plan publish + design
  - `src/components/patients/PlanSuggestionsPanel.tsx` — suggestions CRUD
  - `src/components/patients/MessageThread.tsx` — chat messages + ws-token
  - `src/app/(auth)/login/page.tsx` — login
  - `src/app/(auth)/register/page.tsx` — register
- `practitioner/src/proxy.ts` — auth gate redirect now uses
  `request.nextUrl.basePath` so unauthenticated users are redirected to
  `${basePath}/login` (was hardcoded to `/login`). Next.js middleware
  receives the pathname WITHOUT the basePath (it's stripped before the
  proxy runs), so the public-route checks are unchanged.
- `practitioner/.env.example` — documented `PRACTITIONER_BASE_PATH` and
  the Docker Compose values for `PRACTITIONER_BACKEND_URL` (server-side,
  Docker internal `http://backend:8000`) and `NEXT_PUBLIC_BACKEND_URL`
  (client-side Socket.io, proxy origin `http://localhost:8080`).
- `practitioner/Dockerfile` — three-stage build:
  - **deps:** `node:20-alpine`, `npm ci --omit=dev` (cached layer).
  - **builder:** `node:20-alpine`, full `npm ci`, `npm run build` with
    build-time `ARG`s: `PRACTITIONER_BASE_PATH=/practitioner`,
    `NEXT_PUBLIC_BACKEND_URL=http://localhost:8080`. Both are exported
    as `ENV` so Next.js inlines them into the standalone server + client
    bundles. `NODE_ENV=production`.
  - **runner:** `node:20-alpine`, copies ONLY `.next/standalone` +
    `.next/static`. Runs as the non-root `node` user. No `node_modules`
    in the runtime image (standalone includes a minimal set). Internal-only
    (port 3000 in-container); the Phase 5 reverse proxy routes
    `/practitioner/` to it.
- `practitioner/.dockerignore` — excludes `node_modules/`, `.next/`,
  `*.tsbuildinfo`, local env files.

### Design notes
- **Server-side vs client-side env vars:** `PRACTITIONER_BACKEND_URL`
  (server-side BFF fetches to FastAPI) is a runtime env var set in the
  Compose service definition — the standalone server reads it at request
  time. `NEXT_PUBLIC_BACKEND_URL` (client-side Socket.io origin) and
  `PRACTITIONER_BASE_PATH` (basePath) are build-time — inlined into the
  JS bundle by Next.js/Metro in the builder stage.
- **Cookie path stays `/`:** The httpOnly session cookie is set with
  `path: "/"` so the browser sends it on all requests to the proxy
  origin, including the BFF route handlers under `${basePath}/api/...`.
  This works in both local dev (basePath="") and Docker (basePath="/practitioner").
- **No `<Image>` or `public/` dir:** The app has no `next/image` usage
  or static public assets, so the Dockerfile doesn't copy a `public/`
  dir (none exists).

### Verification
- Image built: `bloom2-practitioner:phase4` (267MB).
- `next build` succeeded with all 19 routes compiled (Turbopack).
- Ran the container on port 13000:
  - `GET /` → 404 (expected — app is at `/practitioner/`, not `/`).
  - `GET /practitioner` → 307 redirect to `/practitioner/login`
    (proxy.ts auth gate working with basePath).
  - `GET /practitioner/login` → 200, full HTML (10.6KB), correct title
    "Bloom2 — Practitioner".
  - Static assets at `/practitioner/_next/static/chunks/*.js` → 200,
    served correctly under the basePath.
- Inspected the inlined client bundle: `withBasePath` reads
  `"/practitioner"` (inlined `NEXT_PUBLIC_BASE_PATH`); Next.js router
  internals also reference `/practitioner` for auto-prefixed Links.
- Local dev unaffected: `npx tsc --noEmit` passes; `npm run build`
  without `PRACTITIONER_BASE_PATH` produces routes at `/`, `/login`,
  etc. as before.

## 14. nginx Reverse Proxy (Phase 5 of staging plan)

Single nginx entry point that routes by path prefix to the
internal-only services on the Compose network. The browser always talks
to one origin (the proxy); no other service exposes a host port. This
eliminates CORS issues and hardcoded URLs.

### What was built
- `proxy/nginx.conf` — complete nginx config (replaces the default
  `/etc/nginx/nginx.conf` so we have full control over the `http{}`
  context for the `map` directive). Routes:
  - `/api/` → `http://backend:8000/` — **strips** the `/api` prefix
    (trailing slash on `proxy_pass` tells nginx to strip the location
    prefix). `/api/health` → backend sees `/health`.
  - `/ws/` → `http://backend:8000` — voice WebSocket, path passed
    unchanged (no URI in `proxy_pass`). `proxy_read_timeout 3600s` for
    long-lived audio sessions.
  - `/chat-ws/` → `http://backend:8000` — Socket.io, path passed
    unchanged. `proxy_read_timeout 60s` (must exceed Socket.io's
    `pingInterval + pingTimeout` = 45s default, or nginx closes idle
    connections).
  - `/practitioner` → `http://practitioner:3000` — Next.js app, path
    passed unchanged (Next.js `basePath: /practitioner` expects the
    prefix). `/practitioner/login` → practitioner sees
    `/practitioner/login`.
  - `/` → `http://frontend:80` — Expo web SPA, catch-all.
- WebSocket upgrade handling: `map $http_upgrade $connection_upgrade`
  block at the `http` level (the standard nginx pattern from
  https://nginx.org/en/docs/http/websocket.html). Each WebSocket
  location sets `proxy_http_version 1.1` + `Upgrade` + `Connection`
  headers.
- `client_max_body_size 50M` — allows large health document uploads
  (PDFs/images to `/api/upload-doc`); the default 1MB is too small.
- `proxy/Dockerfile` — `nginx:alpine` + `COPY nginx.conf`. Single layer.
  Internal-only (port 80 in-container); the Compose service maps the
  host port (e.g. `8080:80`).
- `proxy/.dockerignore` — excludes everything except `nginx.conf`.

### Design notes
- **Prefix stripping vs preservation:** The `/api/` location uses
  `proxy_pass http://backend:8000/;` (trailing slash = strip prefix).
  The `/practitioner` and `/ws/` and `/chat-ws/` locations use
  `proxy_pass http://...:port;` (no URI = pass path unchanged). This
  distinction is the most common source of proxy misconfiguration —
  see https://www.getpagespeed.com/server-setup/nginx/nginx-proxy-pass-trailing-slash.
- **nginx resolves upstream hostnames at startup.** If a service isn't
  up yet, nginx fails to start. The Compose `depends_on` with health
  checks (Phase 6) ensures upstreams are ready before the proxy starts.
- **No `upstream` blocks** — direct `proxy_pass` with hostnames is
  simpler and sufficient for staging. Docker Compose's internal DNS
  resolves `backend`, `practitioner`, `frontend` to container IPs.
- **Logs to stdout/stderr** so `docker compose logs proxy` works.

### Verification
- Image built: `bloom2-proxy:phase5` (49.2MB).
- `nginx -t` passes when upstreams are resolvable (on the Compose
  network).
- End-to-end routing test with mock upstream containers on a shared
  Docker network:
  - `/api/health` → backend received `/health` (prefix stripped ✓)
  - `/api/dashboard/today` → backend received `/dashboard/today` ✓
  - `/practitioner/login` → practitioner received `/practitioner/login`
    (prefix preserved ✓)
  - `/practitioner/_next/static/chunks/abc.js` → practitioner received
    full path ✓
  - `/` → frontend received `/` (catch-all ✓)
  - `/some/deep/client/route` → frontend received `/some/deep/client/route`
    (SPA fallback will be handled by the frontend's own nginx ✓)
  - `/ws/user123/session456` → backend received `/ws/user123/session456`
    (prefix preserved ✓)
  - `/chat-ws/socket.io/?EIO=4&transport=polling` → backend received
    `/chat-ws/socket.io/?EIO=4` (prefix preserved, query params
    forwarded ✓)
  - WebSocket upgrade requests on `/ws/` and `/chat-ws/` forwarded to
    the backend (not rejected by nginx).

## 15. Docker Compose Assembly (Phase 6 of staging plan)

Assembled all 5 services into a single `docker compose up --build` stack
with health-checked dependency ordering, named volumes for data
persistence, and a single proxy entry point.

### What was built
- `docker-compose.yml` (project root) — 5 services:
  - **postgres** — `postgres:17-alpine`, named volume `pgdata` for data
    persistence. Health check via `pg_isready`. Internal-only.
  - **backend** — built from `./backend`, named volume `uploads` for
    health document persistence. Depends on postgres (service_healthy).
    Health check via Python `urllib` hitting `/health` (python:3.12-slim
    has no curl/wget). `start_period: 40s` gives time for pool init +
    migrations + seeding. Internal-only.
  - **practitioner** — built from `./practitioner` with build-time args
    (`PRACTITIONER_BASE_PATH=/practitioner`,
    `NEXT_PUBLIC_BACKEND_URL=http://localhost:${PROXY_PORT}`). Depends
    on backend (service_healthy). Runtime env:
    `PRACTITIONER_BACKEND_URL=http://backend:8000` (Docker internal).
    Internal-only.
  - **frontend** — built from `./frontend` with build-time args
    (`EXPO_PUBLIC_BACKEND_ORIGIN=http://localhost:${PROXY_PORT}`,
    `EXPO_PUBLIC_API_PREFIX=/api`). No depends_on (static SPA, doesn't
    need the backend to start). Internal-only.
  - **proxy** — built from `./proxy`. Depends on backend
    (service_healthy), practitioner + frontend (service_started). The
    ONLY host port mapping: `${PROXY_PORT:-8080}:80`.
- `.env.docker.example` — 3 variables:
  - `GOOGLE_API_KEY` (required) — Gemini API key.
  - `POSTGRES_PASSWORD` (default `bloom`) — PostgreSQL password.
  - `PROXY_PORT` (default `8080`) — host port for the nginx proxy.
    Configurable in case 8080 is taken (e.g. by another service on the
    dev machine). Since this is a build-time arg for the frontend and
    practitioner images, changing it requires a rebuild.
- `.gitignore` — added `.env.docker` (the actual env file with secrets).

### Design notes
- **`--env-file` flag:** Docker Compose's `${}` interpolation reads from
  the shell environment or the `.env` file at the project root by
  default. Since we use `.env.docker` (to keep Docker secrets separate
  from local dev `.env` files), the user must pass
  `--env-file .env.docker`:
  ```
  docker compose --env-file .env.docker up --build
  ```
  This makes `GOOGLE_API_KEY`, `POSTGRES_PASSWORD`, and `PROXY_PORT`
  available for interpolation in the compose file.
- **Required vs optional vars:** `GOOGLE_API_KEY` uses
  `${GOOGLE_API_KEY:?message}` — the `:?` guard causes Docker Compose
  to fail with a clear error if the var is unset (rather than silently
  using an empty string). `POSTGRES_PASSWORD` and `PROXY_PORT` use
  `:-default` so the stack works with sensible defaults even without
  the env file.
- **Health-checked dependency chain:**
  postgres (healthy) → backend (healthy) → practitioner + proxy.
  The proxy also depends on frontend (service_started) because nginx
  resolves upstream hostnames at startup — if frontend isn't up, nginx
  fails to start.
- **Backend health check uses Python urllib** (not curl/wget) because
  `python:3.12-slim` doesn't include either. The check hits
  `http://localhost:8000/health` from inside the container.
- **`PROXY_PORT` is a build-time arg** for frontend and practitioner
  (it's inlined into the JS bundle as `EXPO_PUBLIC_BACKEND_ORIGIN` /
  `NEXT_PUBLIC_BACKEND_URL`). Changing it requires rebuilding those
  images — `docker compose up --build` handles this automatically.
- **No `env_file:` directive** — all env vars are set via `environment:`
  blocks with `${}` interpolation from the `--env-file`. This keeps the
  source of truth in one place (the `.env.docker` file) and avoids the
  mismatch problem where `env_file` loads a var into a container but
  `${}` interpolation can't see it.

### Verification
- `docker compose --env-file .env.docker config` passes (valid YAML,
  correct interpolation).
- All 4 images built successfully (backend, frontend, practitioner,
  proxy).
- Full stack brought up with correct dependency ordering:
  postgres → (healthy) → backend → (healthy) → practitioner + proxy.
- All routes through the proxy verified:
  - `GET /api/health` → 200 `{"status":"ok","model":"gemini-3.1-flash-live-preview"}`
  - `GET /` → 200 (Expo web SPA, 1210 bytes)
  - `GET /some/deep/route` → 200 (SPA fallback)
  - `GET /practitioner` → 307 redirect to `/practitioner/login`
  - `GET /practitioner/login` → 200 (10.6KB HTML)
- Auth flows verified:
  - Patient login `demo`/`demodemo` via `POST /api/auth/login` → token returned.
  - Practitioner BFF login `dranya`/`demodemo` via `POST /practitioner/api/auth/login` → practitioner data + httpOnly cookie set.
  - Practitioner appointments via BFF proxy `GET /practitioner/api/proxy/practitioner/appointments` (with cookie) → 200 with appointment data.
- Dashboard data verified: onboarded=True, day 14 of plan, 8 schedule items, 10 biomarkers.
- **Data persistence verified:** `docker compose down` + `up` (without
  `-v`) — demo user, dashboard data, and all seeded data survived via
  the `pgdata` named volume. Seeder correctly skipped re-seeding
  ("demo user already onboarded — skipping").
- Frontend bundle verified to have `localhost:${PROXY_PORT}` correctly
  inlined as `EXPO_PUBLIC_BACKEND_ORIGIN`.
- Named volumes created: `bloom2app_pgdata`, `bloom2app_uploads`.
