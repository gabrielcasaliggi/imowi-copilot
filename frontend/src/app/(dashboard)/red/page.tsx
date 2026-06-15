"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { TelemetryGrid } from "@/components/red/TelemetryGrid";
import { useApp } from "@/contexts/AppContext";

export default function RedPage() {
  const { isAdmin } = useApp();
  const router = useRouter();

  useEffect(() => {
    if (!isAdmin) router.replace("/soporte");
  }, [isAdmin, router]);

  if (!isAdmin) return null;

  return <TelemetryGrid />;
}
