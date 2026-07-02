import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { login, register } from "../auth";

interface AuthScreenProps {
  onAuthenticated: () => void;
}

export function AuthScreen({ onAuthenticated }: AuthScreenProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [busy, setBusy] = useState(false);

  const handleAuth = async () => {
    setError(null);
    setBusy(true);
    try {
      if (mode === "login") {
        await login(username, password);
      } else {
        await register(username, password);
      }
      setUsername("");
      setPassword("");
      onAuthenticated();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
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
              value={username}
              onChangeText={setUsername}
              placeholder="Username"
              placeholderTextColor="#6b7280"
              autoCapitalize="none"
              autoCorrect={false}
            />
            <TextInput
              style={styles.authInput}
              value={password}
              onChangeText={setPassword}
              placeholder="Password"
              placeholderTextColor="#6b7280"
              secureTextEntry
            />

            {error && (
              <View style={styles.errorBar}>
                <Text style={styles.errorText}>{error}</Text>
              </View>
            )}

            <Pressable style={styles.connectButton} onPress={handleAuth}>
              {busy ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.connectButtonText}>
                  {mode === "login" ? "Sign in" : "Create account"}
                </Text>
              )}
            </Pressable>

            <Pressable
              style={styles.authSwitchButton}
              onPress={() => setMode(mode === "login" ? "register" : "login")}
            >
              <Text style={styles.authSwitchText}>
                {mode === "login"
                  ? "Need an account? Register"
                  : "Already have an account? Sign in"}
              </Text>
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  flex: { flex: 1 },
  authContainer: {
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: 28,
    paddingVertical: 24,
  },
  authForm: { marginTop: 36, gap: 16 },
  authInput: {
    backgroundColor: "#1e293b",
    color: "#f1f5f9",
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderRadius: 12,
    fontSize: 16,
  },
  errorBar: {
    backgroundColor: "#7f1d1d",
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
  },
  errorText: { color: "#fecaca", fontSize: 13 },
  connectButton: {
    backgroundColor: "#22c55e",
    paddingVertical: 14,
    borderRadius: 14,
    alignItems: "center",
  },
  connectButtonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  authSwitchButton: { alignItems: "center", paddingVertical: 8 },
  authSwitchText: { color: "#94a3b8", fontSize: 14 },
  title: { fontSize: 24, fontWeight: "700", color: "#f8fafc" },
  subtitle: { fontSize: 13, color: "#94a3b8", marginTop: 2 },
});
