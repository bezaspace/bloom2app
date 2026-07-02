"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Practitioner } from "@/lib/types";

export function SettingsForm({ practitioner }: { practitioner: Practitioner }) {
  const router = useRouter();
  const [form, setForm] = useState({
    full_name: practitioner.full_name,
    title: practitioner.title ?? "",
    specialization: practitioner.specialization ?? "",
    bio: practitioner.bio ?? "",
    email: practitioner.email ?? "",
    phone: practitioner.phone ?? "",
    years_experience: practitioner.years_experience?.toString() ?? "",
    consultation_fee: practitioner.consultation_fee?.toString() ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const payload: Record<string, unknown> = {};
      if (form.full_name !== practitioner.full_name) payload.full_name = form.full_name;
      if (form.title !== (practitioner.title ?? "")) payload.title = form.title || null;
      if (form.specialization !== (practitioner.specialization ?? "")) payload.specialization = form.specialization || null;
      if (form.bio !== (practitioner.bio ?? "")) payload.bio = form.bio || null;
      if (form.email !== (practitioner.email ?? "")) payload.email = form.email || null;
      if (form.phone !== (practitioner.phone ?? "")) payload.phone = form.phone || null;
      if (form.years_experience !== (practitioner.years_experience?.toString() ?? ""))
        payload.years_experience = form.years_experience ? Number(form.years_experience) : null;
      if (form.consultation_fee !== (practitioner.consultation_fee?.toString() ?? ""))
        payload.consultation_fee = form.consultation_fee ? Number(form.consultation_fee) : null;

      if (Object.keys(payload).length === 0) {
        setSaved(true);
        return;
      }

      const res = await fetch("/api/proxy/practitioner/auth/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Failed to update profile");
      }
      setSaved(true);
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900 p-6">
      <Field label="Full Name" value={form.full_name} onChange={set("full_name")} />
      <div className="grid grid-cols-2 gap-4">
        <Field label="Title" value={form.title} onChange={set("title")} />
        <Field label="Specialization" value={form.specialization} onChange={set("specialization")} />
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium text-slate-300">Bio</label>
        <textarea
          value={form.bio}
          onChange={set("bio")}
          rows={4}
          className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Email" value={form.email} onChange={set("email")} />
        <Field label="Phone" value={form.phone} onChange={set("phone")} />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Years of Experience" type="number" value={form.years_experience} onChange={set("years_experience")} />
        <Field label="Consultation Fee ($)" type="number" value={form.consultation_fee} onChange={set("consultation_fee")} />
      </div>
      {error && <div className="rounded-lg bg-red-900/40 px-4 py-2 text-sm text-red-200">{error}</div>}
      {saved && <div className="rounded-lg bg-emerald-900/40 px-4 py-2 text-sm text-emerald-200">Profile saved.</div>}
      <button
        type="submit"
        disabled={busy}
        className="rounded-lg bg-indigo-600 px-6 py-2.5 font-semibold text-white hover:bg-indigo-500 disabled:opacity-60"
      >
        {busy ? "Saving..." : "Save Changes"}
      </button>
    </form>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  type?: string;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-slate-300">{label}</label>
      <input
        type={type}
        value={value}
        onChange={onChange}
        className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
      />
    </div>
  );
}
