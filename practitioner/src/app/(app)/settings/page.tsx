import { apiJson } from "@/lib/api";
import type { Practitioner } from "@/lib/types";
import { SettingsForm } from "@/components/patients/SettingsForm";

export default async function SettingsPage() {
  let practitioner: Practitioner | null = null;
  let loadError: string | null = null;
  try {
    const data = await apiJson<{ practitioner: Practitioner }>("/practitioner/me");
    practitioner = data.practitioner;
  } catch (e) {
    loadError = e instanceof Error ? e.message : String(e);
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-2xl font-bold text-slate-50">Settings</h1>
      {loadError && (
        <div className="rounded-lg bg-red-900/40 px-4 py-3 text-sm text-red-200">
          Failed to load profile: {loadError}
        </div>
      )}
      {practitioner && <SettingsForm practitioner={practitioner} />}
    </div>
  );
}
