import { cookies } from "next/headers";
import { COOKIE_NAME } from "./env";

/** Read the practitioner session token from the httpOnly cookie.
 * Server-only (uses next/headers). */
export async function getSessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(COOKIE_NAME)?.value ?? null;
}

/** Set the practitioner session cookie. Call from a Route Handler. */
export async function setSessionCookie(token: string): Promise<void> {
  const store = await cookies();
  store.set(COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30, // 30 days
  });
}

/** Clear the practitioner session cookie. */
export async function clearSessionCookie(): Promise<void> {
  const store = await cookies();
  store.delete(COOKIE_NAME);
}
