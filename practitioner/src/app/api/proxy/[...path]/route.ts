import { NextRequest, NextResponse } from "next/server";
import { BACKEND_URL } from "@/lib/env";
import { getSessionToken } from "@/lib/session";

/** Generic BFF proxy: forwards any /api/proxy/<path> request to the FastAPI
 * backend at <path>, attaching the bearer token from the httpOnly cookie.
 *
 * This keeps the browser from ever talking to the FastAPI origin directly —
 * CORS is a non-issue and the token is never visible to client JS. */
export async function handler(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  const { path } = await params;
  const targetPath = "/" + path.join("/");
  const url = new URL(request.url);
  const search = url.search; // preserve query string
  const target = `${BACKEND_URL}${targetPath}${search}`;

  const token = await getSessionToken();
  if (!token) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const headers = new Headers(request.headers);
  headers.set("Authorization", `Bearer ${token}`);
  // Remove Next.js-specific headers that FastAPI doesn't need.
  headers.delete("host");
  headers.delete("content-length");

  const init: RequestInit = {
    method: request.method,
    headers,
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  const res = await fetch(target, init);
  const body = await res.text();
  const respHeaders = new Headers();
  respHeaders.set("Content-Type", res.headers.get("Content-Type") ?? "application/json");
  return new NextResponse(body, { status: res.status, headers: respHeaders });
}

export {
  handler as GET,
  handler as POST,
  handler as PUT,
  handler as PATCH,
  handler as DELETE,
};
