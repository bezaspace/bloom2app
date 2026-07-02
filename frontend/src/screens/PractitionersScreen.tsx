import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";
import { useFocusEffect } from "@react-navigation/native";
import {
  bookAppointment,
  cancelAppointment,
  getMyAppointments,
  listPractitioners,
  type Appointment,
  type Practitioner,
} from "../practitioners";

type ScreenView =
  | { kind: "list" }
  | { kind: "detail"; practitioner: Practitioner }
  | { kind: "book"; practitioner: Practitioner }
  | { kind: "myAppointments" };

const STATUS_COLORS: Record<Appointment["status"], string> = {
  pending: "#f59e0b",
  accepted: "#22c55e",
  declined: "#ef4444",
  completed: "#6366f1",
  cancelled: "#64748b",
};

export function PractitionersScreen() {
  const [view, setView] = useState<ScreenView>({ kind: "list" });

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar style="light" />
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Practitioners</Text>
        <View style={styles.headerTabs}>
          <Pressable
            style={[
              styles.headerTab,
              view.kind === "list" && styles.headerTabActive,
            ]}
            onPress={() => setView({ kind: "list" })}
          >
            <Text
              style={[
                styles.headerTabText,
                view.kind === "list" && styles.headerTabTextActive,
              ]}
            >
              Find
            </Text>
          </Pressable>
          <Pressable
            style={[
              styles.headerTab,
              view.kind === "myAppointments" && styles.headerTabActive,
            ]}
            onPress={() => setView({ kind: "myAppointments" })}
          >
            <Text
              style={[
                styles.headerTabText,
                view.kind === "myAppointments" && styles.headerTabTextActive,
              ]}
            >
              My Appointments
            </Text>
          </Pressable>
        </View>
      </View>

      {view.kind === "list" && (
        <PractitionerList onSelect={(p) => setView({ kind: "detail", practitioner: p })} />
      )}
      {view.kind === "detail" && (
        <PractitionerDetail
          practitioner={view.practitioner}
          onBack={() => setView({ kind: "list" })}
          onBook={() => setView({ kind: "book", practitioner: view.practitioner })}
        />
      )}
      {view.kind === "book" && (
        <BookAppointment
          practitioner={view.practitioner}
          onBack={() => setView({ kind: "detail", practitioner: view.practitioner })}
          onDone={() => setView({ kind: "myAppointments" })}
        />
      )}
      {view.kind === "myAppointments" && (
        <MyAppointments onBookMore={() => setView({ kind: "list" })} />
      )}
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// Practitioner list
// ---------------------------------------------------------------------------
function PractitionerList({ onSelect }: { onSelect: (p: Practitioner) => void }) {
  const [practitioners, setPractitioners] = useState<Practitioner[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const list = await listPractitioners(search || undefined);
      setPractitioners(list);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [search]);

  useFocusEffect(
    useCallback(() => {
      void load(false);
    }, [load]),
  );

  const filtered = search
    ? practitioners.filter(
        (p) =>
          p.full_name.toLowerCase().includes(search.toLowerCase()) ||
          (p.specialization ?? "").toLowerCase().includes(search.toLowerCase()),
      )
    : practitioners;

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color="#6366f1" size="large" />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.flex}
      contentContainerStyle={styles.scrollContent}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => {
            setRefreshing(true);
            void load(true);
          }}
          tintColor="#6366f1"
        />
      }
    >
      <TextInput
        style={styles.searchInput}
        placeholder="Search by name or specialization..."
        placeholderTextColor="#64748b"
        value={search}
        onChangeText={setSearch}
      />
      {error && <Text style={styles.errorText}>{error}</Text>}
      {filtered.length === 0 && !error && (
        <Text style={styles.emptyText}>No practitioners found.</Text>
      )}
      {filtered.map((p) => (
        <Pressable
          key={p.id}
          style={styles.card}
          onPress={() => onSelect(p)}
        >
          <View style={styles.cardHeader}>
            <Text style={styles.cardName}>{p.full_name}</Text>
            {p.title && <Text style={styles.cardTitle}>{p.title}</Text>}
          </View>
          {p.specialization && (
            <Text style={styles.cardSpec}>{p.specialization}</Text>
          )}
          {p.bio && (
            <Text style={styles.cardBio} numberOfLines={3}>
              {p.bio}
            </Text>
          )}
          <View style={styles.cardFooter}>
            {p.years_experience != null && (
              <Text style={styles.cardMeta}>{p.years_experience} yrs exp</Text>
            )}
            {p.consultation_fee != null && (
              <Text style={styles.cardMeta}>
                ${p.consultation_fee.toFixed(0)} / session
              </Text>
            )}
          </View>
        </Pressable>
      ))}
    </ScrollView>
  );
}

// ---------------------------------------------------------------------------
// Practitioner detail
// ---------------------------------------------------------------------------
function PractitionerDetail({
  practitioner,
  onBack,
  onBook,
}: {
  practitioner: Practitioner;
  onBack: () => void;
  onBook: () => void;
}) {
  return (
    <ScrollView style={styles.flex} contentContainerStyle={styles.scrollContent}>
      <Pressable style={styles.backButton} onPress={onBack}>
        <Text style={styles.backButtonText}>{"< Back"}</Text>
      </Pressable>
      <View style={styles.detailCard}>
        <Text style={styles.detailName}>{practitioner.full_name}</Text>
        {practitioner.title && (
          <Text style={styles.detailTitle}>{practitioner.title}</Text>
        )}
        {practitioner.specialization && (
          <Text style={styles.detailSpec}>{practitioner.specialization}</Text>
        )}
        {practitioner.bio && (
          <Text style={styles.detailBio}>{practitioner.bio}</Text>
        )}
        <View style={styles.detailMetaRow}>
          {practitioner.years_experience != null && (
            <View style={styles.detailMetaItem}>
              <Text style={styles.detailMetaLabel}>Experience</Text>
              <Text style={styles.detailMetaValue}>
                {practitioner.years_experience} years
              </Text>
            </View>
          )}
          {practitioner.consultation_fee != null && (
            <View style={styles.detailMetaItem}>
              <Text style={styles.detailMetaLabel}>Fee</Text>
              <Text style={styles.detailMetaValue}>
                ${practitioner.consultation_fee.toFixed(0)}
              </Text>
            </View>
          )}
        </View>
      </View>
      <Pressable style={styles.bookButton} onPress={onBook}>
        <Text style={styles.bookButtonText}>Book Appointment</Text>
      </Pressable>
    </ScrollView>
  );
}

// ---------------------------------------------------------------------------
// Book appointment
// ---------------------------------------------------------------------------
function BookAppointment({
  practitioner,
  onBack,
  onDone,
}: {
  practitioner: Practitioner;
  onBack: () => void;
  onDone: () => void;
}) {
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleBook = async () => {
    if (!date) {
      setError("Please enter a date (YYYY-MM-DD).");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await bookAppointment({
        practitioner_id: practitioner.id,
        requested_date: date,
        requested_time: time || null,
        reason: reason || null,
        patient_note: note || null,
      });
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ScrollView style={styles.flex} contentContainerStyle={styles.scrollContent}>
      <Pressable style={styles.backButton} onPress={onBack}>
        <Text style={styles.backButtonText}>{"< Back"}</Text>
      </Pressable>
      <Text style={styles.formTitle}>
        Book with {practitioner.full_name}
      </Text>
      <View style={styles.form}>
        <Text style={styles.fieldLabel}>Date (YYYY-MM-DD)</Text>
        <TextInput
          style={styles.fieldInput}
          placeholder="2026-07-10"
          placeholderTextColor="#64748b"
          value={date}
          onChangeText={setDate}
        />
        <Text style={styles.fieldLabel}>Time (HH:MM, optional)</Text>
        <TextInput
          style={styles.fieldInput}
          placeholder="10:00"
          placeholderTextColor="#64748b"
          value={time}
          onChangeText={setTime}
        />
        <Text style={styles.fieldLabel}>Reason for visit</Text>
        <TextInput
          style={[styles.fieldInput, styles.fieldMultiline]}
          placeholder="Brief reason for the appointment..."
          placeholderTextColor="#64748b"
          value={reason}
          onChangeText={setReason}
          multiline
        />
        <Text style={styles.fieldLabel}>Note to practitioner (optional)</Text>
        <TextInput
          style={[styles.fieldInput, styles.fieldMultiline]}
          placeholder="Anything you'd like the practitioner to know..."
          placeholderTextColor="#64748b"
          value={note}
          onChangeText={setNote}
          multiline
        />
        {error && <Text style={styles.errorText}>{error}</Text>}
        <Pressable
          style={[styles.bookButton, busy && styles.bookButtonDisabled]}
          onPress={handleBook}
          disabled={busy}
        >
          {busy ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.bookButtonText}>Request Appointment</Text>
          )}
        </Pressable>
      </View>
    </ScrollView>
  );
}

// ---------------------------------------------------------------------------
// My appointments
// ---------------------------------------------------------------------------
function MyAppointments({ onBookMore }: { onBookMore: () => void }) {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const list = await getMyAppointments();
      setAppointments(list);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load(false);
    }, [load]),
  );

  const handleCancel = async (id: number) => {
    try {
      await cancelAppointment(id);
      void load(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator color="#6366f1" size="large" />
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.flex}
      contentContainerStyle={styles.scrollContent}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={() => {
            setRefreshing(true);
            void load(true);
          }}
          tintColor="#6366f1"
        />
      }
    >
      {error && <Text style={styles.errorText}>{error}</Text>}
      {appointments.length === 0 && !error && (
        <View style={styles.emptyState}>
          <Text style={styles.emptyText}>No appointments yet.</Text>
          <Pressable style={styles.bookButton} onPress={onBookMore}>
            <Text style={styles.bookButtonText}>Find a Practitioner</Text>
          </Pressable>
        </View>
      )}
      {appointments.map((a) => (
        <View key={a.id} style={styles.card}>
          <View style={styles.apptHeader}>
            <Text style={styles.cardName}>
              {a.practitioner?.full_name ?? `Practitioner #${a.practitioner_id}`}
            </Text>
            <View
              style={[
                styles.statusBadge,
                { backgroundColor: STATUS_COLORS[a.status] + "22" },
              ]}
            >
              <Text
                style={[styles.statusText, { color: STATUS_COLORS[a.status] }]}
              >
                {a.status}
              </Text>
            </View>
          </View>
          <Text style={styles.apptDate}>
            {a.requested_date}
            {a.requested_time ? ` at ${a.requested_time}` : ""}
          </Text>
          {a.reason && <Text style={styles.cardBio}>{a.reason}</Text>}
          {a.status === "accepted" && (
            <Text style={styles.acceptedNote}>
              Accepted — you're now connected with this practitioner.
            </Text>
          )}
          {a.status === "declined" && a.practitioner_note && (
            <Text style={styles.declinedNote}>
              Note: {a.practitioner_note}
            </Text>
          )}
          {a.status === "pending" && (
            <Pressable
              style={styles.cancelButton}
              onPress={() => handleCancel(a.id)}
            >
              <Text style={styles.cancelButtonText}>Cancel Request</Text>
            </Pressable>
          )}
        </View>
      ))}
    </ScrollView>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  flex: { flex: 1 },
  centered: { flex: 1, justifyContent: "center", alignItems: "center" },
  scrollContent: { padding: 16, paddingBottom: 32 },
  header: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 12 },
  headerTitle: { fontSize: 22, fontWeight: "700", color: "#f8fafc", marginBottom: 12 },
  headerTabs: { flexDirection: "row", gap: 8 },
  headerTab: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 10,
    backgroundColor: "#1e293b",
  },
  headerTabActive: { backgroundColor: "#6366f1" },
  headerTabText: { color: "#94a3b8", fontSize: 14, fontWeight: "600" },
  headerTabTextActive: { color: "#fff" },
  searchInput: {
    backgroundColor: "#1e293b",
    color: "#f1f5f9",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 12,
    fontSize: 15,
    marginBottom: 12,
  },
  card: {
    backgroundColor: "#1e293b",
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
  },
  cardHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 },
  cardName: { fontSize: 17, fontWeight: "700", color: "#f8fafc", flexShrink: 1 },
  cardTitle: { fontSize: 13, color: "#6366f1", fontWeight: "600" },
  cardSpec: { fontSize: 14, color: "#94a3b8", marginBottom: 8 },
  cardBio: { fontSize: 13, color: "#cbd5e1", lineHeight: 19, marginBottom: 8 },
  cardFooter: { flexDirection: "row", gap: 16 },
  cardMeta: { fontSize: 12, color: "#64748b" },
  backButton: { paddingVertical: 8, marginBottom: 8 },
  backButtonText: { color: "#6366f1", fontSize: 15, fontWeight: "600" },
  detailCard: { backgroundColor: "#1e293b", borderRadius: 14, padding: 20, marginBottom: 16 },
  detailName: { fontSize: 22, fontWeight: "700", color: "#f8fafc", marginBottom: 4 },
  detailTitle: { fontSize: 15, color: "#6366f1", fontWeight: "600", marginBottom: 2 },
  detailSpec: { fontSize: 15, color: "#94a3b8", marginBottom: 12 },
  detailBio: { fontSize: 14, color: "#cbd5e1", lineHeight: 20, marginBottom: 16 },
  detailMetaRow: { flexDirection: "row", gap: 24 },
  detailMetaItem: {},
  detailMetaLabel: { fontSize: 11, color: "#64748b", textTransform: "uppercase", marginBottom: 2 },
  detailMetaValue: { fontSize: 16, color: "#f1f5f9", fontWeight: "600" },
  bookButton: {
    backgroundColor: "#6366f1",
    paddingVertical: 14,
    borderRadius: 14,
    alignItems: "center",
  },
  bookButtonDisabled: { opacity: 0.6 },
  bookButtonText: { color: "#fff", fontSize: 16, fontWeight: "700" },
  formTitle: { fontSize: 20, fontWeight: "700", color: "#f8fafc", marginBottom: 16 },
  form: { gap: 12 },
  fieldLabel: { fontSize: 13, color: "#94a3b8", fontWeight: "600", marginBottom: -4 },
  fieldInput: {
    backgroundColor: "#1e293b",
    color: "#f1f5f9",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 12,
    fontSize: 15,
  },
  fieldMultiline: { minHeight: 70, textAlignVertical: "top" },
  errorText: { color: "#fca5a5", fontSize: 13, marginBottom: 8 },
  emptyText: { color: "#64748b", fontSize: 15, textAlign: "center", marginBottom: 16 },
  emptyState: { alignItems: "center", paddingTop: 40 },
  apptHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  statusText: { fontSize: 12, fontWeight: "700", textTransform: "uppercase" },
  apptDate: { fontSize: 14, color: "#94a3b8", marginBottom: 8 },
  acceptedNote: { fontSize: 13, color: "#86efac", marginTop: 4 },
  declinedNote: { fontSize: 13, color: "#fca5a5", marginTop: 4 },
  cancelButton: {
    backgroundColor: "#1e293b",
    borderWidth: 1,
    borderColor: "#ef4444",
    paddingVertical: 10,
    borderRadius: 10,
    alignItems: "center",
    marginTop: 8,
  },
  cancelButtonText: { color: "#ef4444", fontSize: 14, fontWeight: "600" },
});
