"use client";

import { useEffect, type ReactNode } from "react";
import { useApp } from "@/contexts/AppContext";

export function AuthGuard({ children }: { children: ReactNode }) {
  const { ready, user } = useApp();

  useEffect(() => {
    if (!ready) return;
    if (!user) window.location.replace("/login");
  }, [ready, user]);

  if (!ready) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3" role="status" aria-live="polite">
          <div
            className="h-8 w-8 rounded-full border-2 border-slate-700 border-t-[var(--brand)] animate-spin"
            aria-hidden
          />
          <p className="text-slate-400 text-sm">Cargando sesión…</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-slate-500 font-mono text-sm">Redirigiendo…</p>
      </div>
    );
  }

  return <>{children}</>;
}
