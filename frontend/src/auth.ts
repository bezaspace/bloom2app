import AsyncStorage from "@react-native-async-storage/async-storage";
import { HTTP_BASE } from "./config";

const TOKEN_KEY = "bloom2_auth_token";

export async function getToken(): Promise<string | null> {
  return AsyncStorage.getItem(TOKEN_KEY);
}

export async function setToken(token: string): Promise<void> {
  await AsyncStorage.setItem(TOKEN_KEY, token);
}

export async function clearToken(): Promise<void> {
  await AsyncStorage.removeItem(TOKEN_KEY);
}

export async function login(username: string, password: string): Promise<string> {
  const res = await fetch(`${HTTP_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = (await res.json()) as { detail?: string; token?: string };
  if (!res.ok || !data.token) {
    throw new Error(data.detail || "Login failed");
  }
  await setToken(data.token);
  return data.token;
}

export async function register(username: string, password: string): Promise<string> {
  const res = await fetch(`${HTTP_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = (await res.json()) as { detail?: string; token?: string };
  if (!res.ok || !data.token) {
    throw new Error(data.detail || "Registration failed");
  }
  await setToken(data.token);
  return data.token;
}

export async function logout(): Promise<void> {
  const token = await getToken();
  if (token) {
    await fetch(`${HTTP_BASE}/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
  }
  await clearToken();
}
