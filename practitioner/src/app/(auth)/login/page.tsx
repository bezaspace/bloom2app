"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Login failed");
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
      <h1 className="text-2xl font-bold text-slate-50">Bloom2 Practitioner</h1>
      <p className="mt-1 text-sm text-slate-400">Sign in to your practitioner account</p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-300">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-slate-100 outline-none focus:border-indigo-500"
            autoComplete="username"
            required
          />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-300">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2.5 text-slate-100 outline-none focus:border-indigo-500"
            autoComplete="current-password"
            required
          />
        </div>
        {error && (
          <div className="rounded-lg bg-red-900/40 px-4 py-2 text-sm text-red-200">{error}</div>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-indigo-600 py-2.5 font-semibold text-white transition hover:bg-indigo-500 disabled:opacity-60"
        >
          {busy ? "Signing in..." : "Sign In"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-400">
        Don&apos;t have an account?{" "}
        <Link href="/register" className="font-medium text-indigo-400 hover:text-indigo-300">
          Register
        </Link>
      </p>

      <div className="mt-6 rounded-lg border border-slate-800 bg-slate-800/50 px-4 py-3 text-xs text-slate-400">
        <p className="font-semibold text-slate-300">Demo practitioner login</p>
        <p className="mt-1">username: <code className="text-slate-200">dranya</code> · password: <code className="text-slate-200">demodemo</code></p>
      </div>
    </div>
  );
}
