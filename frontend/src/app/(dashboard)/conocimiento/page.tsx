"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { KnowledgeBasePanel } from "@/components/kb/KnowledgeBasePanel";
import { useApp } from "@/contexts/AppContext";

/** Centro KB completo: solo quien puede publicar/revisar. El agente propone desde la Consola. */
export default function ConocimientoPage() {
  const { can, ready } = useApp();
  const router = useRouter();
  const allowed = can("kb.publish");

  useEffect(() => {
    if (!ready) return;
    if (!allowed) router.replace("/soporte");
  }, [ready, allowed, router]);

  if (!ready || !allowed) return null;

  return <KnowledgeBasePanel />;
}
