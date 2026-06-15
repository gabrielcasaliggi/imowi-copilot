"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { StatsDashboard } from "@/components/stats/StatsDashboard";
import { useApp } from "@/contexts/AppContext";

export default function EstadisticasPage() {
  const { isAdmin } = useApp();
  const router = useRouter();

  useEffect(() => {
    if (!isAdmin) router.replace("/soporte");
  }, [isAdmin, router]);

  if (!isAdmin) return null;

  return <StatsDashboard />;
}
