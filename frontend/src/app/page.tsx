"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/storage";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getToken() ? "/soporte" : "/login");
  }, [router]);

  return (
    <div className="flex-1 flex items-center justify-center">
      <p className="text-slate-500 font-mono text-sm">Cargando…</p>
    </div>
  );
}
