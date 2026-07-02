import { apiJson } from "@/lib/api";
import type { Practitioner } from "@/lib/types";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

/** Server component: fetches the current practitioner profile and wraps the
 * (app) route group in the sidebar + topbar shell. */
export async function AppShell({ children }: { children: React.ReactNode }) {
  let practitioner: Practitioner | null = null;
  try {
    const data = await apiJson<{ practitioner: Practitioner }>("/practitioner/me");
    practitioner = data.practitioner;
  } catch {
    // Token invalid or backend down — the proxy will redirect to /login on
    // next navigation. Render the shell without the profile.
  }

  return (
    <div className="flex min-h-screen bg-slate-950">
      <Sidebar />
      <div className="flex flex-1 flex-col">
        <Topbar practitioner={practitioner} />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
