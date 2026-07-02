import { Pressable, StyleSheet, Text, View } from "react-native";
import type { TrackingPlan, OutcomeProgress } from "../../dashboard";

interface PlanOverviewCardProps {
  plan: TrackingPlan;
  /** Overall adherence (0..1) for today, or null if not computed. */
  overallAdherence: number | null;
  /** Outcome progress data (from /analytics/biomarker-progress). */
  outcomes: OutcomeProgress[];
  /** Day of plan (1-90). */
  dayOfPlan: number;
}

/** A card showing the plan title, rationale, overall adherence ring, and
 * outcome target progress. */
export function PlanOverviewCard({
  plan,
  overallAdherence,
  outcomes,
  dayOfPlan,
}: PlanOverviewCardProps) {
  const adherencePct =
    overallAdherence !== null && overallAdherence !== undefined
      ? Math.round(overallAdherence * 100)
      : null;

  // Determine current phase.
  const currentPhase = plan.phases.find(
    (p) => p.day_start <= dayOfPlan && dayOfPlan <= p.day_end,
  );

  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <View style={styles.headerLeft}>
          <Text style={styles.title}>{plan.title ?? "Your Plan"}</Text>
          {currentPhase ? (
            <Text style={styles.phase}>
              Day {dayOfPlan} · {currentPhase.name}
            </Text>
          ) : (
            <Text style={styles.phase}>Day {dayOfPlan}</Text>
          )}
        </View>
        {adherencePct !== null ? (
          <View style={styles.adherenceBadge}>
            <Text style={styles.adherenceValue}>{adherencePct}%</Text>
            <Text style={styles.adherenceLabel}>adherence</Text>
          </View>
        ) : null}
      </View>

      {plan.rationale ? (
        <Text style={styles.rationale}>{plan.rationale}</Text>
      ) : null}

      {currentPhase?.focus ? (
        <View style={styles.focusBox}>
          <Text style={styles.focusLabel}>This phase's focus</Text>
          <Text style={styles.focusText}>{currentPhase.focus}</Text>
        </View>
      ) : null}

      {/* Outcome targets */}
      {outcomes.length > 0 ? (
        <View style={styles.outcomesWrap}>
          <Text style={styles.outcomesTitle}>Outcome Targets</Text>
          {outcomes.map((o, i) => (
            <OutcomeRow key={i} outcome={o} />
          ))}
        </View>
      ) : null}
    </View>
  );
}

function OutcomeRow({ outcome }: { outcome: OutcomeProgress }) {
  const directionLabel =
    outcome.target_direction === "below"
      ? "below"
      : outcome.target_direction === "above"
      ? "above"
      : "in range";
  const onTrack = outcome.on_track;
  const current = outcome.current_value;
  const delta = outcome.delta;

  return (
    <View style={styles.outcomeRow}>
      <View
        style={[
          styles.outcomeDot,
          {
            backgroundColor:
              onTrack === true
                ? "#22c55e"
                : onTrack === false
                ? "#f97316"
                : "#64748b",
          },
        ]}
      />
      <View style={styles.outcomeContent}>
        <Text style={styles.outcomeName}>{outcome.biomarker_name}</Text>
        <Text style={styles.outcomeTarget}>
          Target: {directionLabel} {outcome.target_value} {outcome.unit}
        </Text>
        {current !== null && current !== undefined ? (
          <Text style={styles.outcomeCurrent}>
            Current: {formatValue(current)} {outcome.unit}
            {delta !== null && delta !== undefined ? (
              <Text
                style={[
                  styles.outcomeDelta,
                  {
                    color:
                      outcome.target_direction === "below"
                        ? delta < 0
                          ? "#22c55e"
                          : "#ef4444"
                        : outcome.target_direction === "above"
                        ? delta > 0
                          ? "#22c55e"
                          : "#ef4444"
                        : "#94a3b8",
                  },
                ]}
              >
                {"  "}
                ({delta > 0 ? "+" : ""}
                {formatValue(delta)})
              </Text>
            ) : null}
          </Text>
        ) : (
          <Text style={styles.outcomeCurrent}>No current reading</Text>
        )}
      </View>
      {onTrack !== null && onTrack !== undefined ? (
        <Text style={[styles.outcomeStatus, onTrack ? styles.onTrack : styles.offTrack]}>
          {onTrack ? "On track" : "Working on it"}
        </Text>
      ) : null}
    </View>
  );
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
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 8,
  },
  headerLeft: { flex: 1 },
  title: { color: "#f8fafc", fontSize: 17, fontWeight: "700" },
  phase: { color: "#a5b4fc", fontSize: 12, marginTop: 4 },
  adherenceBadge: {
    backgroundColor: "#0f172a",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 12,
    alignItems: "center",
  },
  adherenceValue: { color: "#6366f1", fontSize: 20, fontWeight: "800" },
  adherenceLabel: { color: "#94a3b8", fontSize: 10, marginTop: 2 },
  rationale: {
    color: "#cbd5e1",
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 10,
  },
  focusBox: {
    backgroundColor: "#0f172a",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 10,
  },
  focusLabel: { color: "#94a3b8", fontSize: 11, fontWeight: "600", marginBottom: 4 },
  focusText: { color: "#e2e8f0", fontSize: 13, lineHeight: 18 },
  outcomesWrap: {
    marginTop: 4,
  },
  outcomesTitle: {
    color: "#94a3b8",
    fontSize: 12,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  outcomeRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    gap: 10,
  },
  outcomeDot: { width: 8, height: 8, borderRadius: 4 },
  outcomeContent: { flex: 1 },
  outcomeName: { color: "#e2e8f0", fontSize: 13, fontWeight: "600" },
  outcomeTarget: { color: "#64748b", fontSize: 11, marginTop: 2 },
  outcomeCurrent: { color: "#94a3b8", fontSize: 11, marginTop: 1 },
  outcomeDelta: { fontSize: 11, fontWeight: "600" },
  outcomeStatus: { fontSize: 11, fontWeight: "700" },
  onTrack: { color: "#22c55e" },
  offTrack: { color: "#f97316" },
});
