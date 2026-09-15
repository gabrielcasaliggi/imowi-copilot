/** Helpers de presentación. No interpretan planta ni inventan campos. */

export function present(value?: string | null): string {
  return (value || "").trim();
}

export function firstName(nombre?: string | null): string {
  const full = present(nombre);
  if (!full) return "";
  return full.split(/\s+/)[0] || "";
}

/** Etiqueta de servicio conocida; cualquier otro valor se muestra tal cual. */
export function labelServicio(servicio?: string | null): string {
  const raw = present(servicio);
  if (!raw) return "";
  const key = raw.toLowerCase();
  if (key === "internet") return "Internet";
  if (key === "movil") return "Móvil";
  if (key === "ambos") return "Internet y móvil";
  return raw;
}

export function isZeroAmount(raw?: string | null): boolean {
  const v = present(raw);
  if (!v) return false;
  const cleaned = v.replace(/[$\s]/g, "");
  const n = cleaned.includes(",")
    ? Number(cleaned.replace(/\./g, "").replace(",", "."))
    : Number(cleaned);
  if (!Number.isFinite(n)) return false;
  return n === 0;
}
