"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { KnowledgeBasePanel } from "@/components/kb/KnowledgeBasePanel";
import { useApp } from "@/contexts/AppContext";

export default function ConocimientoPage() {
  const { isAdmin } = useApp();
  const router = useRouter();

  useEffect(() => {
    if (!isAdmin) router.replace("/soporte");
  }, [isAdmin, router]);

  if (!isAdmin) return null;

  return <KnowledgeBasePanel />;
}
