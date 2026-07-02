import { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { useFocusEffect } from "@react-navigation/native";
import {
  getDashboardToday,
  regenerateSchedule,
  saveDailyLog,
  getPlan,
  getTodayMetricLogs,
  getAdherence,
  getBiomarkerProgress,
  logMetric,
  type DailySchedule,
  type DashboardToday,
  type LogEntry,
  type ScheduleItem,
  type TrackingPlan,
  type OutcomeProgress,
} from "../dashboard";
import { PlanSummaryCard } from "./dashboard/PlanSummaryCard";
import { DailyScheduleCard } from "./dashboard/DailyScheduleCard";
import { WellnessDomainCard } from "./dashboard/WellnessDomainCard";
import { MentalHealthCard } from "./dashboard/MentalHealthCard";
import { BiomarkerSection } from "./dashboard/BiomarkerSection";
import { EmptyState } from "./dashboard/EmptyState";
import { MetricCard } from "./dashboard/MetricCard";
import { PlanOverviewCard } from "./dashboard/PlanOverviewCard";
import { InsightsCard } from "./dashboard/InsightsCard";

interface DashboardScreenProps {
  /** Called when the user wants to switch to the Talk tab (e.g. to onboard). */
  onGoToTalk: () => void;
}

export function DashboardScreen({ onGoToTalk }: DashboardScreenProps) {
  const [data, setData] = useState<DashboardToday | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [biomarkerCount, setBiomarkerCount] = useState(0);
  // Tracking plan state.
  const [plan, setPlan] = useState<TrackingPlan | null>(null);
  const [metricLogs, setMetricLogs] = useState<Record<string, LogEntry[]>>({});
  const [overallAdherence, setOverallAdherence] = useState<number | null>(null);
  const [outcomes, setOutcomes] = useState<OutcomeProgress[]>([]);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const d = await getDashboardToday();
      setData(d);
      setBiomarkerCount(d.biomarker_count);
      setError(null);
      // Fetch tracking plan + metric logs + adherence + outcomes in parallel.
      const [p, ml, ad, oc] = await Promise.all([
        getPlan().catch(() => null),
        getTodayMetricLogs().catch(() => ({})),
        getAdherence().catch(() => null),
        getBiomarkerProgress().catch(() => []),
      ]);
      setPlan(p);
      setMetricLogs(ml);
      setOverallAdherence(ad?.overall ?? null);
      setOutcomes(oc);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // Re-fetch whenever the Dashboard tab gains focus (including initial mount).
  // The first focus shows the loading spinner; subsequent focuses (e.g. after
  // the user logs something by voice on the Talk tab) refetch silently so the
  // dashboard reflects voice-logged entries without a jarring spinner.
  const firstFocus = useRef(true);
  useFocusEffect(
    useCallback(() => {
      const silent = !firstFocus.current;
      firstFocus.current = false;
      void load(silent);
    }, [load]),
  );

  const handleRefresh = () => {
    setRefreshing(true);
    void load(true);
  };

  const handleRegenerate = async () => {
    setRegenerating(true);
    try {
      const schedule = await regenerateSchedule();
      setData((prev) =>
        prev ? { ...prev, schedule } : prev,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRegenerating(false);
    }
  };

  /** Toggle a schedule item's completion by upserting a log entry. */
  const handleToggleItem = useCallback(
    async (item: ScheduleItem, completed: boolean) => {
      if (!data) return;
      const domain = item.domain;
      const existing = data.logs[domain] ?? [];
      // Replace any existing entry with the same key, then add/update.
      const without = existing.filter((e) => e.key !== item.title);
      const entry: LogEntry = {
        key: item.title,
        completed,
        value: item.duration_min ?? null,
      };
      const next = [...without, entry];
      // Optimistic update.
      setData({
        ...data,
        logs: { ...data.logs, [domain]: next },
      });
      try {
        await saveDailyLog(data.date, domain, next);
      } catch (e) {
        // Revert on failure.
        setData(data);
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [data],
  );

  /** Quick-log an actual value for a domain (adds to today's total). */
  const handleQuickLog = useCallback(
    async (domain: string, value: number) => {
      if (!data) return;
      const existing = data.logs[domain] ?? [];
      const entry: LogEntry = {
        key: `quick_${Date.now()}`,
        completed: true,
        value,
      };
      const next = [...existing, entry];
      setData({ ...data, logs: { ...data.logs, [domain]: next } });
      try {
        await saveDailyLog(data.date, domain, next);
      } catch (e) {
        setData(data);
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [data],
  );

  const handleLogMood = useCallback(
    async (mood: number) => {
      if (!data) return;
      const domain = "mental_health";
      const existing = (data.logs[domain] ?? []).filter((e) => e.key !== "mood");
      const entry: LogEntry = { key: "mood", completed: true, value: mood };
      const next = [...existing, entry];
      setData({ ...data, logs: { ...data.logs, [domain]: next } });
      try {
        await saveDailyLog(data.date, domain, next);
      } catch (e) {
        setData(data);
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [data],
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <StatusBar style="light" />
        <View style={styles.centered}>
          <ActivityIndicator color="#6366f1" size="large" />
          <Text style={styles.loadingText}>Loading your dashboard…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (error && !data) {
    return (
      <SafeAreaView style={styles.container}>
        <StatusBar style="light" />
        <View style={styles.centered}>
          <Text style={styles.errorText}>{error}</Text>
          <Pressable style={styles.retryBtn} onPress={() => void load()}>
            <Text style={styles.retryText}>Retry</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  // Not onboarded → show CTA to switch to Talk tab.
  if (data && !data.onboarded) {
    return (
      <SafeAreaView style={styles.container}>
        <StatusBar style="light" />
        <View style={styles.centered}>
          <Text style={styles.ctaTitle}>Welcome to your dashboard</Text>
          <Text style={styles.ctaBody}>
            Complete onboarding with Bloom to unlock your personalized daily
            schedule, wellness tracking, and biomarker visuals.
          </Text>
          <Pressable style={styles.ctaBtn} onPress={onGoToTalk}>
            <Text style={styles.ctaBtnText}>Talk to Bloom</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  const schedule = data?.schedule ?? null;
  const targets = schedule?.daily_targets ?? {};
  const hasPlan = plan !== null && plan.metrics.length > 0;

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            tintColor="#6366f1"
            colors={["#6366f1"]}
          />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Text style={styles.greeting}>{greeting()}</Text>
            {data ? (
              <Text style={styles.dayOfPlan}>
                Day {data.day_of_plan} of 90{"  "}{"\u00B7"}{"  "}
                {data.phase}
              </Text>
            ) : null}
          </View>
          <Pressable
            style={[
              styles.regenerateBtn,
              regenerating && styles.regenerateBtnDisabled,
            ]}
            onPress={handleRegenerate}
            disabled={regenerating}
          >
            {regenerating ? (
              <ActivityIndicator color="#a5b4fc" size="small" />
            ) : (
              <Text style={styles.regenerateText}>{"\u21BB"} New plan</Text>
            )}
          </Pressable>
        </View>

        {error ? (
          <View style={styles.errorBar}>
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        {/* Plan overview card (when a tracking plan is active) */}
        {hasPlan && data ? (
          <PlanOverviewCard
            plan={plan!}
            overallAdherence={overallAdherence}
            outcomes={outcomes}
            dayOfPlan={data.day_of_plan}
          />
        ) : data ? (
          /* Legacy plan summary card (no tracking plan) */
          <PlanSummaryCard
            summary={data.plan_summary}
            phase={data.phase}
            dayOfPlan={data.day_of_plan}
            phaseFocus={data.plan_phase_focus}
          />
        ) : null}

        {/* Daily schedule */}
        {schedule ? (
          <DailyScheduleCard
            focusToday={schedule.focus_today}
            motivationNote={schedule.motivation_note}
            items={schedule.items}
            logs={data?.logs ?? {}}
            onToggleItem={handleToggleItem}
          />
        ) : (
          <EmptyState
            message="No schedule for today yet."
            hint='Tap "New plan" above to generate one.'
          />
        )}

        {/* Plan-based metric cards (when a tracking plan is active) */}
        {hasPlan ? (
          <>
            <SectionHeader title="Today's Metrics" />
            {plan!.metrics
              .filter((m) => m.is_active)
              .map((m) => (
                <MetricCard
                  key={m.id}
                  metric={m}
                  todayEntries={metricLogs[String(m.id)]}
                  onLogged={() => void load(true)}
                />
              ))}
            {/* AI Insights */}
            <SectionHeader title="AI Insights" />
            <InsightsCard />
          </>
        ) : (
          <>
            {/* Legacy wellness domain cards (no tracking plan) */}
            <SectionHeader title="Today's Wellness" />
            <WellnessDomainCard
              domain="workout"
              title="Workouts"
              icon={"\u{1F3CB}"}
              targetValue={targets.workout_minutes}
              targetLabel="min"
              todayEntries={data?.logs?.workout}
              onQuickLog={(v) => void handleQuickLog("workout", v)}
            />
            <WellnessDomainCard
              domain="diet"
              title="Diet"
              icon={"\u{1F969}"}
              targetValue={targets.meals_logged}
              targetLabel="meals"
              todayEntries={data?.logs?.diet}
              onQuickLog={() => void handleQuickLog("diet", 1)}
            />
            <WellnessDomainCard
              domain="meditation"
              title="Meditation"
              icon={"\u{1F9D8}"}
              targetValue={targets.meditation_minutes}
              targetLabel="min"
              todayEntries={data?.logs?.meditation}
              onQuickLog={(v) => void handleQuickLog("meditation", v)}
            />
            <WellnessDomainCard
              domain="medication"
              title="Medication"
              icon={"\u{1F48A}"}
              targetValue={targets.meds_taken}
              targetLabel="doses"
              todayEntries={data?.logs?.medication}
              onQuickLog={() => void handleQuickLog("medication", 1)}
            />

            {/* Mental health (special card with mood check-in) */}
            <MentalHealthCard
              todayEntries={data?.logs?.mental_health}
              onLogMood={handleLogMood}
            />
          </>
        )}

        {/* Biomarkers (the centerpiece) */}
        <SectionHeader title="Biomarkers" />
        <BiomarkerSection
          initialCount={biomarkerCount}
          onCountChange={setBiomarkerCount}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function SectionHeader({ title }: { title: string }) {
  return <Text style={styles.sectionHeader}>{title}</Text>;
}

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 40 },
  centered: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: 28,
  },
  loadingText: { color: "#94a3b8", fontSize: 14, marginTop: 12 },
  errorBar: {
    backgroundColor: "#7f1d1d",
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
    marginBottom: 12,
  },
  errorText: { color: "#fecaca", fontSize: 13, textAlign: "center" },
  retryBtn: {
    backgroundColor: "#6366f1",
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 10,
    marginTop: 16,
  },
  retryText: { color: "#fff", fontWeight: "600" },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 14,
  },
  headerLeft: { flex: 1 },
  greeting: { color: "#f8fafc", fontSize: 22, fontWeight: "700" },
  dayOfPlan: { color: "#94a3b8", fontSize: 12, marginTop: 4 },
  regenerateBtn: {
    backgroundColor: "#1e293b",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
  },
  regenerateBtnDisabled: { opacity: 0.6 },
  regenerateText: { color: "#a5b4fc", fontSize: 13, fontWeight: "600" },
  sectionHeader: {
    color: "#94a3b8",
    fontSize: 13,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.5,
    marginTop: 8,
    marginBottom: 10,
    paddingHorizontal: 4,
  },
  ctaTitle: { color: "#f8fafc", fontSize: 22, fontWeight: "700", textAlign: "center" },
  ctaBody: {
    color: "#94a3b8",
    fontSize: 14,
    textAlign: "center",
    lineHeight: 20,
    marginTop: 12,
  },
  ctaBtn: {
    backgroundColor: "#6366f1",
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 12,
    marginTop: 24,
  },
  ctaBtnText: { color: "#fff", fontSize: 15, fontWeight: "700" },
});
