/** Formato de tiempos relativos/absolutos para UI operativa (es-AR). */

function parseWhen(iso: string | undefined | null): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "hace 3 min", "hace 2 h", "ayer", o fecha corta. */
export function formatRelative(iso: string | undefined | null, now = Date.now()): string {
  const d = parseWhen(iso);
  if (!d) return "";
  const diffMs = Math.max(0, now - d.getTime());
  const sec = Math.floor(diffMs / 1000);
  if (sec < 45) return "ahora";
  const min = Math.floor(sec / 60);
  if (min < 60) return `hace ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `hace ${h} h`;
  const days = Math.floor(h / 24);
  if (days === 1) return "ayer";
  if (days < 7) return `hace ${days} d`;
  return d.toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit" });
}

/** Fecha/hora absoluta corta para tooltip: "06/08/2026 14:32". */
export function formatDateTime(iso: string | undefined | null): string {
  const d = parseWhen(iso);
  if (!d) return "";
  return d.toLocaleString("es-AR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Minutos de espera desde un ISO (para chip "Espera · 12m"). */
export function waitMinutes(iso: string | undefined | null, now = Date.now()): number {
  const d = parseWhen(iso);
  if (!d) return 0;
  return Math.max(0, Math.floor((now - d.getTime()) / 60_000));
}

export function formatWaitChip(iso: string | undefined | null, now = Date.now()): string {
  const m = waitMinutes(iso, now);
  if (m < 1) return "Espera · <1m";
  if (m < 60) return `Espera · ${m}m`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  return rest ? `Espera · ${h}h ${rest}m` : `Espera · ${h}h`;
}

/**
 * Countdown SLA restante.
 * Acepta ISO due_at o horas restantes numéricas (puede ser negativo si venció).
 */
export function formatSlaRemaining(
  opts: {
    slaDueAt?: string | null;
    horasRestantes?: number | null;
  },
  now = Date.now(),
): string {
  const due = parseWhen(opts.slaDueAt);
  if (due) {
    const diffMs = due.getTime() - now;
    const absMin = Math.floor(Math.abs(diffMs) / 60_000);
    if (diffMs < 0) {
      if (absMin < 60) return `SLA −${absMin}m`;
      const h = Math.floor(absMin / 60);
      const m = absMin % 60;
      return m ? `SLA −${h}h ${m}m` : `SLA −${h}h`;
    }
    if (absMin < 1) return "SLA <1m";
    if (absMin < 60) return `SLA ${absMin}m`;
    const h = Math.floor(absMin / 60);
    const m = absMin % 60;
    return m ? `SLA ${h}h ${m}m` : `SLA ${h}h`;
  }
  const hr = opts.horasRestantes;
  if (hr == null || Number.isNaN(hr)) return "";
  const absMin = Math.round(Math.abs(hr) * 60);
  if (hr < 0) {
    if (absMin < 60) return `SLA −${absMin}m`;
    const h = Math.floor(absMin / 60);
    return `SLA −${h}h`;
  }
  if (absMin < 1) return "SLA <1m";
  if (absMin < 60) return `SLA ${absMin}m`;
  const h = Math.floor(absMin / 60);
  const m = absMin % 60;
  return m ? `SLA ${h}h ${m}m` : `SLA ${h}h`;
}

