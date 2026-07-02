# Bloom2 — Local Staging Plan

A high-level outline for containerizing the Bloom2 platform and migrating
from SQLite to PostgreSQL, with the goal of producing a single
`docker compose up` local staging environment that mirrors a future GCP
deployment.

This document captures the **what**, the **why**, and the **how at a high
level** — but deliberately leaves implementation details to the developer
executing it. Treat it as a map, not a script.

---

## Goal

Stand up the entire Bloom2 platform locally via Docker Compose, with every
service that will eventually run on GCP (everything except the React Native
mobile app, which stays on the user's phone). The React Native app is
included in this staging stack **only as an Expo Web build** for testing —
it keeps all mobile features so the same code can later become the Android
app with no functional changes.

This staging environment is the dress rehearsal for GCP. If it runs cleanly
here, the GCP migration is mostly a matter of swapping Docker Compose for
Cloud Run + Cloud SQL.

---

## Current State

Bloom2 has three components, all currently run via local dev scripts
(`./sb`, `./sf`, `npm run dev`):

| Component | Stack | Role |
|-----------|-------|------|
| **Backend** (`backend/`) | FastAPI + Google ADK + Gemini Live API | Voice assistant, REST APIs, Socket.io chat, AI features |
| **Frontend** (`frontend/`) | Expo SDK 57 / React Native 0.86 | Patient app (Dashboard, Talk, Practitioners, Messages) |
| **Practitioner** (`practitioner/`) | Next.js 16 (App Router) | Practitioner web app (BFF auth pattern, httpOnly cookies) |

**Database today:** a single SQLite file (`backend/auth.db`) accessed via
Python's built-in `sqlite3` module with a `threading.Lock` for write
serialization. No ORM, no async driver, no connection pool. All four DB
modules (`database.py`, `practitioner_db.py`, `chat_db.py`, `plan_db.py`)
share this file and lock.

**Session state today:** both the voice agent and the plan design agent use
ADK's `InMemorySessionService` — conversation state is lost on restart.
This is acceptable for staging and is explicitly out of scope for this
phase.

---

## Decisions Taken (and Why)

### 1. Migrate SQLite → PostgreSQL

**Why:** SQLite is a file-based, single-writer database. It cannot run on
GCP as a managed service, doesn't support concurrent connections from
multiple backend replicas, and the thread-lock pattern doesn't scale. Every
GCP deployment uses Cloud SQL (PostgreSQL). Migrating now — in staging —
means the GCP move later is just infrastructure, not a code change.

**How (high level):** Replace the `sqlite3` connection pattern with an
async PostgreSQL connection pool created in the FastAPI lifespan. Refactor
all four DB modules to use it. Convert SQLite-specific SQL to PostgreSQL
syntax. Move schema creation from inline `CREATE TABLE IF NOT EXISTS` calls
into versioned migration scripts.

### 2. Driver: psycopg3 (async)

**Why:** The codebase uses raw SQL strings (no ORM), so we need a driver
that fits that style. psycopg3 was chosen over asyncpg because its `%s`
placeholder syntax is a closer mechanical match to sqlite3's `?` — making
the migration of hundreds of existing query strings simpler and less
error-prone. psycopg3 is also fully compatible with GCP Cloud SQL and
supports both direct use and SQLAlchemy integration later if needed.

**How (high level):** Add `psycopg[binary,pool]` as a dependency. Create a
central `db.py` module that owns the `AsyncConnectionPool` and provides
helper functions/cursors. All DB modules import from it.

### 3. Migrations: Versioned SQL Scripts (not Alembic)

**Why:** The current codebase already does ad-hoc `ALTER TABLE IF NOT
EXISTS` checks — a manual, informal migration system. Formalizing that into
numbered `.sql` files run by a lightweight runner matches the existing
style and avoids the complexity of Alembic for a project this size. Alembic
can be introduced later as a natural evolution without rework.

**How (high level):** A `backend/migrations/` directory with numbered SQL
files. A small runner tracks applied versions in a `_schema_migrations`
table and executes any unrun scripts on startup.

### 4. Single nginx Reverse Proxy as Entry Point

**Why:** Without a reverse proxy, the browser needs to know the backend's
host:port directly — leading to hardcoded URLs, CORS configuration, and
different settings for dev vs Docker. A single proxy on one port solves
this elegantly: the browser always talks to one origin, and the proxy
routes by path prefix (`/api/` → backend, `/practitioner/` → Next.js, `/`
→ Expo SPA, `/ws/` and `/chat-ws/` → backend WebSockets). No CORS issues.
One URL to remember. This also mirrors how production typically works
(behind a load balancer / API gateway).

**How (high level):** An nginx container in the Compose stack listens on
one port (e.g., 8080) and proxies to the internal services. All other
services are internal-only (no host port mapping).

### 5. Expo Web Build for Frontend Testing

**Why:** The React Native app is the real patient app and will eventually
run on mobile phones. But for local staging, we need to test it in a
browser alongside everything else. Expo's web export (`expo export -p web`)
produces a static SPA that runs the same code — including the voice
assistant, which uses the Web Audio API on web and the native audio
library on mobile. The platform-aware audio layer is already properly
guarded with dynamic imports, so the web build works today.

**How (high level):** Multi-stage Dockerfile: Node stage runs `expo
export`, nginx stage serves the static `dist/` with an SPA fallback. The
backend URL is injected at build time via `EXPO_PUBLIC_*` environment
variables (Expo inlines these into the JS bundle).

### 6. Next.js Standalone Output for Practitioner App

**Why:** Next.js's `output: 'standalone'` produces a minimal self-contained
server that doesn't need the full `node_modules` in the runtime image —
significantly smaller Docker images and faster cold starts. This is the
documented best practice for containerized Next.js deployments.

**How (high level):** Set `output: 'standalone'` in `next.config.ts`. The
Dockerfile copies the standalone server + static assets into a slim
runtime image. The app runs behind the reverse proxy at `/practitioner/`
(via Next.js `basePath`).

### 7. No pgAdmin in the Stack

**Why:** Keeps the stack lean. Database inspection can be done via `psql`
CLI or external tools. pgAdmin can always be added back if needed.

### 8. Session State Stays In-Memory (Explicitly Deferred)

**Why:** Migrating ADK's `InMemorySessionService` to a persistent backend
(`DatabaseSessionService`) is a separate concern from containerization and
DB migration. Active voice conversations and plan design chat sessions
resetting on container restart is acceptable for staging. Tackling it now
would expand scope significantly without blocking the staging goal.

**Future:** ADK's `DatabaseSessionService` (backed by PostgreSQL) can
replace `InMemorySessionService` in both `main.py` and
`plan_design_agent/runner.py` when persistence is needed.

---

## What Needs to Happen (Outline)

### Phase 1: PostgreSQL Migration (Backend) — Largest Effort

This is the foundation. Everything else depends on it.

- Add `psycopg[binary,pool]` to `backend/pyproject.toml`.
- Create a central DB module (`app/db.py`) that owns the async connection
  pool, initialized in the FastAPI lifespan. This replaces the current
  `sqlite3` + `threading.Lock` pattern.
- Create a `backend/migrations/` directory with versioned SQL files
  defining the full PostgreSQL schema (all tables across all four DB
  modules). Write a small migration runner that tracks applied versions.
- Refactor all four DB modules (`database.py`, `practitioner_db.py`,
  `chat_db.py`, `plan_db.py`) to use the new pool-based async layer
  instead of `sqlite3` directly. Convert SQL syntax:
  - `?` placeholders → `%s`
  - `INTEGER PRIMARY KEY AUTOINCREMENT` → `BIGSERIAL PRIMARY KEY` (or
    `GENERATED ALWAYS AS IDENTITY`)
  - `INTEGER` booleans → `BOOLEAN`
  - `TEXT` timestamps → `TIMESTAMPTZ`
  - `TEXT` JSON columns → `JSONB`
  - `PRAGMA table_info()` → `information_schema.columns` queries
  - Pass Python `datetime` objects instead of ISO strings for timestamps
- Update `seed.py` to use the new DB layer. Keep all demo data identical.
  `SEED_ON_STARTUP` continues to control auto-seeding.
- Update `main.py` lifespan: create pool → run migrations → seed (if
  enabled) → ready.
- Add `DATABASE_URL` to `.env.example`.

**Note on schema design:** The developer executing this should design the
PostgreSQL schema fresh based on the existing SQLite tables (documented in
`progress.md` and visible in the current code). This is an opportunity to
use proper PostgreSQL types (`JSONB`, `TIMESTAMPTZ`, `BOOLEAN`,
`BIGSERIAL`) rather than copying SQLite's `TEXT`-for-everything pattern.

### Phase 2: Backend Dockerization

- Write a multi-stage `backend/Dockerfile` using the official uv Docker
  approach (builder stage with `ghcr.io/astral-sh/uv`, runtime stage with
  `python:3.12-slim`). No `--reload` in production CMD.
- Mount a volume for `uploads/` so uploaded health documents persist.
- Backend is internal-only (no host port) — accessed via the reverse proxy.
- Health check uses the existing `/health` endpoint.

### Phase 3: Frontend (Expo Web) Dockerization

- Update `frontend/src/config.ts` to support `EXPO_PUBLIC_*` environment
  variables for backend origin and API path prefix. Keep the existing
  defaults working for local dev (so `./sf` still works outside Docker).
- Add an `export:web` script to `frontend/package.json`.
- Add `web.output: "single"` to `frontend/app.json` (SPA mode).
- Write a multi-stage `frontend/Dockerfile`: Node stage builds the Expo
  web export with build-time env vars set, nginx stage serves the static
  `dist/` with an SPA fallback config.
- The Socket.io connection origin needs to be the proxy origin (not the
  API-prefixed URL) since Socket.io connects to `/chat-ws/socket.io`
  directly.

### Phase 4: Practitioner (Next.js) Dockerization

- Set `output: 'standalone'` in `practitioner/next.config.ts`.
- Set `basePath: '/practitioner'` so the app is served at
  `/practitioner/` behind the reverse proxy.
- Update any client-side `fetch()` calls that use absolute paths (e.g., in
  `MessageThread.tsx`) to prepend the basePath. Next.js handles `<Link>`,
  `router.push()`, and route handler paths automatically when basePath is
  set — only manual `fetch()` calls in client components need updating.
- Write a multi-stage `practitioner/Dockerfile` using the standalone
  output pattern.
- Environment split:
  - `PRACTITIONER_BACKEND_URL` → `http://backend:8000` (server-side BFF,
    Docker internal network)
  - `NEXT_PUBLIC_BACKEND_URL` → `http://localhost:8080` (client-side
    Socket.io, through the proxy)

### Phase 5: nginx Reverse Proxy

- Create a `proxy/` directory with a Dockerfile and `nginx.conf`.
- The proxy listens on one port (e.g., 8080) and routes:
  - `/api/` → backend (strip `/api` prefix)
  - `/ws/` → backend (WebSocket upgrade)
  - `/chat-ws/` → backend (Socket.io, WebSocket upgrade)
  - `/practitioner/` → practitioner Next.js app
  - `/` → frontend (Expo web SPA, catch-all)
- WebSocket locations need `proxy_http_version 1.1` + upgrade headers +
  long read timeout (voice sessions are long-lived).

### Phase 6: Docker Compose Assembly

- Create `docker-compose.yml` at the project root.
- Services: `postgres`, `backend`, `practitioner`, `frontend`, `proxy`.
- Only the `proxy` service exposes a host port. All others are
  internal-only on the Compose network.
- PostgreSQL uses a named volume for data persistence. Backend uses a
  named volume for uploads.
- Health checks: PostgreSQL via `pg_isready`, backend via `/health`.
  Services depend on healthy upstreams before starting.
- Create `.env.docker.example` with `GOOGLE_API_KEY` and
  `POSTGRES_PASSWORD`. The actual `.env.docker` is gitignored.

### Phase 7: Verification

After `docker compose up --build`:

- Backend health check passes.
- Demo data seeds correctly (login as `demo`/`demodemo` and
  `dranya`/`demodemo`).
- Expo web app at the proxy origin: dashboard, voice assistant (mic +
  headphones required), practitioners, messages all work.
- Practitioner app at `/practitioner/`: dashboard, appointments, patients,
  plan designer, analytics, messages all work.
- Voice WebSocket connects through the proxy.
- Socket.io chat connects through the proxy (real-time messaging between
  patient and practitioner).
- Data persists across `docker compose down` + `up` (volumes).

---

## What's Explicitly Out of Scope

- **GCP deployment** (Cloud SQL, Cloud Run, Artifact Registry) — next phase
- **ADK session persistence** (`DatabaseSessionService`) — future
- **Alembic migrations** — can evolve from versioned SQL scripts later
- **HTTPS / TLS** — not needed for local staging
- **Secrets management** (Docker secrets, KMS) — simple env vars for now
- **React Native Android/iOS native builds** — Expo web is for testing only
- **CI/CD pipeline** — not part of local staging
- **CORS configuration beyond the proxy** — the proxy makes everything
  same-origin from the browser's perspective

---

## Key Architectural Principles for the Implementer

1. **The browser always talks to one origin** (the proxy). No service
   other than the proxy should expose a host port. This eliminates CORS
   issues and hardcoding.

2. **Server-side code uses Docker internal hostnames** (`backend:8000`,
   `postgres:5432`). Client-side code (browser JS) uses the proxy origin
   (`http://localhost:8080`). Never confuse these — the browser cannot
   resolve Docker internal names.

3. **Build-time vs runtime env vars:** Expo's `EXPO_PUBLIC_*` and Next.js's
   `NEXT_PUBLIC_*` variables are inlined into the JS bundle at build time
   (in the Dockerfile build stage). Server-side env vars
   (`PRACTITIONER_BACKEND_URL`, `DATABASE_URL`) are set at runtime in the
   Compose service definition.

4. **Keep local dev working:** The changes to `config.ts`, `next.config.ts`,
   and the backend env vars should not break the existing `./sb` / `./sf` /
   `npm run dev` workflow. Defaults should fall back to the current
   localhost behavior when env vars aren't set.

5. **The PostgreSQL schema is a fresh design**, not a line-by-line port of
   the SQLite schema. Use proper PostgreSQL types. This is the right time
   to do it — doing it later in production is much harder.

6. **Don't over-engineer.** This is staging. The goal is a working
   `docker compose up` that mirrors GCP, not a production-hardened system.
   Skip PgBouncer, skip HA, skip TLS, skip secrets management. Those come
   with GCP.
