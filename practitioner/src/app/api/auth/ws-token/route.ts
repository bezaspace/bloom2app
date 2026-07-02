import { NextResponse } from "next/server";
import { apiJson } from "@/lib/api";

/**
 * BFF route that mints a short-lived, single-use WebSocket token for the
 * practitioner's browser to authenticate a Socket.io connection to FastAPI.
 *
 * The browser never sees the long-lived bearer token — it only gets this
 * short-lived (60s) token, which it passes in the socket handshake `auth`
 * payload. This is the standard pattern for WebSockets behind a BFF.
 */
export async function POST() {
  try {
    const data = await apiJson<{ status: string; token: string; expires_in: number }>(
      "/practitioner/ws-token",
      { method: "POST" },
    );
    return NextResponse.json({
      token: data.token,
      expiresIn: data.expires_in,
    });
  } catch (e) {
    return NextResponse.json(
      { detail: e instanceof Error ? e.message : "Failed to mint WS token" },
      { status: 401 },
    );
  }
}
