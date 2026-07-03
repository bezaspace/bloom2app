import type { NextConfig } from "next";

/**
 * The basePath is set at build time via the PRACTITIONER_BASE_PATH env var.
 *
 * - Local dev (`npm run dev`): env var is unset → basePath is "" → the app
 *   is served at `/` as before. No workflow change.
 * - Dockerized staging: the Dockerfile sets `PRACTITIONER_BASE_PATH=/practitioner`
 *   so the app is served at `/practitioner/` behind the nginx reverse proxy.
 *
 * Next.js auto-prefixes `<Link>`, `router.push()`, `redirect()`, and route
 * handler paths with the basePath. Manual `fetch()` calls in client
 * components are NOT auto-prefixed — use the `withBasePath()` helper from
 * `src/lib/basePath.ts` for those.
 */
const basePath = process.env.PRACTITIONER_BASE_PATH || "";

const nextConfig: NextConfig = {
  output: "standalone",
  ...(basePath ? { basePath } : {}),
  env: {
    // Exposed to client bundles so withBasePath() can read it at runtime.
    NEXT_PUBLIC_BASE_PATH: basePath,
  },
};

export default nextConfig;
