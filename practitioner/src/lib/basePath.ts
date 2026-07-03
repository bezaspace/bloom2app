/**
 * Client-side helper for prepending the Next.js `basePath` to manual
 * `fetch()` calls in client components.
 *
 * Next.js auto-prefixes `<Link>`, `router.push()`, `redirect()`, and route
 * handler paths with the configured `basePath`. However, raw `fetch()`
 * calls to the app's own API routes (`/api/...`) are NOT auto-prefixed —
 * the browser sends them as-is, which breaks behind a reverse proxy that
 * mounts the app at a sub-path (e.g. `/practitioner`).
 *
 * `NEXT_PUBLIC_BASE_PATH` is set in `next.config.ts` from
 * `PRACTITIONER_BASE_PATH` and inlined into the client bundle at build
 * time. It is `""` in local dev (no basePath) and `/practitioner` in the
 * Dockerized staging build.
 *
 * Usage:
 *   const res = await fetch(withBasePath("/api/auth/logout"), { method: "POST" });
 */

const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/** Prepend the configured basePath to an app-relative path. */
export function withBasePath(path: string): string {
  if (!BASE_PATH) return path;
  if (path.startsWith(BASE_PATH)) return path;
  return `${BASE_PATH}${path}`;
}
