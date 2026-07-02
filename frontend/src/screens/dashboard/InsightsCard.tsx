import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import {
  getTrendAlerts,
  getWeeklyReport,
  type TrendAlert,
  type WeeklyReport,
} from "../../dashboard";

/** A card showing AI-generated insights: weekly report + trend alerts.
 * Fetches on mount and on manual refresh. */
export function InsightsCard() {
  const [report, setReport] = useState<WeeklyReport | null>(null);
  const [alerts, setAlerts] = useState<TrendAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const [r, a] = await Promise.all([
        getWeeklyReport().catch(() => null),
        getTrendAlerts().catch(() => []),
      ]);
      setReport(r);
      setAlerts(a);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    void load(true);
  };

  if (loading) {
    return (
      <View style={styles.card}>
        <Text style={styles.title}>{"\u{1F4AC}"} AI Insights</Text>
        <Text style={styles.loading}>Loading insights…</Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>{"\u{1F4AC}"} AI Insights</Text>
        <Pressable
          style={[styles.refreshBtn, refreshing && styles.refreshBtnDisabled]}
          onPress={handleRefresh}
          disabled={refreshing}
        >
          <Text style={styles.refreshText}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </Text>
        </Pressable>
      </View>

      {error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : null}

      {/* Weekly report */}
      {report ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>This Week's Summary</Text>
          <Text style={styles.narrative}>{report.narrative}</Text>
          {report.highlights.length > 0 ? (
            <View style={styles.listWrap}>
              {report.highlights.map((h, i) => (
                <View key={`h${i}`} style={styles.listItem}>
                  <Text style={styles.highlightDot}>{"\u2705"}</Text>
                  <Text style={styles.listText}>{h}</Text>
                </View>
              ))}
            </View>
          ) : null}
          {report.concerns.length > 0 ? (
            <View style={styles.listWrap}>
              {report.concerns.map((c, i) => (
                <View key={`c${i}`} style={styles.listItem}>
                  <Text style={styles.concernDot}>{"\u26A0\uFE0F"}</Text>
                  <Text style={styles.listText}>{c}</Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}

      {/* Trend alerts */}
      {alerts.length > 0 ? (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Trend Alerts</Text>
          {alerts.map((a, i) => (
            <View
              key={`a${i}`}
              style={[
                styles.alertRow,
                a.severity === "critical"
                  ? styles.alertCritical
                  : a.severity === "warning"
                  ? styles.alertWarning
                  : styles.alertInfo,
              ]}
            >
              <Text style={styles.alertMetric}>{a.metric}</Text>
              <Text style={styles.alertMessage}>{a.message}</Text>
              <Text
                style={[
                  styles.alertBadge,
                  a.severity === "critical"
                    ? styles.alertBadgeCritical
                    : a.severity === "warning"
                    ? styles.alertBadgeWarning
                    : styles.alertBadgeInfo,
                ]}
              >
                {a.severity}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {!report && alerts.length === 0 && !error ? (
        <Text style={styles.emptyText}>
          No insights yet. Log a few days of data and tap Refresh.
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#1e293b",
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 12,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 10,
  },
  title: { color: "#f8fafc", fontSize: 16, fontWeight: "700" },
  refreshBtn: {
    backgroundColor: "#0f172a",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 10,
  },
  refreshBtnDisabled: { opacity: 0.6 },
  refreshText: { color: "#a5b4fc", fontSize: 12, fontWeight: "600" },
  loading: { color: "#64748b", fontSize: 13, paddingVertical: 20, textAlign: "center" },
  errorText: { color: "#ef4444", fontSize: 13, marginBottom: 8 },
  section: { marginBottom: 12 },
  sectionTitle: {
    color: "#94a3b8",
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  narrative: {
    color: "#cbd5e1",
    fontSize: 13,
    lineHeight: 19,
    marginBottom: 8,
  },
  listWrap: { gap: 4, marginTop: 6 },
  listItem: { flexDirection: "row", gap: 8, alignItems: "flex-start" },
  highlightDot: { fontSize: 13 },
  concernDot: { fontSize: 13 },
  listText: { color: "#e2e8f0", fontSize: 13, flex: 1, lineHeight: 18 },
  alertRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderRadius: 8,
    marginBottom: 6,
  },
  alertCritical: { backgroundColor: "rgba(239,68,68,0.1)" },
  alertWarning: { backgroundColor: "rgba(249,115,22,0.1)" },
  alertInfo: { backgroundColor: "rgba(99,102,241,0.1)" },
  alertMetric: { color: "#e2e8f0", fontSize: 13, fontWeight: "600" },
  alertMessage: { color: "#94a3b8", fontSize: 12, flex: 1 },
  alertBadge: {
    fontSize: 10,
    fontWeight: "700",
    textTransform: "uppercase",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
    overflow: "hidden",
  },
  alertBadgeCritical: { backgroundColor: "#ef4444", color: "#fff" },
  alertBadgeWarning: { backgroundColor: "#f97316", color: "#fff" },
  alertBadgeInfo: { backgroundColor: "#6366f1", color: "#fff" },
  emptyText: { color: "#64748b", fontSize: 13, paddingVertical: 12, textAlign: "center" },
});
