import { StyleSheet, Text, View } from "react-native";

interface EmptyStateProps {
  message: string;
  /** Optional smaller hint line below the message. */
  hint?: string;
}

/** A centered empty-state placeholder for dashboard sections with no data. */
export function EmptyState({ message, hint }: EmptyStateProps) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.message}>{message}</Text>
      {hint ? <Text style={styles.hint}>{hint}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: "center",
    paddingVertical: 24,
    paddingHorizontal: 16,
  },
  message: {
    color: "#94a3b8",
    fontSize: 14,
    textAlign: "center",
    lineHeight: 20,
  },
  hint: {
    color: "#64748b",
    fontSize: 12,
    marginTop: 6,
    textAlign: "center",
  },
});
