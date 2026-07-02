import { Pressable, StyleSheet, Text, View } from "react-native";

interface PlanSummaryCardProps {
  summary: string | null | undefined;
  phase: string;
  dayOfPlan: number;
  phaseFocus: string | null | undefined;
  /** Called when the user taps "View full plan". */
  onViewFullPlan?: () => void;
}

/** Top-of-dashboard card showing the 90-day plan summary + current phase. */
export function PlanSummaryCard({
  summary,
  phase,
  dayOfPlan,
  phaseFocus,
  onViewFullPlan,
}: PlanSummaryCardProps) {
  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <Text style={styles.phase}>{phase || "Your 90-Day Plan"}</Text>
        <View style={styles.dayPill}>
          <Text style={styles.dayPillText}>
            Day {dayOfPlan} of 90
          </Text>
        </View>
      </View>
      {phaseFocus ? <Text style={styles.focus}>{phaseFocus}</Text> : null}
      {summary ? <Text style={styles.summary}>{summary}</Text> : null}
      {onViewFullPlan ? (
        <Pressable style={styles.viewButton} onPress={onViewFullPlan}>
          <Text style={styles.viewButtonText}>View full plan</Text>
        </Pressable>
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
    marginBottom: 8,
  },
  phase: { color: "#a5b4fc", fontSize: 16, fontWeight: "700", flexShrink: 1 },
  dayPill: {
    backgroundColor: "#0f172a",
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  dayPillText: { color: "#cbd5e1", fontSize: 12, fontWeight: "600" },
  focus: {
    color: "#e2e8f0",
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 8,
  },
  summary: {
    color: "#94a3b8",
    fontSize: 13,
    lineHeight: 19,
    marginBottom: 12,
  },
  viewButton: {
    backgroundColor: "#6366f1",
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 10,
    alignSelf: "flex-start",
  },
  viewButtonText: { color: "#fff", fontSize: 13, fontWeight: "600" },
});
