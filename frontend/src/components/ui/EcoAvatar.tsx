"use client";

import { getBranding } from "@/lib/brand";

/** Avatar visual del asistente N1 (Eco). No usar en Copilot NOC. */
export function EcoAvatar({ className = "h-7 w-7" }: { className?: string }) {
  const letter = (getBranding().botDisplayName.trim().charAt(0) || "E").toUpperCase();
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white shadow-sm shadow-ecolan-brand/25 ${className}`}
      style={{ background: "linear-gradient(135deg, #2298A6, #1A7985)" }}
      aria-hidden
    >
      {letter}
    </span>
  );
}
