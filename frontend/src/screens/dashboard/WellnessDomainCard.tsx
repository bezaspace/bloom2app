import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { BarChart } from "react-native-gifted-charts";
import {
  WELLNESS_DOMAINS,
  getRecentLogs,
  type LogEntry,
} from "../../dashboard";
import { EmptyState } from "./EmptyState";
import { ProgressRing } from "./ProgressRing";

interface WellnessDomainCardProps {
  domain: (typeof WELLNESS_DOMAINS)[number];
  /** Today's target value for the domain (e.g. workout_minutes: 30). */
  targetValue: number | undefined;
  /** Today's target label (e.g. "min", "meals", "sessions"). */
  targetLabel: string;
  /** Today's logged entries for this domain. */
  todayEntries: LogEntry[] | undefined;
  /** Called when the user logs a quick actual for today. */
  onQuickLog: (value: number) => void;
  /** Title shown on the card. */
  title: string;
  /** Emoji icon. */
  icon: string;
}

const DOMAIN_COLORS: Record<string, string> = {
  workout: "#22c55e",
  diet: "#f97316",
  medication: "#ec4899",
  mental_health: "#a855f7",
  meditation: "#06b6d4",
  other: "#64748b",
};

/** A wellness domain card: today's target + quick-log + 7-day bar chart. */
export function WellnessDomainCard({
  domain,
  targetValue,
  targetLabel,
  todayEntries,
  onQuickLog,
  title,
  icon,
}: WellnessDomainCardProps) {
  const [recent, setRecent] = useState<{ date: string; entries: LogEntry[] }[]>(
    [],
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getRecentLogs(domain, 7)
      .then((res) => {
        if (!cancelled && res.status === "success") setRecent(res.logs);
      })
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [domain, todayEntries]);

  // Sum today's actual value from entries.
  const todayActual = (todayEntries ?? []).reduce(
    (sum, e) => sum + (e.value ?? 0),
    0,
  );
  const target = targetValue ?? 0;
  const progress = target > 0 ? Math.min(1, todayActual / target) : 0;
  const color = DOMAIN_COLORS[domain] || DOMAIN_COLORS.other;

  // Build the last 7 days of bars (fill gaps with 0).
  const bars = buildSevenDayBars(recent, target, color);

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.icon}>{icon}</Text>
        <Text style={styles.title}>{title}</Text>
        {target > 0 ? (
          <View style={styles.targetPill}>
            <Text style={styles.targetPillText}>
              Target: {target} {targetLabel}
            </Text>
          </View>
        ) : null}
      </View>

      <View style={styles.bodyRow}>
        <ProgressRing
          progress={progress}
          size={64}
          label={target > 0 ? targetLabel : undefined}
        />
        <View style={styles.actualCol}>
          <Text style={styles.actualValue}>
            {todayActual} <Text style={styles.actualUnit}>{targetLabel}</Text>
          </Text>
          <Text style={styles.actualSub}>
            {target > 0
              ? `${Math.max(0, target - todayActual)} ${targetLabel} to go`
              : "Log today's activity"}
          </Text>
          <View style={styles.quickLogRow}>
            <Pressable
              style={styles.quickLogBtn}
              onPress={() => onQuickLog(Math.max(5, (targetValue ?? 15) / 3))}
            >
              <Text style={styles.quickLogText}>+ Quick log</Text>
            </Pressable>
          </View>
        </View>
      </View>

      {/* 7-day bar chart */}
      <View style={styles.chartWrap}>
        {loading ? (
          <Text style={styles.chartLoading}>Loading…</Text>
        ) : bars.length === 0 || bars.every((b) => b.value === 0) ? (
          <EmptyState
            message={`No ${title.toLowerCase()} logged this week.`}
            hint="Today's plan suggests a target above — tap + Quick log."
          />
        ) : (
          <BarChart
            data={bars}
            barWidth={22}
            spacing={14}
            roundedTop
            roundedBottom
            noOfSections={3}
            xAxisLabelTextStyle={styles.axisText}
            yAxisTextStyle={styles.axisText}
            yAxisColor="#475569"
            xAxisColor="#475569"
            rulesColor="#1e293b"
            isAnimated
            showLine={false}
            minHeight={110}
          />
        )}
      </View>
    </View>
  );
}

/** Build 7 day-bars ending today, filling gaps with 0. */
function buildSevenDayBars(
  recent: { date: string; entries: LogEntry[] }[],
  target: number,
  color: string,
): { value: number; label: string; frontColor: string }[] {
  const byDate = new Map<string, number>();
  for (const row of recent) {
    const sum = row.entries.reduce((s, e) => s + (e.value ?? 0), 0);
    byDate.set(row.date, sum);
  }
  const out: { value: number; label: string; frontColor: string }[] = [];
  const today = new Date();
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const iso = d.toISOString().slice(0, 10);
    const value = byDate.get(iso) ?? 0;
    const label = ["S", "M", "T", "W", "T", "F", "S"][d.getDay()];
    const isToday = i === 0;
    out.push({
      value,
      label,
      frontColor: isToday ? color : "#334155",
    });
  }
  return out;
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
    alignItems: "center",
    gap: 8,
    marginBottom: 12,
  },
  icon: { fontSize: 18 },
  title: { color: "#f8fafc", fontSize: 16, fontWeight: "700", flex: 1 },
  targetPill: {
    backgroundColor: "#0f172a",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  targetPillText: { color: "#cbd5e1", fontSize: 11, fontWeight: "600" },
  bodyRow: { flexDirection: "row", alignItems: "center", gap: 16, marginBottom: 12 },
  actualCol: { flex: 1 },
  actualValue: { color: "#f1f5f9", fontSize: 22, fontWeight: "700" },
  actualUnit: { color: "#94a3b8", fontSize: 13, fontWeight: "500" },
  actualSub: { color: "#64748b", fontSize: 12, marginTop: 2 },
  quickLogRow: { flexDirection: "row", gap: 8, marginTop: 8 },
  quickLogBtn: {
    backgroundColor: "#6366f1",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  quickLogText: { color: "#fff", fontSize: 12, fontWeight: "600" },
  chartWrap: {
    backgroundColor: "#0f172a",
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 10,
    alignItems: "center",
  },
  chartLoading: { color: "#64748b", fontSize: 12, paddingVertical: 20 },
  axisText: { color: "#64748b", fontSize: 10 },
});
