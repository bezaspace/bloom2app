import { getToken } from "./auth";
import { HTTP_BASE } from "./config";

/** A chat message in a patient <-> practitioner conversation. */
export interface ChatMessage {
  id: number;
  conversation_id: string;
  practitioner_id: number;
  patient_username: string;
  sender: "patient" | "practitioner";
  body: string;
  created_at: string;
  read_at: string | null;
}

/** A conversation summary for the inbox view. */
export interface Conversation {
  patient_username: string;
  practitioner_id: number;
  conversation_id: string;
  last_message: ChatMessage | null;
  unread_count: number;
  practitioner?: PractitionerInfo;
}

/** Minimal practitioner info attached to patient-facing conversations. */
export interface PractitionerInfo {
  id: number;
  username: string;
  full_name: string;
  title: string | null;
  specialization: string | null;
  is_active: boolean;
}

async function _authHeaders(): Promise<HeadersInit> {
  const token = await getToken();
  if (!token) throw new Error("Not authenticated");
  return { Authorization: `Bearer ${token}` };
}

/** List the patient's chat conversations (one per connected practitioner they
 * have exchanged messages with), with last message preview + unread count. */
export async function listConversations(): Promise<Conversation[]> {
  const headers = await _authHeaders();
  const res = await fetch(`${HTTP_BASE}/chat/conversations`, { headers });
  if (!res.ok) throw new Error(`Failed to fetch conversations: ${res.status}`);
  const data = (await res.json()) as { conversations: Conversation[] };
  return data.conversations;
}

/** Fetch message history for a conversation with a practitioner, oldest-first.
 * Use `before` for cursor pagination (load older on scroll-up). */
export async function getMessages(
  practitionerId: number,
  before?: number,
  limit: number = 50,
): Promise<{ messages: ChatMessage[]; hasMore: boolean }> {
  const headers = await _authHeaders();
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (before) params.set("before", String(before));
  const res = await fetch(
    `${HTTP_BASE}/chat/conversations/${practitionerId}/messages?${params}`,
    { headers },
  );
  if (!res.ok) throw new Error(`Failed to fetch messages: ${res.status}`);
  const data = (await res.json()) as {
    messages: ChatMessage[];
    has_more: boolean;
  };
  return { messages: data.messages, hasMore: data.has_more };
}

/** Send a message as the patient (REST fallback / primary path). */
export async function sendMessage(
  practitionerId: number,
  body: string,
): Promise<ChatMessage> {
  const headers = await _authHeaders();
  const res = await fetch(
    `${HTTP_BASE}/chat/conversations/${practitionerId}/messages`,
    {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    },
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to send: ${res.status}`);
  }
  const data = (await res.json()) as { message: ChatMessage };
  return data.message;
}

/** Mark all practitioner messages in the conversation as read. */
export async function markConversationRead(
  practitionerId: number,
): Promise<void> {
  const headers = await _authHeaders();
  await fetch(`${HTTP_BASE}/chat/conversations/${practitionerId}/read`, {
    method: "POST",
    headers,
  });
}
