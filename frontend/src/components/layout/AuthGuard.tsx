"use client";

import { useEffect, type ReactNode } from "react";
import { useApp } from "@/contexts/AppContext";
import { getToken } from "@/lib/storage";

export function AuthGuard({ children }: { children: ReactNode }) {
  const { ready, user } = useApp();

  useEffect(() => {
    if (!ready) return;
    if (!getToken() || !user) window.location.replace("/login");
  }, [ready, user]);

  if (!ready) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-slate-500 font-mono text-sm">Cargando sesión…</p>
      </div>
    );
  }

  if (!getToken() || !user) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-slate-500 font-mono text-sm">Redirigiendo…</p>
      </div>
    );
  }

  return <>{children}</>;
}
