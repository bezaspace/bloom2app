import { BACKEND_URL } from "./env";
import { getSessionToken } from "./session";

/** Server-side fetch wrapper: attaches the bearer token from the httpOnly
 * cookie to outgoing requests to the FastAPI backend.
 *
 * Always call from a Server Component or Route Handler. */
export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const token = await getSessionToken();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const url = path.startsWith("http") ? path : `${BACKEND_URL}${path}`;
  return fetch(url, { ...init, headers });
}

/** Convenience: apiFetch + JSON parse + error handling. Returns parsed JSON
 * or throws an Error with the backend detail message. */
export async function apiJson<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await apiFetch(path, init);
  if (!res.ok) {
    let detail = `Backend returned ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch {
      // ignore JSON parse errors
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}
