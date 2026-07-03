# syntax=docker/dockerfile:1.7
#
# Bloom2 backend — FastAPI + Google ADK + Gemini Live API.
#
# Multi-stage build following the official uv Docker guide:
#   https://docs.astral.sh/uv/guides/integration/docker/
#
#   builder  — ghcr.io/astral-sh/uv image (uv pre-installed) creates a
#              self-contained .venv from the lockfile.
#   runtime  — python:3.12-slim with just the .venv + app source, no uv,
#              no build toolchain. Runs as a non-root user.
#
# The service is intended to run behind the nginx reverse proxy in the
# Compose stack and does NOT map a host port itself.

# ---------------------------------------------------------------------------
# Builder stage
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:0.9.18-python3.12-trixie AS builder

# uv settings:
#   UV_COMPILE_BYTECODE     — pre-compile .pyc for faster cold start
#   UV_LINK_MODE=copy       — copy (not symlink) so the venv is relocatable
#   UV_NO_DEV=1             — skip dev dependencies
#   UV_PROJECT_ENVIRONMENT  — fixed venv path we copy into the runtime stage
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Copy the manifest + lockfile first so dependency resolution is cached
# independently of application source changes.
COPY pyproject.toml uv.lock ./

# Install dependencies only (no project code) — reuses the cache layer
# above as long as the lockfile is unchanged.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Now copy the application source and install the project itself on top.
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY README.md ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# No build toolchain needed at runtime. Create a non-root user for the
# app and the persistent uploads directory (mounted as a volume in
# docker-compose so uploaded health documents survive restarts).
RUN groupadd --system --gid 1001 bloom && \
    useradd  --system --uid 1001 --gid bloom \
             --create-home --home-dir /home/bloom bloom && \
    install -d -o bloom -g bloom /app/uploads

WORKDIR /app

# Copy the self-contained virtualenv and application from the builder.
COPY --from=builder --chown=bloom:bloom /app/.venv /app/.venv
COPY --from=builder --chown=bloom:bloom /app/app    ./app
COPY --from=builder --chown=bloom:bloom /app/migrations ./migrations

# Put the venv on PATH so `uvicorn` resolves directly. HOST/PORT defaults
# match .env.example; the Compose service overrides DATABASE_URL etc.
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000

USER bloom
EXPOSE 8000

# Production command — no --reload. uvicorn served straight from the venv.
# A single worker is intentional for staging; the app holds in-memory ADK
# session state that is not shared across workers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
