import { Platform } from "react-native";

/**
 * Backend host for the Bloom2 voice assistant server.
 *
 * Defaults are chosen for local development:
 *  - Web:              localhost
 *  - Android emulator: 10.0.2.2  (maps to the host machine's localhost)
 *  - iOS simulator:    localhost
 *
 * If you run on a PHYSICAL device, set this to your dev machine's LAN IP,
 * e.g. "192.168.1.50". Both the phone and the computer must be on the same
 * network, and the backend must be reachable (it listens on 0.0.0.0:8000).
 */
const DEFAULT_HOST =
  Platform.OS === "android" ? "10.0.2.2" : "localhost";

// Override here for a physical device, or set via env if you prefer.
export const BACKEND_HOST = DEFAULT_HOST;
export const BACKEND_PORT = 8000;

export const HTTP_BASE = `http://${BACKEND_HOST}:${BACKEND_PORT}`;
export const WS_BASE = `ws://${BACKEND_HOST}:${BACKEND_PORT}`;
