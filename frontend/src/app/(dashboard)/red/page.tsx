"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Monitor de red (JSC/telemetría) fuera de la UX Batán. */
export default function RedPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/inbox");
  }, [router]);
  return null;
}
