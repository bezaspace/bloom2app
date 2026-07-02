import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { LineChart } from "react-native-gifted-charts";
import { getRecentLogs, type LogEntry } from "../../dashboard";
import { EmptyState } from "./EmptyState";

interface MentalHealthCardProps {
  /** Today's logged entries for mental_health. */
  todayEntries: LogEntry[] | undefined;
  /** Called when the user picks a mood (1-5). */
  onLogMood: (mood: number) => void;
}

const MOOD_EMOJI = ["\u{1F622}", "\u{1F614}", "\u{1F610}", "\u{1F642}", "\u{1F600}"];
const MOOD_LABELS = ["Rough", "Low", "Okay", "Good", "Great"];

/** Mental-health card: daily mood check-in (1-5) + 7-day trend line. */
export function MentalHealthCard({ todayEntries, onLogMood }: MentalHealthCardProps) {
  const [recent, setRecent] = useState<{ date: string; entries: LogEntry[] }[]>(
    [],
  );
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getRecentLogs("mental_health", 7)
      .then((res) => {
        if (!cancelled && res.status === "success") setRecent(res.logs);
      })
      .catch(() => {})
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [todayEntries]);

  const todayMood = (todayEntries ?? []).find((e) => e.key === "mood")?.value;

  // Build 7-day trend line.
  const byDate = new Map<string, number>();
  for (const row of recent) {
    const mood = row.entries.find((e) => e.key === "mood")?.value;
    if (mood != null) byDate.set(row.date, mood);
  }
  const today = new Date();
  const points: { value: number; label: string; dataPointColor: string }[] = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const iso = d.toISOString().slice(0, 10);
    const value = byDate.get(iso);
    const label = ["S", "M", "T", "W", "T", "F", "S"][d.getDay()];
    if (value != null) {
      points.push({
        value,
        label,
        dataPointColor: i === 0 ? "#a855f7" : "#64748b",
      });
    }
  }

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.icon}>{"\u{1F9E0}"}</Text>
        <Text style={styles.title}>Mental Health</Text>
      </View>

      <Text style={styles.question}>How are you feeling today?</Text>
      <View style={styles.moodRow}>
        {MOOD_EMOJI.map((emoji, i) => {
          const selected = todayMood === i + 1;
          return (
            <Pressable
              key={i}
              style={[styles.moodBtn, selected && styles.moodBtnSelected]}
              onPress={() => onLogMood(i + 1)}
            >
              <Text style={styles.moodEmoji}>{emoji}</Text>
              <Text
                style={[styles.moodLabel, selected && styles.moodLabelSelected]}
              >
                {MOOD_LABELS[i]}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.chartWrap}>
        {loading ? (
          <Text style={styles.chartLoading}>Loading…</Text>
        ) : points.length === 0 ? (
          <EmptyState
            message="No mood check-ins yet this week."
            hint="Tap a face above to log today's mood."
          />
        ) : (
          <LineChart
            data={points}
            width={260}
            height={120}
            color="#a855f7"
            dataPointsRadius={4}
            thickness={2}
            curved
            isAnimated
            noOfSections={4}
            maxValue={5}
            yAxisTextStyle={styles.axisText}
            yAxisColor="#475569"
            xAxisColor="#475569"
            rulesColor="#1e293b"
            xAxisLabelTextStyle={styles.axisText}
            spacing={30}
          />
        )}
      </View>
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
    alignItems: "center",
    gap: 8,
    marginBottom: 12,
  },
  icon: { fontSize: 18 },
  title: { color: "#f8fafc", fontSize: 16, fontWeight: "700", flex: 1 },
  question: { color: "#cbd5e1", fontSize: 14, marginBottom: 10 },
  moodRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 14,
    gap: 4,
  },
  moodBtn: {
    flex: 1,
    alignItems: "center",
    backgroundColor: "#0f172a",
    borderRadius: 10,
    paddingVertical: 8,
    borderWidth: 2,
    borderColor: "transparent",
  },
  moodBtnSelected: { borderColor: "#a855f7" },
  moodEmoji: { fontSize: 22 },
  moodLabel: { color: "#64748b", fontSize: 10, marginTop: 4 },
  moodLabelSelected: { color: "#a855f7", fontWeight: "700" },
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
