"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AdminPanel } from "@/components/admin/AdminPanel";
import { useApp } from "@/contexts/AppContext";

export default function AdminPage() {
  const { isAdmin, ready } = useApp();
  const router = useRouter();

  useEffect(() => {
    if (ready && !isAdmin) router.replace("/inbox");
  }, [isAdmin, ready, router]);

  if (!ready) {
    return (
      <div className="flex-1 flex items-center justify-center p-8" role="status">
        <p className="text-sm text-slate-400">Cargando administración…</p>
      </div>
    );
  }

  if (!isAdmin) {
    return (
      <div className="flex-1 flex items-center justify-center p-8" role="status">
        <p className="text-sm text-slate-400">Sin permiso · redirigiendo…</p>
      </div>
    );
  }

  return <AdminPanel />;
}
