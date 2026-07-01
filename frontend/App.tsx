import { useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { useVoiceAssistant } from "./src/useVoiceAssistant";
import type { ConnectionStatus } from "./src/useVoiceAssistant";

const STATUS_COLORS: Record<ConnectionStatus, string> = {
  disconnected: "#ef4444",
  connecting: "#f59e0b",
  connected: "#22c55e",
};

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  disconnected: "Disconnected",
  connecting: "Connecting…",
  connected: "Connected",
};

export default function App() {
  const {
    status,
    isSpeaking,
    isListening,
    transcript,
    error,
    connect,
    disconnect,
    startTalking,
    stopTalking,
    sendText,
  } = useVoiceAssistant();

  const [textInput, setTextInput] = useState("");
  const scrollRef = useRef<ScrollView>(null);

  const isConnected = status === "connected";

  const handleMicPress = async () => {
    if (isListening) {
      await stopTalking();
    } else {
      await startTalking();
    }
  };

  const handleSendText = () => {
    const text = textInput.trim();
    if (!text || !isConnected) return;
    sendText(text);
    setTextInput("");
  };

  return (
    <SafeAreaProvider>
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.title}>Bloom</Text>
            <Text style={styles.subtitle}>your voice companion</Text>
          </View>
          <View style={styles.statusPill}>
            <View
              style={[styles.statusDot, { backgroundColor: STATUS_COLORS[status] }]}
            />
            <Text style={styles.statusText}>{STATUS_LABELS[status]}</Text>
          </View>
        </View>

        {/* Transcript */}
        <ScrollView
          ref={scrollRef}
          style={styles.transcript}
          contentContainerStyle={styles.transcriptContent}
          onContentSizeChange={() =>
            scrollRef.current?.scrollToEnd({ animated: true })
          }
        >
          {transcript.length === 0 && (
            <Text style={styles.emptyHint}>
              {isConnected
                ? "Tap the mic and start talking, or type a message below."
                : "Connect to start a conversation with Bloom."}
            </Text>
          )}
          {transcript.map((entry) => (
            <View
              key={entry.id}
              style={[
                styles.bubble,
                entry.role === "user" ? styles.bubbleUser : styles.bubbleAssistant,
              ]}
            >
              <Text style={styles.bubbleText}>{entry.text}</Text>
              {entry.partial && <Text style={styles.cursor}>▍</Text>}
            </View>
          ))}
        </ScrollView>

        {/* Error */}
        {error && (
          <View style={styles.errorBar}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {/* Text input */}
        {isConnected && (
          <View style={styles.textInputRow}>
            <TextInput
              style={styles.textInput}
              value={textInput}
              onChangeText={setTextInput}
              placeholder="Type a message…"
              placeholderTextColor="#6b7280"
              onSubmitEditing={handleSendText}
              editable={isConnected}
            />
            <Pressable
              style={[styles.sendButton, !textInput.trim() && styles.sendButtonDisabled]}
              onPress={handleSendText}
              disabled={!textInput.trim()}
            >
              <Text style={styles.sendButtonText}>Send</Text>
            </Pressable>
          </View>
        )}

        {/* Controls */}
        <View style={styles.controls}>
          {!isConnected ? (
            <Pressable style={styles.connectButton} onPress={connect}>
              {status === "connecting" ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.connectButtonText}>Connect</Text>
              )}
            </Pressable>
          ) : (
            <View style={styles.connectedControls}>
              <Pressable style={styles.disconnectButton} onPress={disconnect}>
                <Text style={styles.disconnectButtonText}>Disconnect</Text>
              </Pressable>
              <Pressable
                style={[
                  styles.micButton,
                  isListening && styles.micButtonActive,
                ]}
                onPress={handleMicPress}
              >
                <Text style={styles.micIcon}>{isListening ? "⏹" : "🎤"}</Text>
                <Text style={styles.micLabel}>
                  {isSpeaking ? "Speaking…" : isListening ? "Listening…" : "Talk"}
                </Text>
              </Pressable>
            </View>
          )}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#0f172a",
  },
  flex: {
    flex: 1,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: "#1e293b",
  },
  title: {
    fontSize: 24,
    fontWeight: "700",
    color: "#f8fafc",
  },
  subtitle: {
    fontSize: 13,
    color: "#94a3b8",
    marginTop: 2,
  },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#1e293b",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  statusText: {
    fontSize: 12,
    color: "#cbd5e1",
    fontWeight: "500",
  },
  transcript: {
    flex: 1,
    paddingHorizontal: 16,
  },
  transcriptContent: {
    paddingVertical: 16,
  },
  emptyHint: {
    color: "#64748b",
    textAlign: "center",
    marginTop: 60,
    fontSize: 15,
    paddingHorizontal: 30,
  },
  bubble: {
    maxWidth: "85%",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 16,
    marginBottom: 10,
  },
  bubbleUser: {
    alignSelf: "flex-end",
    backgroundColor: "#3b82f6",
  },
  bubbleAssistant: {
    alignSelf: "flex-start",
    backgroundColor: "#1e293b",
  },
  bubbleText: {
    color: "#f1f5f9",
    fontSize: 15,
    lineHeight: 21,
  },
  cursor: {
    color: "#94a3b8",
    fontSize: 15,
  },
  errorBar: {
    backgroundColor: "#7f1d1d",
    paddingHorizontal: 16,
    paddingVertical: 8,
    marginHorizontal: 16,
    marginBottom: 8,
    borderRadius: 8,
  },
  errorText: {
    color: "#fecaca",
    fontSize: 13,
  },
  textInputRow: {
    flexDirection: "row",
    paddingHorizontal: 16,
    paddingVertical: 8,
    gap: 8,
  },
  textInput: {
    flex: 1,
    backgroundColor: "#1e293b",
    color: "#f1f5f9",
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 12,
    fontSize: 15,
  },
  sendButton: {
    backgroundColor: "#3b82f6",
    paddingHorizontal: 16,
    justifyContent: "center",
    borderRadius: 12,
  },
  sendButtonDisabled: {
    backgroundColor: "#1e293b",
  },
  sendButtonText: {
    color: "#fff",
    fontWeight: "600",
  },
  controls: {
    paddingHorizontal: 20,
    paddingVertical: 16,
    paddingBottom: 28,
  },
  connectButton: {
    backgroundColor: "#22c55e",
    paddingVertical: 14,
    borderRadius: 14,
    alignItems: "center",
  },
  connectButtonText: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },
  connectedControls: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  disconnectButton: {
    backgroundColor: "#1e293b",
    paddingHorizontal: 18,
    paddingVertical: 14,
    borderRadius: 14,
  },
  disconnectButtonText: {
    color: "#94a3b8",
    fontWeight: "600",
  },
  micButton: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    backgroundColor: "#3b82f6",
    paddingVertical: 14,
    borderRadius: 14,
  },
  micButtonActive: {
    backgroundColor: "#ef4444",
  },
  micIcon: {
    fontSize: 20,
  },
  micLabel: {
    color: "#fff",
    fontSize: 16,
    fontWeight: "700",
  },
});
