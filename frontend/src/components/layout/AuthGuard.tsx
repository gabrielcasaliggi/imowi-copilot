"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { getToken } from "@/lib/storage";

export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { ready, user } = useApp();

  useEffect(() => {
    if (!ready) return;
    if (!getToken() || !user) router.replace("/login");
  }, [ready, user, router]);

  if (!ready || !user) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-slate-500 font-mono text-sm">Cargando sesión…</p>
      </div>
    );
  }

  return <>{children}</>;
}
