"use client";

/** Avatar visual del asistente virtual N1 (Eko). No usar en Copilot NOC. */
export function EkoAvatar({
  className = "h-7 w-7",
  alt,
}: {
  className?: string;
  alt?: string;
}) {
  const decorative = !alt;
  return (
    <img
      src="/eko-avatar.png"
      alt={alt ?? ""}
      className={`inline-block shrink-0 rounded-full object-cover ${className}`}
      aria-hidden={decorative || undefined}
    />
  );
}

/** @deprecated Usar EkoAvatar */
export const EcoAvatar = EkoAvatar;
