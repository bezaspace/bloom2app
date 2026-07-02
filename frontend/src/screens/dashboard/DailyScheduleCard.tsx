import { Pressable, StyleSheet, Text, View } from "react-native";
import type { ScheduleItem, LogEntry } from "../../dashboard";

interface DailyScheduleCardProps {
  focusToday: string;
  motivationNote: string;
  items: ScheduleItem[];
  /** Today's logs keyed by domain — used to show check-off state. */
  logs: Record<string, LogEntry[]>;
  /** Called when the user toggles a schedule item's completion. */
  onToggleItem: (item: ScheduleItem, completed: boolean) => void;
}

const DOMAIN_EMOJI: Record<string, string> = {
  workout: "\u{1F3CB}",
  diet: "\u{1F969}",
  medication: "\u{1F48A}",
  mental_health: "\u{1F9E0}",
  meditation: "\u{1F9D8}",
  other: "\u{2728}",
};

/** The timeline of today's AI-generated schedule with check-off toggles. */
export function DailyScheduleCard({
  focusToday,
  motivationNote,
  items,
  logs,
  onToggleItem,
}: DailyScheduleCardProps) {
  // Build a quick lookup of which item titles are checked off.
  const completedKeys = new Set<string>();
  for (const entries of Object.values(logs)) {
    for (const e of entries) {
      if (e.completed) completedKeys.add(e.key);
    }
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Today's Schedule</Text>
      {focusToday ? <Text style={styles.focus}>{focusToday}</Text> : null}

      {items.length === 0 ? (
        <Text style={styles.empty}>
          No scheduled items for today. Tap "Regenerate" to create a new plan.
        </Text>
      ) : (
        <View style={styles.timeline}>
          {items.map((item, i) => {
            const done = completedKeys.has(item.title);
            return (
              <View key={i} style={styles.itemRow}>
                <Text style={styles.time}>{item.time}</Text>
                <Text style={styles.emoji}>
                  {DOMAIN_EMOJI[item.domain] || DOMAIN_EMOJI.other}
                </Text>
                <View style={styles.itemBody}>
                  <Text
                    style={[styles.itemTitle, done && styles.itemTitleDone]}
                    numberOfLines={2}
                  >
                    {item.title}
                  </Text>
                  {item.detail ? (
                    <Text style={styles.itemDetail} numberOfLines={2}>
                      {item.detail}
                    </Text>
                  ) : null}
                </View>
                <Pressable
                  style={[styles.checkBtn, done && styles.checkBtnDone]}
                  onPress={() => onToggleItem(item, !done)}
                >
                  <Text style={styles.checkBtnText}>
                    {done ? "\u2713" : ""}
                  </Text>
                </Pressable>
              </View>
            );
          })}
        </View>
      )}

      {motivationNote ? (
        <Text style={styles.motivation}>{"\u201C"}{motivationNote}{"\u201D"}</Text>
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
  title: { color: "#f8fafc", fontSize: 17, fontWeight: "700", marginBottom: 4 },
  focus: { color: "#a5b4fc", fontSize: 13, marginBottom: 12, lineHeight: 18 },
  empty: {
    color: "#64748b",
    fontSize: 13,
    textAlign: "center",
    paddingVertical: 16,
  },
  timeline: { gap: 8 },
  itemRow: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#0f172a",
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 10,
    gap: 10,
  },
  time: {
    color: "#94a3b8",
    fontSize: 12,
    fontWeight: "600",
    width: 44,
    fontFamily: "monospace",
  },
  emoji: { fontSize: 16 },
  itemBody: { flex: 1 },
  itemTitle: { color: "#e2e8f0", fontSize: 14, fontWeight: "600" },
  itemTitleDone: {
    color: "#64748b",
    textDecorationLine: "line-through",
  },
  itemDetail: {
    color: "#94a3b8",
    fontSize: 12,
    marginTop: 2,
    lineHeight: 16,
  },
  checkBtn: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 2,
    borderColor: "#475569",
    alignItems: "center",
    justifyContent: "center",
  },
  checkBtnDone: {
    backgroundColor: "#22c55e",
    borderColor: "#22c55e",
  },
  checkBtnText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  motivation: {
    color: "#cbd5e1",
    fontSize: 13,
    fontStyle: "italic",
    marginTop: 12,
    textAlign: "center",
    lineHeight: 18,
  },
});
