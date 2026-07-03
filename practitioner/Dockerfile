# syntax=docker/dockerfile:1.7
#
# Bloom2 practitioner web app — Next.js 16 (App Router) with standalone
# output, served at /practitioner/ behind the nginx reverse proxy.
#
# Multi-stage build following the official Next.js Docker guide:
#   https://docs.docker.com/guides/nextjs/containerize/
#
#   deps     — node:20-alpine, installs production deps from the lockfile.
#   builder  — node:20-alpine, installs ALL deps, runs `next build` with
#              build-time env vars (basePath, NEXT_PUBLIC_BACKEND_URL).
#   runner   — node:20-alpine, copies ONLY the standalone server + static
#              assets. Runs as non-root `node` user. No node_modules in
#              the runtime image.
#
# The service is internal-only (no host port) — the nginx reverse proxy
# (Phase 5) routes `/practitioner/` to it.

# ---------------------------------------------------------------------------
# Deps stage — install production dependencies (cached layer)
# ---------------------------------------------------------------------------
FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# ---------------------------------------------------------------------------
# Builder stage — full deps + build
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Install ALL dependencies (dev + prod) — needed for the build.
COPY package.json package-lock.json ./
RUN npm ci

# Copy the application source.
COPY next.config.ts tsconfig.json postcss.config.mjs ./
COPY src/ ./src/

# Build-time env vars:
#
#   PRACTITIONER_BASE_PATH — set as a build ARG so next.config.ts picks it
#     up and inlines the basePath into the standalone server + client
#     bundles. The app is then served at /practitioner/ behind the proxy.
#
#   NEXT_PUBLIC_BACKEND_URL — inlined into the client bundle so the
#     Socket.io chat client in MessageThread.tsx connects to the proxy
#     origin (http://localhost:8080) instead of the Docker-internal
#     backend hostname (which the browser can't resolve).
#
#   NEXT_PUBLIC_BASE_PATH — derived from PRACTITIONER_BASE_PATH in
#     next.config.ts and exposed to client bundles so withBasePath()
#     can prepend it to manual fetch() calls at runtime.
ARG PRACTITIONER_BASE_PATH=/practitioner
ARG NEXT_PUBLIC_BACKEND_URL=http://localhost:8080
ENV PRACTITIONER_BASE_PATH=${PRACTITIONER_BASE_PATH} \
    NEXT_PUBLIC_BACKEND_URL=${NEXT_PUBLIC_BACKEND_URL} \
    NEXT_PUBLIC_BASE_PATH=${PRACTITIONER_BASE_PATH} \
    NODE_ENV=production

# Build the standalone output. Next.js writes:
#   .next/standalone/  — self-contained server.js + minimal node_modules
#   .next/static/      — hashed JS/CSS/font/image assets
RUN npm run build

# ---------------------------------------------------------------------------
# Runtime stage — slim, non-root, standalone server only
# ---------------------------------------------------------------------------
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Next.js standalone server needs a writable .next/cache for ISR/dynamic
# routes. Create it owned by the non-root `node` user (uid 1000, present
# in the node:alpine base image).
RUN mkdir -p .next/cache && chown -R node:node /app

# Copy the standalone server (includes a minimal node_modules), the
# static assets, and the public dir if it existed at build time.
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static

# Runtime env vars (set by docker-compose, NOT inlined at build time):
#   PRACTITIONER_BACKEND_URL — http://backend:8000 (Docker internal)
#   PRACTITIONER_COOKIE_NAME — practitioner_session
# These are read by src/lib/env.ts at request time.

USER node
EXPOSE 3000

# The standalone server.js respects HOSTNAME and PORT env vars.
CMD ["node", "server.js"]
