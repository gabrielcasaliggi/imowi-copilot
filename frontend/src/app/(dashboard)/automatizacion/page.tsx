"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Automatización JSC demo fuera de la UX Batán. */
export default function AutomatizacionPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/inbox");
  }, [router]);
  return null;
}
