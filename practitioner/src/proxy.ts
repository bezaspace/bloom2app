import { NextRequest, NextResponse } from "next/server";
import { COOKIE_NAME } from "@/lib/env";

/** Auth gate for the practitioner app. Redirects unauthenticated users
 * from /(app)/* routes to /login. Authorization itself stays on the
 * backend — every BFF call re-verifies the token. */
export function proxy(request: NextRequest): NextResponse {
  const { pathname, basePath } = request.nextUrl;
  const token = request.cookies.get(COOKIE_NAME)?.value;

  // Public routes that don't require auth. (pathname is the raw path
  // WITHOUT the basePath — Next.js strips it before middleware runs.)
  const isPublic =
    pathname === "/login" ||
    pathname === "/register" ||
    pathname.startsWith("/api/");

  if (isPublic) {
    return NextResponse.next();
  }

  if (!token) {
    // Build the redirect URL with the basePath so the browser lands on
    // the correct login page behind the reverse proxy.
    const loginUrl = new URL(`${basePath}/login`, request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
