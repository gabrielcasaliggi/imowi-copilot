"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { StatsDashboard } from "@/components/stats/StatsDashboard";
import { useApp } from "@/contexts/AppContext";

export default function EstadisticasPage() {
  const { can } = useApp();
  const router = useRouter();
  const allowed =
    can("stats.global") ||
    can("stats.bot") ||
    can("stats.agents") ||
    can("stats.self");

  useEffect(() => {
    if (!allowed) router.replace("/inbox");
  }, [allowed, router]);

  if (!allowed) return null;

  return <StatsDashboard />;
}
