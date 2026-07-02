import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { NavigationContainer } from "@react-navigation/native";
import { getToken } from "../auth";
import { AuthScreen } from "../screens/AuthScreen";
import { MainTabs } from "./MainTabs";

interface RootNavigatorProps {
  onLoggedOut: () => void;
}

/**
 * Root navigator: shows the Auth screen until a token is present, then shows
 * the MainTabs (Dashboard | Talk). The auth state is held here so the
 * AuthScreen can flip it after a successful login/register.
 */
export function RootNavigator({ onLoggedOut }: RootNavigatorProps) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    getToken().then((token) => {
      setIsAuthenticated(!!token);
      setChecking(false);
    });
  }, []);

  if (checking) {
    return (
      <SafeAreaProvider>
        <SafeAreaView style={styles.container}>
          <StatusBar style="light" />
          <View style={styles.centered}>
            <ActivityIndicator color="#fff" />
          </View>
        </SafeAreaView>
      </SafeAreaProvider>
    );
  }

  if (!isAuthenticated) {
    return (
      <SafeAreaProvider>
        <AuthScreen onAuthenticated={() => setIsAuthenticated(true)} />
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <NavigationContainer>
        <MainTabs
          onLogout={() => {
            setIsAuthenticated(false);
            onLoggedOut();
          }}
        />
      </NavigationContainer>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  centered: { flex: 1, justifyContent: "center", alignItems: "center" },
});
