import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { BarChart, LineChart } from "react-native-gifted-charts";
import {
  getRecentMetricLogs,
  logMetric,
  type LogEntry,
  type PlanMetric,
} from "../../dashboard";
import { EmptyState } from "./EmptyState";
import { ProgressRing } from "./ProgressRing";

interface MetricCardProps {
  metric: PlanMetric;
  /** Today's logged entries for this metric (from /logs/today). */
  todayEntries: LogEntry[] | undefined;
  /** Called after a quick-log to trigger a parent refresh. */
  onLogged?: () => void;
}

/** Template-based color mapping for visual consistency. */
const TEMPLATE_COLORS: Record<string, string> = {
  steps: "#22c55e",
  workout_minutes: "#22c55e",
  sleep_duration: "#3b82f6",
  sleep_quality: "#3b82f6",
  mood: "#a855f7",
  stress_level: "#ef4444",
  anxiety_level: "#ef4444",
  meditation_minutes: "#06b6d4",
  weight: "#f97316",
  blood_pressure_systolic: "#ec4899",
  blood_pressure_diastolic: "#ec4899",
  resting_heart_rate: "#ec4899",
  medication_adherence: "#eab308",
  meals_logged: "#f97316",
  carbs_per_meal: "#f97316",
  calories_per_meal: "#f97316",
  protein_per_meal: "#f97316",
  water_intake: "#06b6d4",
  caffeine_intake: "#a16207",
  alcohol_drinks: "#a16207",
  symptom_severity: "#64748b",
  therapy_homework: "#a855f7",
  screen_time: "#64748b",
  fasting_glucose: "#eab308",
};

/** Point-in-time metrics that take the last value rather than summing. */
const POINT_IN_TIME = new Set([
  "mood", "stress_level", "anxiety_level", "sleep_quality",
  "blood_pressure_systolic", "blood_pressure_diastolic",
  "resting_heart_rate", "weight", "symptom_severity",
]);

/** A metric card: today's target + quick-log + 7-day chart. */
export function MetricCard({ metric, todayEntries, onLogged }: MetricCardProps) {
  const [recent, setRecent] = useState<{ date: string; entries: LogEntry[] }[]>([]);
  const [loading, setLoading] = useState(true);
  const [logging, setLogging] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getRecentMetricLogs(metric.id, 7)
      .then((rows) => {
        if (!cancelled) setRecent(rows);
      })
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [metric.id, todayEntries]);

  const target = metric.target_value ?? 0;
  const targetHigh = metric.target_high ?? null;
  const isPointInTime = POINT_IN_TIME.has(metric.template_id);
  const isCount = metric.target_type === "count";
  const isRange = metric.target_type === "range";
  const isNone = metric.target_type === "none";

  // Compute today's actual.
  const todayActual = computeActual(metric, todayEntries ?? []);
  const adherence = computeAdherence(metric, todayActual);
  const progress = adherence ?? 0;
  const color = TEMPLATE_COLORS[metric.template_id] ?? "#64748b";
  const hasVoiceLog = (todayEntries ?? []).some((e) => e.note === "via voice");

  // Build chart data.
  const chartData = buildChartData(metric, recent, target, color);

  const handleQuickLog = async (value: number) => {
    setLogging(true);
    try {
      await logMetric(metric.id, value, undefined, true);
      onLogged?.();
    } catch (e) {
      console.warn("Quick log failed:", e);
    } finally {
      setLogging(false);
    }
  };

  const handleCheckOff = async () => {
    setLogging(true);
    try {
      await logMetric(metric.id, 1, undefined, true);
      onLogged?.();
    } catch (e) {
      console.warn("Check-off failed:", e);
    } finally {
      setLogging(false);
    }
  };

  // Determine the quick-log value.
  const quickLogValue = isCount ? 1 : Math.max(1, (target || 15) / 3);
  const showCheckOff = isCount || isNone;
  const showQuickLog = !showCheckOff && target > 0;

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>{metric.label}</Text>
        {hasVoiceLog ? (
          <View style={styles.voiceBadge}>
            <Text style={styles.voiceBadgeText}>{"\u{1F3A4}"} via voice</Text>
          </View>
        ) : null}
        {target > 0 && !isNone ? (
          <View style={styles.targetPill}>
            <Text style={styles.targetPillText}>
              {isRange
                ? `Target: ${target}–${targetHigh} ${metric.unit}`
                : metric.target_type === "maximum"
                ? `Limit: ${target} ${metric.unit}`
                : `Target: ${target} ${metric.unit}`}
            </Text>
          </View>
        ) : null}
      </View>

      <View style={styles.bodyRow}>
        {!isNone && target > 0 ? (
          <ProgressRing
            progress={progress}
            size={64}
            label={metric.unit}
          />
        ) : null}
        <View style={styles.actualCol}>
          <Text style={styles.actualValue}>
            {todayActual !== null ? formatValue(todayActual) : "—"}{" "}
            <Text style={styles.actualUnit}>{metric.unit}</Text>
          </Text>
          <Text style={styles.actualSub}>
            {isNone
              ? "Tap + to log"
              : target > 0 && todayActual !== null
              ? `${Math.max(0, target - todayActual).toFixed(0)} ${metric.unit} to go`
              : "Log today's value"}
          </Text>
          <View style={styles.quickLogRow}>
            {showQuickLog ? (
              <Pressable
                style={[styles.quickLogBtn, logging && styles.quickLogBtnDisabled]}
                onPress={() => void handleQuickLog(quickLogValue)}
                disabled={logging}
              >
                <Text style={styles.quickLogText}>+ Quick log</Text>
              </Pressable>
            ) : null}
            {showCheckOff ? (
              <Pressable
                style={[styles.quickLogBtn, logging && styles.quickLogBtnDisabled]}
                onPress={() => void handleCheckOff()}
                disabled={logging}
              >
                <Text style={styles.quickLogText}>+ Done</Text>
              </Pressable>
            ) : null}
          </View>
        </View>
      </View>

      {/* 7-day chart */}
      <View style={styles.chartWrap}>
        {loading ? (
          <Text style={styles.chartLoading}>Loading…</Text>
        ) : chartData.length === 0 || chartData.every((d) => d.value === 0) ? (
          <EmptyState
            message={`No ${metric.label.toLowerCase()} logged this week.`}
            hint="Tap + Quick log above to start tracking."
          />
        ) : isPointInTime ? (
          <LineChart
            data={chartData}
            color={color}
            thickness={2}
            dataPointsRadius={4}
            curved
            isAnimated
            yAxisTextStyle={styles.axisText}
            yAxisColor="#475569"
            xAxisColor="#475569"
            xAxisLabelTextStyle={styles.axisText}
            rulesColor="#1e293b"
            adjustToWidth
            height={110}
          />
        ) : (
          <BarChart
            data={chartData}
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

/** Compute the actual value for a metric from today's entries. */
function computeActual(metric: PlanMetric, entries: LogEntry[]): number | null {
  if (entries.length === 0) return null;
  if (metric.target_type === "count") {
    return entries.filter((e) => e.completed !== false).length;
  }
  if (POINT_IN_TIME.has(metric.template_id)) {
    // Take the last entry's value.
    for (let i = entries.length - 1; i >= 0; i--) {
      if (entries[i].value != null) return entries[i].value!;
    }
    return null;
  }
  // Sum completed entries.
  return entries.reduce((sum, e) => sum + (e.completed !== false ? e.value ?? 0 : 0), 0);
}

/** Compute adherence as a 0..1 fraction. */
function computeAdherence(metric: PlanMetric, actual: number | null): number | null {
  if (actual === null) return null;
  const target = metric.target_value;
  const targetHigh = metric.target_high;
  if (metric.target_type === "none") return null;
  if (metric.target_type === "range") {
    if (target == null || targetHigh == null) return null;
    return target <= actual && actual <= targetHigh ? 1 : 0;
  }
  if (metric.target_type === "exact") {
    if (target == null) return null;
    return Math.abs(actual - target) < 1e-9 ? 1 : 0;
  }
  if (target == null || target === 0) return null;
  if (metric.target_type === "maximum") {
    return actual <= target ? 1 : target / actual;
  }
  // minimum, count, target
  return Math.min(1, actual / target);
}

/** Build 7-day chart data ending today, filling gaps with 0. */
function buildChartData(
  metric: PlanMetric,
  recent: { date: string; entries: LogEntry[] }[],
  target: number,
  color: string,
): { value: number; label: string; frontColor: string }[] {
  const byDate = new Map<string, number>();
  for (const row of recent) {
    const actual = computeActual(metric, row.entries);
    if (actual !== null) byDate.set(row.date, actual);
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

function formatValue(v: number): string {
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(2).replace(/\.?0+$/, "");
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
  title: { color: "#f8fafc", fontSize: 16, fontWeight: "700", flex: 1 },
  targetPill: {
    backgroundColor: "#0f172a",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  targetPillText: { color: "#cbd5e1", fontSize: 11, fontWeight: "600" },
  voiceBadge: {
    backgroundColor: "#312e81",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
    marginRight: -4,
  },
  voiceBadgeText: { color: "#a5b4fc", fontSize: 10, fontWeight: "600" },
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
  quickLogBtnDisabled: { opacity: 0.6 },
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
