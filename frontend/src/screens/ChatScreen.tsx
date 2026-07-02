import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { useFocusEffect } from "@react-navigation/native";
import {
  getMessages,
  listConversations,
  markConversationRead,
  sendMessage as apiSendMessage,
  type ChatMessage,
  type Conversation,
} from "../chat";
import { useChatSocket } from "../useChatSocket";

type ScreenView =
  | { kind: "list" }
  | { kind: "thread"; conversation: Conversation };

export function ChatScreen() {
  const [view, setView] = useState<ScreenView>({ kind: "list" });

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Messages</Text>
      </View>
      {view.kind === "list" && (
        <ConversationList
          onOpen={(c) => setView({ kind: "thread", conversation: c })}
        />
      )}
      {view.kind === "thread" && (
        <ThreadView
          conversation={view.conversation}
          onBack={() => setView({ kind: "list" })}
        />
      )}
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Conversation list (inbox)
// ---------------------------------------------------------------------------
function ConversationList({
  onOpen,
}: {
  onOpen: (c: Conversation) => void;
}) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { onMessage } = useChatSocket();

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const list = await listConversations();
      setConversations(list);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load(false);
    }, [load]),
  );

  // Live-update the inbox when a new message arrives.
  useEffect(() => {
    const unsub = onMessage(() => {
      void load(true);
    });
    return unsub;
  }, [onMessage, load]);

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color="#6366f1" size="large" />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.flex}
      contentContainerStyle={styles.scrollContent}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => {
            setRefreshing(true);
            void load(true);
          }}
          tintColor="#6366f1"
        />
      }
    >
      {error && <Text style={styles.errorText}>{error}</Text>}
      {conversations.length === 0 && !error && (
        <View style={styles.emptyState}>
          <Text style={styles.emptyText}>No conversations yet.</Text>
          <Text style={styles.emptySubtext}>
            Once a practitioner accepts your appointment, you can message them here.
          </Text>
        </View>
      )}
      {conversations.map((c) => {
        const last = c.last_message;
        const name = c.practitioner?.full_name ?? `Practitioner #${c.practitioner_id}`;
        return (
          <Pressable
            key={c.conversation_id}
            style={styles.convCard}
            onPress={() => onOpen(c)}
          >
            <View style={styles.convRow}>
              <View style={styles.convAvatar}>
                <Text style={styles.convAvatarText}>
                  {name.charAt(0).toUpperCase()}
                </Text>
              </View>
              <View style={styles.convBody}>
                <View style={styles.convHeaderRow}>
                  <Text style={styles.convName} numberOfLines={1}>
                    {name}
                  </Text>
                  {last && (
                    <Text style={styles.convTime}>
                      {formatTime(last.created_at)}
                    </Text>
                  )}
                </View>
                <Text style={styles.convPreview} numberOfLines={1}>
                  {last
                    ? `${last.sender === "patient" ? "You: " : ""}${last.body}`
                    : "Start a conversation"}
                </Text>
              </View>
              {c.unread_count > 0 && (
                <View style={styles.unreadBadge}>
                  <Text style={styles.unreadText}>{c.unread_count}</Text>
                </View>
              )}
            </View>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

// ---------------------------------------------------------------------------
// Thread view (WhatsApp-style)
// ---------------------------------------------------------------------------
function ThreadView({
  conversation,
  onBack,
}: {
  conversation: Conversation;
  onBack: () => void;
}) {
  const practitionerId = conversation.practitioner_id;
  const patientUsername = conversation.patient_username;
  const conversationId = conversation.conversation_id;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [otherTyping, setOtherTyping] = useState(false);
  const [optimisticMsgs, setOptimisticMsgs] = useState<ChatMessage[]>([]);

  const flatListRef = useRef<FlatList<ChatMessage>>(null);
  const typingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isTypingRef = useRef(false);

  const { onMessage, onTyping, onRead, sendMessage, sendTyping, markRead } =
    useChatSocket();

  // Load initial history.
  const loadHistory = useCallback(
    async (silent = false) => {
      if (!silent) setLoading(true);
      try {
        const { messages: msgs, hasMore: more } = await getMessages(
          practitionerId,
        );
        setMessages(msgs);
        setHasMore(more);
        setError(null);
        // Mark as read on open.
        void markConversationRead(practitionerId);
        markRead(practitionerId, patientUsername);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [practitionerId, patientUsername, markRead],
  );

  useEffect(() => {
    void loadHistory(false);
  }, [loadHistory]);

  // Live incoming messages from the socket.
  useEffect(() => {
    const unsub = onMessage((msg) => {
      if (msg.conversation_id !== conversationId) return;
      // Clear any optimistic placeholder for this body.
      setOptimisticMsgs((prev) =>
        prev.filter((m) => !(m.body === msg.body && m.sender === msg.sender)),
      );
      setMessages((prev) => {
        if (prev.some((m) => m.id === msg.id)) return prev;
        const next = [...prev, msg];
        return next;
      });
      // If the message is from the practitioner, mark read.
      if (msg.sender === "practitioner") {
        void markConversationRead(practitionerId);
        markRead(practitionerId, patientUsername);
      }
    });
    return unsub;
  }, [onMessage, conversationId, practitionerId, patientUsername, markRead]);

  // Typing indicators.
  useEffect(() => {
    const unsub = onTyping((data) => {
      if (data.conversation_id !== conversationId) return;
      if (data.sender === "practitioner") {
        setOtherTyping(data.is_typing);
      }
    });
    return unsub;
  }, [onTyping, conversationId]);

  // Read receipts — update read_at on messages the other party has read.
  useEffect(() => {
    const unsub = onRead((data) => {
      if (data.conversation_id !== conversationId) return;
      if (data.reader === "practitioner") {
        setMessages((prev) =>
          prev.map((m) =>
            m.sender === "patient" && m.read_at === null
              ? { ...m, read_at: new Date().toISOString() }
              : m,
          ),
        );
      }
    });
    return unsub;
  }, [onRead, conversationId]);

  // Clear typing indicator after a timeout.
  useEffect(() => {
    if (!otherTyping) return;
    const t = setTimeout(() => setOtherTyping(false), 4000);
    return () => clearTimeout(t);
  }, [otherTyping]);

  const handleLoadMore = useCallback(async () => {
    if (loadingMore || !hasMore || messages.length === 0) return;
    setLoadingMore(true);
    try {
      const oldestId = messages[0].id;
      const { messages: older, hasMore: more } = await getMessages(
        practitionerId,
        oldestId,
      );
      setMessages((prev) => [...older, ...prev]);
      setHasMore(more);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, hasMore, messages, practitionerId]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);

    // Stop typing indicator.
    if (isTypingRef.current) {
      sendTyping(practitionerId, patientUsername, false);
      isTypingRef.current = false;
    }

    // Optimistic echo.
    const tempId = -Date.now();
    const optimistic: ChatMessage = {
      id: tempId,
      conversation_id: conversationId,
      practitioner_id: practitionerId,
      patient_username: patientUsername,
      sender: "patient",
      body: text,
      created_at: new Date().toISOString(),
      read_at: null,
    };
    setOptimisticMsgs((prev) => [...prev, optimistic]);

    try {
      // Send via socket (primary) — the server persists + broadcasts.
      sendMessage(practitionerId, patientUsername, text);
      // Also hit REST as a reliable fallback to ensure persistence + get the
      // real server-assigned id. The socket handler dedupes by id.
      await apiSendMessage(practitionerId, text);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      // Remove the optimistic message on failure.
      setOptimisticMsgs((prev) => prev.filter((m) => m.id !== tempId));
      setInput(text);
    } finally {
      setSending(false);
    }
  }, [
    input,
    sending,
    practitionerId,
    patientUsername,
    conversationId,
    sendMessage,
    sendTyping,
  ]);

  const handleInputChange = useCallback(
    (text: string) => {
      setInput(text);
      // Typing indicator: emit on first keystroke, clear after 2s of silence.
      if (!isTypingRef.current && text.length > 0) {
        isTypingRef.current = true;
        sendTyping(practitionerId, patientUsername, true);
      }
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
      typingTimeoutRef.current = setTimeout(() => {
        if (isTypingRef.current) {
          sendTyping(practitionerId, patientUsername, false);
          isTypingRef.current = false;
        }
      }, 2000);
    },
    [practitionerId, patientUsername, sendTyping],
  );

  useEffect(() => {
    return () => {
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    };
  }, []);

  const allMessages = [...messages, ...optimisticMsgs];
  const practitionerName =
    conversation.practitioner?.full_name ??
    `Practitioner #${practitionerId}`;

  if (loading) {
    return (
      <View style={styles.flex}>
        <Pressable style={styles.backButton} onPress={onBack}>
          <Text style={styles.backButtonText}>{"< Back"}</Text>
        </Pressable>
        <View style={styles.centered}>
          <ActivityIndicator color="#6366f1" size="large" />
        </View>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      keyboardVerticalOffset={90}
    >
      {/* Thread header */}
      <View style={styles.threadHeader}>
        <Pressable style={styles.backButton} onPress={onBack}>
          <Text style={styles.backButtonText}>{"< Back"}</Text>
        </Pressable>
        <View style={styles.threadHeaderInfo}>
          <View style={styles.convAvatarSmall}>
            <Text style={styles.convAvatarTextSmall}>
              {practitionerName.charAt(0).toUpperCase()}
            </Text>
          </View>
          <View>
            <Text style={styles.threadHeaderName} numberOfLines={1}>
              {practitionerName}
            </Text>
            <Text style={styles.threadHeaderStatus}>
              {otherTyping ? "typing..." : "online"}
            </Text>
          </View>
        </View>
      </View>

      {error && (
        <Text style={[styles.errorText, { marginHorizontal: 16 }]}>
          {error}
        </Text>
      )}

      <FlatList
        ref={flatListRef}
        style={styles.flex}
        contentContainerStyle={{ padding: 12, paddingBottom: 8 }}
        data={allMessages}
        keyExtractor={(item) => String(item.id)}
        renderItem={({ item }) => <MessageBubble msg={item} />}
        onContentSizeChange={() => {
          if (allMessages.length > 0) {
            flatListRef.current?.scrollToEnd({ animated: false });
          }
        }}
        onLayout={() => {
          if (allMessages.length > 0) {
            flatListRef.current?.scrollToEnd({ animated: false });
          }
        }}
        ListHeaderComponent={
          hasMore ? (
            <Pressable
              style={styles.loadMoreButton}
              onPress={handleLoadMore}
              disabled={loadingMore}
            >
              {loadingMore ? (
                <ActivityIndicator color="#6366f1" size="small" />
              ) : (
                <Text style={styles.loadMoreText}>Load older messages</Text>
              )}
            </Pressable>
          ) : null
        }
        ListEmptyComponent={
          <View style={styles.emptyThread}>
            <Text style={styles.emptyText}>
              No messages yet. Say hello!
            </Text>
          </View>
        }
      />

      {/* Typing indicator bubble */}
      {otherTyping && (
        <View style={styles.typingBubbleWrap}>
          <View style={styles.typingBubble}>
            <Text style={styles.typingDots}>...</Text>
          </View>
        </View>
      )}

      {/* Input bar */}
      <View style={styles.inputBar}>
        <TextInput
          style={styles.inputField}
          placeholder="Type a message..."
          placeholderTextColor="#64748b"
          value={input}
          onChangeText={handleInputChange}
          multiline
          maxLength={4000}
          editable={!sending}
        />
        <Pressable
          style={[styles.sendButton, (!input.trim() || sending) && styles.sendButtonDisabled]}
          onPress={handleSend}
          disabled={!input.trim() || sending}
        >
          {sending ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.sendButtonText}>Send</Text>
          )}
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------------------
// Message bubble
// ---------------------------------------------------------------------------
function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isPatient = msg.sender === "patient";
  const isOptimistic = msg.id < 0;

  return (
    <View
      style={[
        styles.bubbleWrap,
        isPatient ? styles.bubbleWrapRight : styles.bubbleWrapLeft,
      ]}
    >
      <View
        style={[
          styles.bubble,
          isPatient ? styles.bubblePatient : styles.bubblePractitioner,
        ]}
      >
        <Text
          style={[
            styles.bubbleText,
            isPatient ? styles.bubbleTextPatient : styles.bubbleTextPractitioner,
          ]}
        >
          {msg.body}
        </Text>
      </View>
      <View style={styles.bubbleMetaRow}>
        <Text style={styles.bubbleTime}>{formatTime(msg.created_at)}</Text>
        {isPatient && !isOptimistic && (
          <Text style={styles.bubbleRead}>
            {msg.read_at ? "✓✓" : "✓"}
          </Text>
        )}
        {isPatient && isOptimistic && (
          <Text style={styles.bubblePending}>...</Text>
        )}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) {
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  flex: { flex: 1 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center" },
  scrollContent: { padding: 16, paddingBottom: 32 },
  header: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 12 },
  headerTitle: { fontSize: 22, fontWeight: "700", color: "#f8fafc" },
  errorText: { color: "#fca5a5", fontSize: 13, marginBottom: 8 },
  emptyText: { color: "#64748b", fontSize: 15, textAlign: "center", marginBottom: 8 },
  emptySubtext: { color: "#475569", fontSize: 13, textAlign: "center", paddingHorizontal: 24 },
  emptyState: { alignItems: "center", paddingTop: 60 },

  // Conversation list
  convCard: {
    backgroundColor: "#1e293b",
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
  },
  convRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  convAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#6366f1",
    justifyContent: "center",
    alignItems: "center",
  },
  convAvatarText: { color: "#fff", fontSize: 18, fontWeight: "700" },
  convAvatarSmall: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: "#6366f1",
    justifyContent: "center",
    alignItems: "center",
  },
  convAvatarTextSmall: { color: "#fff", fontSize: 14, fontWeight: "700" },
  convBody: { flex: 1 },
  convHeaderRow: { flexDirection: "row", justifyContent: "space-between", marginBottom: 2 },
  convName: { fontSize: 16, fontWeight: "600", color: "#f8fafc", flexShrink: 1 },
  convTime: { fontSize: 11, color: "#64748b" },
  convPreview: { fontSize: 13, color: "#94a3b8" },
  unreadBadge: {
    backgroundColor: "#6366f1",
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 6,
  },
  unreadText: { color: "#fff", fontSize: 11, fontWeight: "700" },

  // Thread header
  threadHeader: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "#1e293b",
    gap: 8,
  },
  threadHeaderInfo: { flexDirection: "row", alignItems: "center", gap: 10, flex: 1 },
  threadHeaderName: { fontSize: 16, fontWeight: "600", color: "#f8fafc" },
  threadHeaderStatus: { fontSize: 12, color: "#22c55e" },
  backButton: { paddingVertical: 4, paddingHorizontal: 4 },
  backButtonText: { color: "#6366f1", fontSize: 15, fontWeight: "600" },

  // Messages
  bubbleWrap: { marginBottom: 10, maxWidth: "80%" },
  bubbleWrapLeft: { alignSelf: "flex-start" },
  bubbleWrapRight: { alignSelf: "flex-end" },
  bubble: { borderRadius: 16, paddingHorizontal: 14, paddingVertical: 10 },
  bubblePatient: { backgroundColor: "#6366f1", borderBottomRightRadius: 4 },
  bubblePractitioner: { backgroundColor: "#1e293b", borderBottomLeftRadius: 4 },
  bubbleText: { fontSize: 15, lineHeight: 20 },
  bubbleTextPatient: { color: "#fff" },
  bubbleTextPractitioner: { color: "#e2e8f0" },
  bubbleMetaRow: { flexDirection: "row", gap: 6, marginTop: 3, paddingHorizontal: 4 },
  bubbleTime: { fontSize: 10, color: "#64748b" },
  bubbleRead: { fontSize: 10, color: "#6366f1" },
  bubblePending: { fontSize: 10, color: "#64748b" },

  // Load more
  loadMoreButton: { alignItems: "center", paddingVertical: 10, marginBottom: 8 },
  loadMoreText: { color: "#6366f1", fontSize: 13, fontWeight: "600" },

  // Empty thread
  emptyThread: { alignItems: "center", paddingTop: 80 },

  // Typing indicator
  typingBubbleWrap: { paddingHorizontal: 16, paddingBottom: 4 },
  typingBubble: {
    alignSelf: "flex-start",
    backgroundColor: "#1e293b",
    borderRadius: 16,
    borderBottomLeftRadius: 4,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  typingDots: { fontSize: 16, color: "#94a3b8", fontWeight: "700" },

  // Input bar
  inputBar: {
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderTopWidth: 1,
    borderTopColor: "#1e293b",
    backgroundColor: "#0f172a",
  },
  inputField: {
    flex: 1,
    backgroundColor: "#1e293b",
    color: "#f1f5f9",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 20,
    fontSize: 15,
    maxHeight: 100,
  },
  sendButton: {
    backgroundColor: "#6366f1",
    paddingHorizontal: 18,
    borderRadius: 20,
    justifyContent: "center",
    alignItems: "center",
  },
  sendButtonDisabled: { opacity: 0.5 },
  sendButtonText: { color: "#fff", fontSize: 15, fontWeight: "700" },
});
