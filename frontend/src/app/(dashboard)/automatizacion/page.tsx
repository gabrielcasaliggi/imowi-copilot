"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AutomationPanel } from "@/components/automation/AutomationPanel";
import { useApp } from "@/contexts/AppContext";

export default function AutomatizacionPage() {
  const { isAdmin } = useApp();
  const router = useRouter();

  useEffect(() => {
    if (!isAdmin) router.replace("/soporte");
  }, [isAdmin, router]);

  if (!isAdmin) return null;

  return <AutomationPanel />;
}
