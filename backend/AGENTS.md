# Backend — Bloom2

## Database

The backend uses **PostgreSQL** (via `psycopg3` async) with a shared connection
pool managed in `app/db.py`. The old SQLite (`auth.db`) layer has been removed.

### Connection

- `DATABASE_URL` env var (default: `postgresql://bloom:bloom@localhost:5432/bloom2`)
- The pool is initialized in `app/main.py` startup handler via `init_pool()`
- Closed on shutdown via `close_pool()`

### Migrations

- SQL scripts live in `backend/migrations/*.sql` (numbered, executed in order)
- Applied automatically on startup via `run_migrations()` in `app/db.py`
- Tracked in the `_schema_migrations` table
- To add a new migration: create `backend/migrations/003_<name>.sql`

### Seeding

```bash
# Seed demo data (idempotent — skips if already seeded)
DATABASE_URL=postgresql://bloom:bloom@localhost:5432/bloom2 uv run python -m app.seed

# Wipe and re-seed
uv run python -m app.seed --force

# Check seed status
uv run python -m app.seed --check
```

### Local PostgreSQL for testing

```bash
docker run -d --name bloom2-pg -e POSTGRES_USER=bloom -e POSTGRES_PASSWORD=bloom \
  -e POSTGRES_DB=bloom2 -p 5432:5432 postgres:17-alpine
```

### Key files

- `app/db.py` — connection pool, migration runner, query helpers
- `app/database.py` — patient auth, profiles, docs, schedules, logs, biomarkers
- `app/practitioner_db.py` — practitioner accounts, appointments, connections, notes
- `app/chat_db.py` — chat messages, WS tokens
- `app/plan_db.py` — tracking plans, metrics, outcomes, phases, drafts, suggestions
- `migrations/` — versioned SQL schema scripts
