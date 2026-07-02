"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { LogOut } from "lucide-react";

export function LogoutButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  const handleLogout = async () => {
    setBusy(true);
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
    router.refresh();
  };

  return (
    <button
      onClick={handleLogout}
      disabled={busy}
      className="flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-400 transition hover:border-slate-600 hover:text-slate-200 disabled:opacity-60"
    >
      <LogOut className="h-4 w-4" />
      Sign out
    </button>
  );
}
