# Practitioner Web App — Next.js 16

## Architecture

This is the **practitioner-facing web app** for Bloom2, built with Next.js 16
(App Router, Server Components). It talks to the FastAPI backend
(`../backend/`) via a **BFF (Backend-for-Frontend)** pattern:

- The browser **never** talks to the FastAPI backend directly.
- All auth goes through `/api/auth/*` route handlers that set an
  **httpOnly cookie** (`practitioner_session`) on the Next.js origin.
- All data calls from client components go through `/api/proxy/<path>`,
  which reads the cookie and forwards the request to FastAPI with a
  `Authorization: Bearer <token>` header.
- Server Components call FastAPI directly via `@/lib/api` (`apiFetch` /
  `apiJson`), which reads the cookie from `next/headers`.

This keeps the JWT off the client, makes CORS a non-issue, and enables SSR.

## Key files

| File | Purpose |
|---|---|
| `src/proxy.ts` | Next 16 auth gate (redirects unauthed users to /login) |
| `src/lib/env.ts` | `BACKEND_URL`, `COOKIE_NAME` from env |
| `src/lib/session.ts` | Cookie get/set/clear (server-only) |
| `src/lib/api.ts` | `apiFetch` / `apiJson` — server-side fetch with bearer |
| `src/lib/types.ts` | Hand-mirrored backend types (keep in sync with backend) |
| `src/app/api/auth/*/route.ts` | BFF auth route handlers |
| `src/app/api/proxy/[...path]/route.ts` | Generic catch-all proxy |

## Commands

```bash
cd practitioner
npm install
npm run dev      # http://localhost:3000 (backend must be running on :8000)
npm run build    # production build
npm run start    # production server
```

## Env

See `.env.example`:
- `PRACTITIONER_BACKEND_URL` — FastAPI URL (default `http://localhost:8000`)
- `PRACTITIONER_COOKIE_NAME` — cookie name (default `practitioner_session`)

## Demo login

`dranya` / `demodemo` (seeded by `backend/app/seed.py`)

## Conventions

- Server Components by default; `"use client"` only for interactivity.
- Tailwind CSS v4 for styling (dark theme matching the mobile app).
- Backend types are hand-mirrored in `src/lib/types.ts` — update when
  backend response shapes change.
