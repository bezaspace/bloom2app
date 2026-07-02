import { useEffect, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { LineChart } from "react-native-gifted-charts";
import {
  getBiomarkers,
  refreshBiomarkersFromDocs,
  type BiomarkerGroup,
  type BiomarkerReading,
} from "../../dashboard";
import { EmptyState } from "./EmptyState";

const STATUS_COLORS: Record<string, string> = {
  low: "#3b82f6",
  normal: "#22c55e",
  high: "#ef4444",
  unknown: "#64748b",
};

const STATUS_LABELS: Record<string, string> = {
  low: "Low",
  normal: "Normal",
  high: "High",
  unknown: "No range",
};

interface BiomarkerSectionProps {
  /** Initial count from /dashboard/today (avoids a flash of 0). */
  initialCount: number;
  /** Called when biomarkers have been refreshed (so parent can update count). */
  onCountChange?: (count: number) => void;
}

/** The biomarker overview grid + a detail modal for a single marker. */
export function BiomarkerSection({ initialCount, onCountChange }: BiomarkerSectionProps) {
  const [groups, setGroups] = useState<BiomarkerGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selected, setSelected] = useState<BiomarkerGroup | null>(null);

  const load = async () => {
    try {
      const g = await getBiomarkers();
      setGroups(g);
      onCountChange?.(g.length);
    } catch (e) {
      console.warn("Failed to load biomarkers:", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshBiomarkersFromDocs();
      await load();
    } catch (e) {
      console.warn("Refresh failed:", e);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <View style={styles.sectionWrap}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>{"\u{1F9EC}"} Biomarkers</Text>
        <Pressable
          style={[styles.refreshBtn, refreshing && styles.refreshBtnDisabled]}
          onPress={handleRefresh}
          disabled={refreshing}
        >
          <Text style={styles.refreshText}>
            {refreshing ? "Refreshing…" : "Refresh from docs"}
          </Text>
        </Pressable>
      </View>

      {loading ? (
        <Text style={styles.loadingText}>Loading biomarkers…</Text>
      ) : groups.length === 0 ? (
        <EmptyState
          message={
            initialCount > 0
              ? "Biomarkers are being processed."
              : "No biomarkers yet."
          }
          hint="Upload a lab report (PDF or image) on the Talk tab to extract biomarker readings."
        />
      ) : (
        <View style={styles.grid}>
          {groups.map((g) => (
            <BiomarkerCard key={g.name} group={g} onPress={() => setSelected(g)} />
          ))}
        </View>
      )}

      <BiomarkerDetailModal
        group={selected}
        onClose={() => setSelected(null)}
      />
    </View>
  );
}

/** A single biomarker card in the overview grid. */
function BiomarkerCard({
  group,
  onPress,
}: {
  group: BiomarkerGroup;
  onPress: () => void;
}) {
  const latest = group.readings[group.readings.length - 1] ?? null;
  const status = latest?.status ?? "unknown";
  const color = STATUS_COLORS[status] ?? STATUS_COLORS.unknown;
  const hasTrend = group.readings.length >= 2;

  // Mini sparkline data (just values).
  const sparkData = group.readings.map((r) => ({ value: r.value }));

  return (
    <Pressable style={styles.card} onPress={onPress}>
      <Text style={styles.cardName} numberOfLines={1}>
        {group.name}
      </Text>
      <View style={styles.cardValueRow}>
        <Text style={[styles.cardValue, { color }]}>
          {latest ? formatValue(latest.value) : "—"}
        </Text>
        <Text style={styles.cardUnit}>{group.unit}</Text>
      </View>
      <View style={styles.cardStatusRow}>
        <View style={[styles.statusDot, { backgroundColor: color }]} />
        <Text style={styles.statusText}>{STATUS_LABELS[status]}</Text>
        {hasTrend ? (
          <Text style={styles.trendCount}>
            {"  \u00B7  "}
            {group.readings.length} readings
          </Text>
        ) : null}
      </View>
      {hasTrend ? (
        <View style={styles.sparkWrap}>
          <LineChart
            data={sparkData}
            width={120}
            height={32}
            color={color}
            thickness={1.5}
            curved
            isAnimated
            hideAxesAndRules
            hideOrigin
            dataPointsRadius={0}
            adjustToWidth
          />
        </View>
      ) : null}
    </Pressable>
  );
}

/** Full-screen modal showing a single biomarker's trend with range bands. */
function BiomarkerDetailModal({
  group,
  onClose,
}: {
  group: BiomarkerGroup | null;
  onClose: () => void;
}) {
  return (
    <Modal
      visible={group !== null}
      animationType="slide"
      onRequestClose={onClose}
    >
      <View style={styles.modalWrap}>
        <View style={styles.modalHeader}>
          <Text style={styles.modalTitle}>{group?.name ?? "Biomarker"}</Text>
          <Pressable style={styles.modalClose} onPress={onClose}>
            <Text style={styles.modalCloseText}>Close</Text>
          </Pressable>
        </View>
        <ScrollView
          style={styles.modalBody}
          contentContainerStyle={styles.modalBodyContent}
        >
          {group ? <BiomarkerDetail group={group} /> : null}
        </ScrollView>
      </View>
    </Modal>
  );
}

/** The inner content of the detail modal: stats + trend chart with bands. */
function BiomarkerDetail({ group }: { group: BiomarkerGroup }) {
  const readings = group.readings;
  const latest = readings[readings.length - 1];
  const prior = readings.length >= 2 ? readings[readings.length - 2] : null;

  const delta = prior ? latest.value - prior.value : null;
  const pctDelta =
    prior && prior.value !== 0 ? (delta! / prior.value) * 100 : null;

  const status = latest?.status ?? "unknown";
  const color = STATUS_COLORS[status] ?? STATUS_COLORS.unknown;

  const chartData = readings.map((r) => ({
    value: r.value,
    label: r.measured_at ? r.measured_at.slice(5) : "",
    dataPointColor: STATUS_COLORS[r.status] ?? STATUS_COLORS.unknown,
  }));

  // gifted-charts supports up to 3 horizontal reference lines. We use
  // line 1 for ref_low and line 2 for ref_high to bracket the normal range.
  const refLow = group.ref_low ?? null;
  const refHigh = group.ref_high ?? null;

  return (
    <View>
      {/* Latest value + delta */}
      <View style={styles.detailStatsRow}>
        <View style={styles.detailStat}>
          <Text style={styles.detailStatLabel}>Latest</Text>
          <Text style={[styles.detailStatValue, { color }]}>
            {formatValue(latest.value)}{" "}
            <Text style={styles.detailStatUnit}>{group.unit}</Text>
          </Text>
          {latest.measured_at ? (
            <Text style={styles.detailStatSub}>{latest.measured_at}</Text>
          ) : null}
        </View>
        {delta != null ? (
          <View style={styles.detailStat}>
            <Text style={styles.detailStatLabel}>Change</Text>
            <Text
              style={[
                styles.detailStatValue,
                { color: delta > 0 ? "#ef4444" : delta < 0 ? "#3b82f6" : "#94a3b8" },
              ]}
            >
              {delta > 0 ? "+" : ""}
              {formatValue(delta)}
            </Text>
            {pctDelta != null ? (
              <Text style={styles.detailStatSub}>
                {pctDelta > 0 ? "+" : ""}
                {pctDelta.toFixed(1)}%
              </Text>
            ) : null}
          </View>
        ) : null}
      </View>

      {/* Reference / optimal ranges */}
      <View style={styles.rangeRow}>
        <RangeChip
          label="Reference range"
          low={group.ref_low}
          high={group.ref_high}
          unit={group.unit}
          color="#475569"
        />
        {group.optimal_low != null || group.optimal_high != null ? (
          <RangeChip
            label="Optimal range"
            low={group.optimal_low}
            high={group.optimal_high}
            unit={group.unit}
            color="#22c55e"
          />
        ) : null}
      </View>

      {/* Trend chart */}
      {readings.length >= 2 ? (
        <View style={styles.detailChartWrap}>
          <Text style={styles.detailChartTitle}>Trend over time</Text>
          <LineChart
            data={chartData}
            width={300}
            height={200}
            color={color}
            dataPointsRadius={5}
            thickness={2}
            curved
            isAnimated
            yAxisTextStyle={styles.axisText}
            yAxisColor="#475569"
            xAxisColor="#475569"
            xAxisLabelTextStyle={styles.axisText}
            rulesColor="#1e293b"
            referenceLine1Config={{
              color: "#475569",
              dashWidth: 4,
              dashGap: 4,
              labelText: refLow != null ? `low ${formatValue(refLow)}` : "",
              labelTextStyle: { color: "#64748b", fontSize: 9 },
            }}
            referenceLine1Position={refLow ?? undefined}
            referenceLine2Config={{
              color: "#475569",
              dashWidth: 4,
              dashGap: 4,
              labelText: refHigh != null ? `high ${formatValue(refHigh)}` : "",
              labelTextStyle: { color: "#64748b", fontSize: 9 },
            }}
            referenceLine2Position={refHigh ?? undefined}
            spacing={Math.max(20, 280 / Math.max(1, readings.length - 1))}
          />
        </View>
      ) : (
        <EmptyState
          message="Only one reading so far."
          hint="Upload another lab report later to see a trend."
        />
      )}

      {/* History table */}
      <View style={styles.historyWrap}>
        <Text style={styles.historyTitle}>History</Text>
        {[...readings].reverse().map((r, i) => (
          <HistoryRow key={r.id ?? i} reading={r} unit={group.unit} />
        ))}
      </View>

      <Text style={styles.disclaimer}>
        Experimental prototype — not medical advice. Consult a licensed
        clinician to interpret these results.
      </Text>
    </View>
  );
}

function RangeChip({
  label,
  low,
  high,
  unit,
  color,
}: {
  label: string;
  low: number | null | undefined;
  high: number | null | undefined;
  unit: string;
  color: string;
}) {
  const hasRange = low != null || high != null;
  return (
    <View style={styles.rangeChip}>
      <View style={[styles.rangeChipDot, { backgroundColor: color }]} />
      <View>
        <Text style={styles.rangeChipLabel}>{label}</Text>
        <Text style={styles.rangeChipValue}>
          {hasRange
            ? `${low != null ? formatValue(low) : "—"} – ${high != null ? formatValue(high) : "—"} ${unit}`
            : "Not specified"}
        </Text>
      </View>
    </View>
  );
}

function HistoryRow({ reading, unit }: { reading: BiomarkerReading; unit: string }) {
  const color = STATUS_COLORS[reading.status] ?? STATUS_COLORS.unknown;
  return (
    <View style={styles.historyRow}>
      <View style={[styles.statusDot, { backgroundColor: color }]} />
      <Text style={styles.historyValue}>
        {formatValue(reading.value)} {unit}
      </Text>
      <Text style={styles.historyDate}>
        {reading.measured_at ?? "Date unknown"}
      </Text>
      <Text style={styles.historySource} numberOfLines={1}>
        {reading.source_doc || ""}
      </Text>
    </View>
  );
}

function formatValue(v: number): string {
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(2).replace(/\.?0+$/, "");
}

const styles = StyleSheet.create({
  sectionWrap: { marginBottom: 12 },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 10,
    paddingHorizontal: 4,
  },
  title: { color: "#f8fafc", fontSize: 17, fontWeight: "700" },
  refreshBtn: {
    backgroundColor: "#1e293b",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 10,
  },
  refreshBtnDisabled: { opacity: 0.6 },
  refreshText: { color: "#a5b4fc", fontSize: 12, fontWeight: "600" },
  loadingText: { color: "#64748b", fontSize: 13, paddingVertical: 20, textAlign: "center" },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  card: {
    backgroundColor: "#1e293b",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 12,
    width: "48%",
    flexGrow: 1,
  },
  cardName: { color: "#e2e8f0", fontSize: 13, fontWeight: "600", marginBottom: 6 },
  cardValueRow: { flexDirection: "row", alignItems: "baseline", gap: 4 },
  cardValue: { fontSize: 22, fontWeight: "700" },
  cardUnit: { color: "#94a3b8", fontSize: 12 },
  cardStatusRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 6,
  },
  statusDot: { width: 8, height: 8, borderRadius: 4, marginRight: 6 },
  statusText: { color: "#cbd5e1", fontSize: 11, fontWeight: "600" },
  trendCount: { color: "#64748b", fontSize: 11 },
  sparkWrap: { marginTop: 8, alignItems: "center" },
  // Modal
  modalWrap: { flex: 1, backgroundColor: "#0f172a" },
  modalHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingVertical: 16,
    borderBottomWidth: 1,
    borderBottomColor: "#1e293b",
  },
  modalTitle: { fontSize: 20, fontWeight: "700", color: "#f8fafc", flexShrink: 1 },
  modalClose: {
    backgroundColor: "#1e293b",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 10,
  },
  modalCloseText: { color: "#94a3b8", fontWeight: "600" },
  modalBody: { flex: 1, paddingHorizontal: 20 },
  modalBodyContent: { paddingVertical: 20, paddingBottom: 40 },
  detailStatsRow: { flexDirection: "row", gap: 20, marginBottom: 16 },
  detailStat: { flex: 1 },
  detailStatLabel: { color: "#64748b", fontSize: 12, marginBottom: 4 },
  detailStatValue: { fontSize: 22, fontWeight: "700" },
  detailStatUnit: { color: "#94a3b8", fontSize: 13, fontWeight: "500" },
  detailStatSub: { color: "#64748b", fontSize: 11, marginTop: 2 },
  rangeRow: { flexDirection: "row", gap: 12, marginBottom: 16, flexWrap: "wrap" },
  rangeChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "#1e293b",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
  },
  rangeChipDot: { width: 8, height: 8, borderRadius: 4 },
  rangeChipLabel: { color: "#94a3b8", fontSize: 11 },
  rangeChipValue: { color: "#e2e8f0", fontSize: 13, fontWeight: "600" },
  detailChartWrap: {
    backgroundColor: "#1e293b",
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 14,
    alignItems: "center",
    marginBottom: 16,
  },
  detailChartTitle: {
    color: "#cbd5e1",
    fontSize: 13,
    fontWeight: "600",
    marginBottom: 10,
    alignSelf: "flex-start",
  },
  axisText: { color: "#64748b", fontSize: 10 },
  historyWrap: { marginBottom: 16 },
  historyTitle: {
    color: "#cbd5e1",
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 8,
  },
  historyRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#1e293b",
    gap: 8,
  },
  historyValue: { color: "#e2e8f0", fontSize: 13, fontWeight: "600", flex: 1 },
  historyDate: { color: "#94a3b8", fontSize: 11 },
  historySource: { color: "#64748b", fontSize: 10, flexShrink: 1, marginLeft: 8 },
  disclaimer: {
    color: "#64748b",
    fontSize: 11,
    fontStyle: "italic",
    textAlign: "center",
    lineHeight: 16,
    marginTop: 8,
  },
});
