import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
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
import * as DocumentPicker from "expo-document-picker";
import { useVoiceAssistant } from "./src/useVoiceAssistant";
import type { ConnectionStatus } from "./src/useVoiceAssistant";
import { getToken, login, logout, register } from "./src/auth";
import {
  getOnboardingStatus,
  uploadDocument,
  SUPPORTED_DOC_TYPES,
} from "./src/onboarding";
import type { OnboardingStatus, WellnessPlan } from "./src/onboarding";

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

  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authChecking, setAuthChecking] = useState(true);
  const [authUsername, setAuthUsername] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");

  const isConnected = status === "connected";

  // Onboarding state
  const [onboardingStatus, setOnboardingStatus] =
    useState<OnboardingStatus | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const [showPlan, setShowPlan] = useState(false);

  useEffect(() => {
    getToken().then((token) => {
      setIsAuthenticated(!!token);
      setAuthChecking(false);
    });
  }, []);

  // Fetch onboarding status when connected, and poll while not yet onboarded
  // so the plan appears automatically after the agent finalizes onboarding.
  const refreshOnboarding = useCallback(async () => {
    try {
      const status = await getOnboardingStatus();
      setOnboardingStatus(status);
    } catch (e) {
      console.warn("Failed to fetch onboarding status:", e);
    }
  }, []);

  useEffect(() => {
    if (!isConnected) {
      setOnboardingStatus(null);
      return;
    }
    // Fetch immediately on connect.
    void refreshOnboarding();
    // Poll every 5 seconds while connected and not onboarded.
    const interval = setInterval(() => {
      void refreshOnboarding();
    }, 5000);
    return () => clearInterval(interval);
  }, [isConnected, refreshOnboarding]);

  const handleUploadDoc = useCallback(async () => {
    setUploadMsg(null);
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: SUPPORTED_DOC_TYPES,
        copyToCacheDirectory: true,
        multiple: false,
      });
      if (result.canceled || !result.assets || result.assets.length === 0) {
        return; // User cancelled the picker
      }
      setUploading(true);
      const asset = result.assets[0];
      const response = await uploadDocument({
        uri: asset.uri,
        name: asset.name,
        mimeType: asset.mimeType,
        file: asset.file,
        base64: asset.base64,
      });
      if (response.status === "success") {
        setUploadMsg(`Uploaded "${response.filename}" — processed successfully.`);
        void refreshOnboarding();
      } else {
        setUploadMsg(response.message || "Upload failed.");
      }
    } catch (e) {
      setUploadMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }, [refreshOnboarding]);

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

  const handleAuth = async () => {
    setAuthError(null);
    try {
      if (authMode === "login") {
        await login(authUsername, authPassword);
      } else {
        await register(authUsername, authPassword);
      }
      setIsAuthenticated(true);
      setAuthUsername("");
      setAuthPassword("");
    } catch (e) {
      setAuthError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleLogout = async () => {
    disconnect();
    await logout();
    setIsAuthenticated(false);
  };

  if (authChecking) {
    return (
      <SafeAreaProvider>
        <SafeAreaView style={[styles.container, styles.centered]}>
          <StatusBar style="light" />
          <ActivityIndicator color="#fff" />
        </SafeAreaView>
      </SafeAreaProvider>
    );
  }

  if (!isAuthenticated) {
    return (
      <SafeAreaProvider>
        <SafeAreaView style={styles.container}>
          <StatusBar style="light" />
          <KeyboardAvoidingView
            style={styles.flex}
            behavior={Platform.OS === "ios" ? "padding" : undefined}
          >
            <View style={styles.authContainer}>
              <Text style={styles.title}>Bloom</Text>
              <Text style={styles.subtitle}>Sign in to talk with Bloom</Text>

              <View style={styles.authForm}>
                <TextInput
                  style={styles.authInput}
                  value={authUsername}
                  onChangeText={setAuthUsername}
                  placeholder="Username"
                  placeholderTextColor="#6b7280"
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                <TextInput
                  style={styles.authInput}
                  value={authPassword}
                  onChangeText={setAuthPassword}
                  placeholder="Password"
                  placeholderTextColor="#6b7280"
                  secureTextEntry
                />

                {authError && (
                  <View style={styles.errorBar}>
                    <Text style={styles.errorText}>{authError}</Text>
                  </View>
                )}

                <Pressable style={styles.connectButton} onPress={handleAuth}>
                  <Text style={styles.connectButtonText}>
                    {authMode === "login" ? "Sign in" : "Create account"}
                  </Text>
                </Pressable>

                <Pressable
                  style={styles.authSwitchButton}
                  onPress={() =>
                    setAuthMode(authMode === "login" ? "register" : "login")
                  }
                >
                  <Text style={styles.authSwitchText}>
                    {authMode === "login"
                      ? "Need an account? Register"
                      : "Already have an account? Sign in"}
                  </Text>
                </Pressable>
              </View>
            </View>
          </KeyboardAvoidingView>
        </SafeAreaView>
      </SafeAreaProvider>
    );
  }

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
            <View style={styles.headerRight}>
              <Pressable style={styles.logoutButton} onPress={handleLogout}>
                <Text style={styles.logoutButtonText}>Logout</Text>
              </Pressable>
              <View style={styles.statusPill}>
                <View
                  style={[
                    styles.statusDot,
                    { backgroundColor: STATUS_COLORS[status] },
                  ]}
                />
                <Text style={styles.statusText}>{STATUS_LABELS[status]}</Text>
              </View>
            </View>
          </View>

          {/* Onboarding banner + upload controls */}
          {isConnected && onboardingStatus && !onboardingStatus.onboarded && (
            <View style={styles.onboardingBanner}>
              <Text style={styles.onboardingBannerTitle}>
                Welcome! Bloom will guide your onboarding.
              </Text>
              <Text style={styles.onboardingBannerText}>
                Tap the mic and talk to Bloom. After a few questions, you can
                upload health documents (optional) to personalize your plan.
              </Text>
              <View style={styles.uploadRow}>
                <Pressable
                  style={[
                    styles.uploadButton,
                    uploading && styles.uploadButtonDisabled,
                  ]}
                  onPress={handleUploadDoc}
                  disabled={uploading}
                >
                  {uploading ? (
                    <ActivityIndicator color="#fff" size="small" />
                  ) : (
                    <Text style={styles.uploadButtonText}>
                      📎 Upload Document
                    </Text>
                  )}
                </Pressable>
              </View>
              {uploadMsg && (
                <Text style={styles.uploadMsg}>{uploadMsg}</Text>
              )}
            </View>
          )}

          {/* Onboarded: show plan button */}
          {isConnected && onboardingStatus && onboardingStatus.onboarded && (
            <Pressable
              style={styles.planButton}
              onPress={() => setShowPlan(true)}
            >
              <Text style={styles.planButtonText}>📋 View My 90-Day Plan</Text>
            </Pressable>
          )}

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
                  entry.role === "user"
                    ? styles.bubbleUser
                    : styles.bubbleAssistant,
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
                style={[
                  styles.sendButton,
                  !textInput.trim() && styles.sendButtonDisabled,
                ]}
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
                    {isSpeaking
                      ? "Speaking…"
                      : isListening
                        ? "Listening…"
                        : "Talk"}
                  </Text>
                </Pressable>
              </View>
            )}
          </View>

          {/* My Plan modal */}
          <Modal
            visible={showPlan}
            animationType="slide"
            onRequestClose={() => setShowPlan(false)}
          >
            <SafeAreaView style={styles.container}>
              <View style={styles.planModalHeader}>
                <Text style={styles.planModalTitle}>My 90-Day Wellness Plan</Text>
                <Pressable
                  style={styles.planModalClose}
                  onPress={() => setShowPlan(false)}
                >
                  <Text style={styles.planModalCloseText}>Close</Text>
                </Pressable>
              </View>
              <ScrollView
                style={styles.planModalBody}
                contentContainerStyle={styles.planModalBodyContent}
              >
                {onboardingStatus?.plan ? (
                  <PlanView plan={onboardingStatus.plan} />
                ) : (
                  <Text style={styles.emptyHint}>
                    Your plan will appear here after onboarding.
                  </Text>
                )}
                {onboardingStatus?.doc_summary &&
                  onboardingStatus.doc_summary.free_text_summary && (
                    <View style={styles.docSummarySection}>
                      <Text style={styles.docSummaryTitle}>
                        From your documents:
                      </Text>
                      <Text style={styles.docSummaryText}>
                        {onboardingStatus.doc_summary.free_text_summary}
                      </Text>
                    </View>
                  )}
              </ScrollView>
            </SafeAreaView>
          </Modal>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

/** Renders the 90-day wellness plan with its phases. */
function PlanView({ plan }: { plan: WellnessPlan }) {
  return (
    <View>
      <Text style={styles.planSummary}>{plan.summary}</Text>
      {plan.phases.map((phase, i) => (
        <View key={i} style={styles.planPhase}>
          <Text style={styles.planPhaseName}>{phase.name}</Text>
          <Text style={styles.planPhaseFocus}>{phase.focus}</Text>
          {phase.actions.map((action, j) => (
            <Text key={j} style={styles.planPhaseAction}>
              {"\u2022"} {action}
            </Text>
          ))}
        </View>
      ))}
      {plan.weekly_rhythm && (
        <View style={styles.planWeeklyRhythm}>
          <Text style={styles.planPhaseName}>Weekly Rhythm</Text>
          <Text style={styles.planPhaseFocus}>{plan.weekly_rhythm}</Text>
        </View>
      )}
    </View>
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
  centered: {
    justifyContent: "center",
    alignItems: "center",
  },
  authContainer: {
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: 28,
    paddingVertical: 24,
  },
  authForm: {
    marginTop: 36,
    gap: 16,
  },
  authInput: {
    backgroundColor: "#1e293b",
    color: "#f1f5f9",
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderRadius: 12,
    fontSize: 16,
  },
  authSwitchButton: {
    alignItems: "center",
    paddingVertical: 8,
  },
  authSwitchText: {
    color: "#94a3b8",
    fontSize: 14,
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  logoutButton: {
    backgroundColor: "#1e293b",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 10,
  },
  logoutButtonText: {
    color: "#94a3b8",
    fontSize: 12,
    fontWeight: "600",
  },
  // ---- Onboarding banner + upload ----
  onboardingBanner: {
    backgroundColor: "#1e293b",
    marginHorizontal: 16,
    marginTop: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderRadius: 14,
  },
  onboardingBannerTitle: {
    color: "#f1f5f9",
    fontSize: 15,
    fontWeight: "700",
    marginBottom: 6,
  },
  onboardingBannerText: {
    color: "#94a3b8",
    fontSize: 13,
    lineHeight: 19,
    marginBottom: 12,
  },
  uploadRow: {
    flexDirection: "row",
    gap: 10,
  },
  uploadButton: {
    backgroundColor: "#6366f1",
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 10,
    alignItems: "center",
    flex: 1,
  },
  uploadButtonDisabled: {
    backgroundColor: "#475569",
  },
  uploadButtonText: {
    color: "#fff",
    fontSize: 14,
    fontWeight: "600",
  },
  uploadMsg: {
    color: "#a5b4fc",
    fontSize: 12,
    marginTop: 8,
  },
  // ---- Plan button ----
  planButton: {
    backgroundColor: "#6366f1",
    marginHorizontal: 16,
    marginTop: 12,
    paddingVertical: 10,
    borderRadius: 10,
    alignItems: "center",
  },
  planButtonText: {
    color: "#fff",
    fontSize: 14,
    fontWeight: "600",
  },
  // ---- Plan modal ----
  planModalHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: "#1e293b",
  },
  planModalTitle: {
    fontSize: 20,
    fontWeight: "700",
    color: "#f8fafc",
  },
  planModalClose: {
    backgroundColor: "#1e293b",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 10,
  },
  planModalCloseText: {
    color: "#94a3b8",
    fontWeight: "600",
  },
  planModalBody: {
    flex: 1,
    paddingHorizontal: 20,
  },
  planModalBodyContent: {
    paddingVertical: 20,
  },
  planSummary: {
    color: "#e2e8f0",
    fontSize: 15,
    lineHeight: 22,
    marginBottom: 20,
  },
  planPhase: {
    backgroundColor: "#1e293b",
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 12,
  },
  planPhaseName: {
    color: "#a5b4fc",
    fontSize: 16,
    fontWeight: "700",
    marginBottom: 6,
  },
  planPhaseFocus: {
    color: "#cbd5e1",
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 8,
  },
  planPhaseAction: {
    color: "#94a3b8",
    fontSize: 13,
    lineHeight: 19,
    marginLeft: 4,
  },
  planWeeklyRhythm: {
    backgroundColor: "#1e293b",
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 12,
  },
  docSummarySection: {
    marginTop: 16,
    backgroundColor: "#1e293b",
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  docSummaryTitle: {
    color: "#a5b4fc",
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 6,
  },
  docSummaryText: {
    color: "#cbd5e1",
    fontSize: 13,
    lineHeight: 19,
  },
});
