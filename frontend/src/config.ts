import { Platform } from "react-native";

/**
 * Backend connection configuration for the Bloom2 patient app.
 *
 * Two modes:
 *
 * 1. **Local dev** (`./sf`, Expo Go, emulator): no `EXPO_PUBLIC_*` env vars
 *    are set, so we fall back to a host:port against a locally-running
 *    backend on :8000.
 *    - Web:              localhost:8000
 *    - Android emulator: 10.0.2.2:8000  (maps to the host machine's localhost)
 *    - iOS simulator:    localhost:8000
 *
 *    For a PHYSICAL device, set the env vars to your dev machine's LAN IP,
 *    e.g. `EXPO_PUBLIC_BACKEND_ORIGIN=http://192.168.1.50:8000`. Both the
 *    phone and the computer must be on the same network and the backend
 *    must be reachable (it listens on 0.0.0.0:8000).
 *
 * 2. **Dockerized staging** (Expo web build): `EXPO_PUBLIC_*` env vars are
 *    inlined into the JS bundle at build time by Metro. The browser talks
 *    to a single nginx proxy origin (e.g. `http://localhost:8080`). REST
 *    calls go through the `/api` prefix (stripped by the proxy before
 *    forwarding to the backend); the voice WebSocket and Socket.io chat
 *    connect to the proxy origin directly at `/ws/...` and
 *    `/chat-ws/socket.io`.
 *
 *    Set in the Dockerfile build stage:
 *      EXPO_PUBLIC_BACKEND_ORIGIN=http://localhost:8080
 *      EXPO_PUBLIC_API_PREFIX=/api
 */

const DEFAULT_HOST = Platform.OS === "android" ? "10.0.2.2" : "localhost";
const DEFAULT_PORT = 8000;

// Build-time env vars (inlined by Metro). Undefined in local dev, so the
// nullish coalescing falls back to the host:port defaults below.
const PROXY_ORIGIN = process.env.EXPO_PUBLIC_BACKEND_ORIGIN;
const API_PREFIX = process.env.EXPO_PUBLIC_API_PREFIX;

/**
 * The origin the browser uses for everything that is NOT a REST API call —
 * i.e. the voice WebSocket (`ws://.../ws/...`) and Socket.io chat
 * (`/chat-ws/socket.io`). In local dev this is the bare backend origin.
 */
export const BACKEND_ORIGIN =
  PROXY_ORIGIN ?? `http://${DEFAULT_HOST}:${DEFAULT_PORT}`;

/**
 * Base URL for REST API calls (auth, dashboard, plans, etc.). In Docker this
 * includes the `/api` prefix that the nginx proxy strips before forwarding
 * to the backend. In local dev it is the bare backend origin (no prefix).
 */
export const HTTP_BASE = API_PREFIX
  ? `${BACKEND_ORIGIN}${API_PREFIX}`
  : BACKEND_ORIGIN;

/**
 * Base URL for the voice WebSocket. Always the proxy/backend origin with a
 * `ws://` scheme — the voice route is `/ws/{user_id}/{session_id}`.
 */
export const WS_BASE = BACKEND_ORIGIN.replace(/^http/, "ws");
