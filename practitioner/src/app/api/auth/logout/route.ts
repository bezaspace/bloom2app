import { NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/env";
import { clearSessionCookie, getSessionToken } from "@/lib/session";

export async function POST() {
  const token = await getSessionToken();
  if (token) {
    // Best-effort: tell the backend to delete the token. Ignore errors.
    await fetch(`${BACKEND_URL}/practitioner/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {});
  }
  await clearSessionCookie();
  return NextResponse.json({ ok: true });
}
