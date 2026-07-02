/** Centralized access to server-side env vars for the practitioner app. */

export const BACKEND_URL = (
  process.env.PRACTITIONER_BACKEND_URL || "http://localhost:8000"
).replace(/\/$/, "");

export const COOKIE_NAME =
  process.env.PRACTITIONER_COOKIE_NAME || "practitioner_session";
