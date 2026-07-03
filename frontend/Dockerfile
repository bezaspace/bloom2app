# syntax=docker/dockerfile:1.7
#
# Bloom2 patient frontend — Expo SDK 57 web export served as a static SPA.
#
# Multi-stage build:
#   builder  — Node installs deps and runs `expo export -p web` to produce
#              a static dist/. Build-time EXPO_PUBLIC_* env vars are inlined
#              into the JS bundle by Metro at this step.
#   runtime  — nginx:alpine serves the static dist/ with an SPA fallback.
#
# The service is internal-only (no host port) — the nginx reverse proxy
# (Phase 5) routes `/` to it.

# ---------------------------------------------------------------------------
# Builder stage
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (cached layer). package-lock.json pins exact
# versions, so a clean npm ci is reproducible.
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the application source.
COPY app.json tsconfig.json App.tsx index.ts ./
COPY assets/ ./assets/
COPY src/ ./src/

# Build-time env vars inlined into the JS bundle by Metro. These are the
# defaults for the standard staging stack (nginx proxy on :8080 with an
# /api prefix). Override via --build-arg in docker-compose if needed.
#
#   EXPO_PUBLIC_BACKEND_ORIGIN — the proxy origin the browser talks to
#   EXPO_PUBLIC_API_PREFIX     — the REST API path prefix the proxy strips
#
# In local dev (./sf) these are unset and config.ts falls back to
# localhost:8000, so the existing workflow is unaffected.
ARG EXPO_PUBLIC_BACKEND_ORIGIN=http://localhost:8080
ARG EXPO_PUBLIC_API_PREFIX=/api
ENV EXPO_PUBLIC_BACKEND_ORIGIN=${EXPO_PUBLIC_BACKEND_ORIGIN} \
    EXPO_PUBLIC_API_PREFIX=${EXPO_PUBLIC_API_PREFIX}

# Produce the static web export in dist/. `web.output: "single"` in app.json
# makes this a single-page app (one index.html + hashed assets).
RUN npx expo export -p web

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM nginx:alpine AS runtime

# Copy the static build into the nginx document root.
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace the default nginx config with our SPA-serving config.
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
