/** Centralized access to server-side env vars for the practitioner app. */

export const BACKEND_URL = (
  process.env.PRACTITIONER_BACKEND_URL || "http://localhost:8000"
).replace(/\/$/, "");

export const COOKIE_NAME =
  process.env.PRACTITIONER_COOKIE_NAME || "practitioner_session";

/**
 * Public backend URL, exposed to the browser so the Socket.io client can
 * connect directly to FastAPI. This is safe to expose — the browser only uses
 * it with a short-lived, single-use WS token (never the long-lived bearer).
 *
 * For local dev this is the same as BACKEND_URL. In production, set this to
 * the externally-reachable URL of the FastAPI server.
 */
export const PUBLIC_BACKEND_URL = (
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  process.env.PRACTITIONER_BACKEND_URL ||
  "http://localhost:8000"
).replace(/\/$/, "");
