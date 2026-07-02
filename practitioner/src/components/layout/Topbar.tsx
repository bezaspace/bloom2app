import type { Practitioner } from "@/lib/types";
import { LogoutButton } from "./LogoutButton";

export function Topbar({ practitioner }: { practitioner: Practitioner | null }) {
  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-800 bg-slate-900 px-6">
      <div>
        {practitioner && (
          <p className="text-sm font-semibold text-slate-200">
            {practitioner.full_name}
            {practitioner.title && (
              <span className="ml-2 text-xs font-normal text-indigo-400">{practitioner.title}</span>
            )}
          </p>
        )}
        {practitioner?.specialization && (
          <p className="text-xs text-slate-500">{practitioner.specialization}</p>
        )}
      </div>
      <LogoutButton />
    </header>
  );
}
