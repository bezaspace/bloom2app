import { StyleSheet, Text, View } from "react-native";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { DashboardScreen } from "../screens/DashboardScreen";
import { VoiceAssistantScreen } from "../screens/VoiceAssistantScreen";
import { PractitionersScreen } from "../screens/PractitionersScreen";

export type MainTabsParamList = {
  Dashboard: undefined;
  Talk: undefined;
  Practitioners: undefined;
};

const Tab = createBottomTabNavigator<MainTabsParamList>();

interface MainTabsProps {
  onLogout: () => void;
}

/** Bottom tab navigator: Dashboard | Talk | Practitioners. */
export function MainTabs({ onLogout }: MainTabsProps) {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: styles.tabBar,
        tabBarActiveTintColor: "#6366f1",
        tabBarInactiveTintColor: "#64748b",
        tabBarLabelStyle: styles.tabBarLabel,
      }}
    >
      <Tab.Screen
        name="Dashboard"
        options={{
          tabBarLabel: "Dashboard",
          tabBarIcon: ({ color, size }) => (
            <TabIcon color={color} size={size} label={"\u{1F4CA}"} />
          ),
        }}
      >
        {({ navigation }) => (
          <DashboardScreen onGoToTalk={() => navigation.navigate("Talk")} />
        )}
      </Tab.Screen>
      <Tab.Screen
        name="Talk"
        options={{
          tabBarLabel: "Talk",
          tabBarIcon: ({ color, size }) => (
            <TabIcon color={color} size={size} label={"\u{1F3A4}"} />
          ),
        }}
      >
        {() => <VoiceAssistantScreen onLogout={onLogout} />}
      </Tab.Screen>
      <Tab.Screen
        name="Practitioners"
        options={{
          tabBarLabel: "Practitioners",
          tabBarIcon: ({ color, size }) => (
            <TabIcon color={color} size={size} label={"\u{1F465}"} />
          ),
        }}
      >
        {() => <PractitionersScreen />}
      </Tab.Screen>
    </Tab.Navigator>
  );
}

/** A simple emoji-based tab icon (avoids needing an icon font dependency). */
function TabIcon({ color, size, label }: { color: string; size: number; label: string }) {
  return (
    <View style={styles.iconWrap}>
      <Text
        style={[styles.iconEmoji, { fontSize: size, opacity: color === "#64748b" ? 0.6 : 1 }]}
      >
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: "#0f172a",
    borderTopColor: "#1e293b",
    borderTopWidth: 1,
    height: 60,
    paddingBottom: 6,
    paddingTop: 6,
  },
  tabBarLabel: { fontSize: 11, fontWeight: "600" },
  iconWrap: { alignItems: "center", justifyContent: "center" },
  iconEmoji: {},
});
