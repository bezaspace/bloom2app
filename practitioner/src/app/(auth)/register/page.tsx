"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { withBasePath } from "@/lib/basePath";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    username: "",
    password: "",
    full_name: "",
    title: "",
    specialization: "",
    bio: "",
    email: "",
    phone: "",
    years_experience: "",
    consultation_fee: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        username: form.username,
        password: form.password,
        full_name: form.full_name,
      };
      if (form.title) payload.title = form.title;
      if (form.specialization) payload.specialization = form.specialization;
      if (form.bio) payload.bio = form.bio;
      if (form.email) payload.email = form.email;
      if (form.phone) payload.phone = form.phone;
      if (form.years_experience) payload.years_experience = Number(form.years_experience);
      if (form.consultation_fee) payload.consultation_fee = Number(form.consultation_fee);

      const res = await fetch(withBasePath("/api/auth/register"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Registration failed");
      }
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl bg-slate-900 p-8 shadow-xl">
      <h1 className="text-2xl font-bold text-slate-50">Create Practitioner Account</h1>
      <p className="mt-1 text-sm text-slate-400">Join Bloom2 to connect with patients</p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Username *" value={form.username} onChange={set("username")} required />
          <Field label="Password *" type="password" value={form.password} onChange={set("password")} required />
        </div>
        <Field label="Full Name *" value={form.full_name} onChange={set("full_name")} required />
        <div className="grid grid-cols-2 gap-4">
          <Field label="Title (e.g. MD)" value={form.title} onChange={set("title")} />
          <Field label="Specialization" value={form.specialization} onChange={set("specialization")} />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-300">Bio</label>
          <textarea
            value={form.bio}
            onChange={set("bio")}
            rows={3}
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-slate-100 outline-none focus:border-indigo-500"
          />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Email" type="email" value={form.email} onChange={set("email")} />
          <Field label="Phone" value={form.phone} onChange={set("phone")} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Years of Experience" type="number" value={form.years_experience} onChange={set("years_experience")} />
          <Field label="Consultation Fee ($)" type="number" value={form.consultation_fee} onChange={set("consultation_fee")} />
        </div>
        {error && (
          <div className="rounded-lg bg-red-900/40 px-4 py-2 text-sm text-red-200">{error}</div>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-indigo-600 py-2.5 font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-60"
        >
          {busy ? "Creating account..." : "Register"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-400">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-indigo-400 hover:text-indigo-300">
          Sign in
        </Link>
      </p>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  required,
}: {
  label: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  type?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-slate-300">{label}</label>
      <input
        type={type}
        value={value}
        onChange={onChange}
        required={required}
        className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-slate-100 outline-none focus:border-indigo-500"
      />
    </div>
  );
}
