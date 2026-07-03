# syntax=docker/dockerfile:1.7
#
# Bloom2 nginx reverse proxy — the single entry point for the staging stack.
#
# Routes by path prefix to the internal-only services:
#   /api/          → backend (FastAPI)          — strip /api prefix
#   /ws/           → backend (voice WebSocket)  — pass path unchanged
#   /chat-ws/      → backend (Socket.io chat)   — pass path unchanged
#   /practitioner  → practitioner (Next.js)     — pass path unchanged
#   /              → frontend (Expo web SPA)    — catch-all
#
# Only this container exposes a host port (mapped in docker-compose).
# All other services are internal-only on the Compose network.

FROM nginx:alpine

# Replace the entire default nginx.conf with our reverse-proxy config.
# We need full control over the http{} context for the `map` directive
# used by the WebSocket upgrade headers.
COPY nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
