"use client";

import { getBranding } from "@/lib/brand";

/** Avatar visual del asistente virtual N1 (Eko). No usar en Copilot NOC. */
export function EkoAvatar({ className = "h-7 w-7" }: { className?: string }) {
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

/** @deprecated Usar EkoAvatar */
export const EcoAvatar = EkoAvatar;
