import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/env";
import { setSessionCookie } from "@/lib/session";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body?.username || !body?.password) {
    return NextResponse.json(
      { detail: "username and password are required" },
      { status: 400 },
    );
  }

  const res = await fetch(`${BACKEND_URL}/practitioner/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: body.username, password: body.password }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    return NextResponse.json(
      { detail: err.detail ?? "Invalid credentials" },
      { status: res.status },
    );
  }

  const data = await res.json();
  await setSessionCookie(data.token);
  return NextResponse.json({ practitioner: data.practitioner });
}
