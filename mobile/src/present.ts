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

export function parseAmount(raw?: string | null): number | null {
  const v = present(raw);
  if (!v) return null;
  const cleaned = v.replace(/[$\s]/g, "");
  const n = cleaned.includes(",")
    ? Number(cleaned.replace(/\./g, "").replace(",", "."))
    : Number(cleaned);
  if (!Number.isFinite(n)) return null;
  return n;
}

export function isZeroAmount(raw?: string | null): boolean {
  const n = parseAmount(raw);
  return n !== null && n === 0;
}

/** Presentación del monto que ya vino del backend. No inventa valores. */
export function formatMontoDisplay(
  raw?: string | null,
  opts?: { absolute?: boolean },
): string {
  const n = parseAmount(raw);
  if (n === null) return present(raw);
  const v = opts?.absolute ? Math.abs(n) : n;
  try {
    return new Intl.NumberFormat("es-AR", {
      style: "currency",
      currency: "ARS",
      maximumFractionDigits: 2,
    }).format(v);
  } catch {
    return present(raw);
  }
}

/** Estado administrativo del padrón. Desconocido → tal cual. */
export function labelEstadoAbonado(estado?: string | null): string {
  const raw = present(estado);
  if (!raw) return "";
  const key = raw.toLowerCase();
  if (key === "activo") return "Activo";
  if (key === "corte") return "Corte";
  if (key === "suspendido") return "Suspendido";
  if (key === "baja") return "Baja";
  return raw;
}

/** Labels de presentación para estados reales del estate. Desconocido → tal cual. */
export function labelTicketEstado(estado?: string | null): string {
  const raw = present(estado);
  if (!raw) return "Sin estado";
  if (raw === "Abierto") return "Abierto";
  if (raw === "En Revisión") return "En revisión";
  if (raw === "Cerrado") return "Cerrado";
  return raw;
}

export function formatTicketWhen(iso?: string | null): string {
  const raw = present(iso);
  if (!raw) return "";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  try {
    return new Intl.DateTimeFormat("es-AR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    }).format(d);
  } catch {
    return raw.slice(0, 10);
  }
}

/** Headline corto de UI. No redefine el status del backend. */
export function labelConnectivityStatus(
  status?: string | null,
): string {
  const s = present(status);
  if (s === "operational") return "Acceso en condiciones";
  if (s === "impaired") return "Problema en el acceso";
  if (s === "outage") return "Incidencia en la zona";
  if (s === "unknown") return "Sin verificación reciente";
  return s || "Estado de Internet";
}

/**
 * ETA solo si el backend confirmó. No inventa minutos.
 * freshness no altera el status.
 */
export function formatConnectivityEta(incident?: {
  eta_confirmed?: boolean;
  eta_minutes?: number | null;
  eta_at?: string | null;
} | null): string {
  if (!incident || !incident.eta_confirmed) return "";
  const mins = incident.eta_minutes;
  if (typeof mins === "number" && Number.isFinite(mins) && mins > 0) {
    return `Estimación de restitución: ${Math.round(mins)} min.`;
  }
  const at = present(incident.eta_at);
  if (!at) return "";
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return "";
  try {
    return `Estimación de restitución: ${new Intl.DateTimeFormat("es-AR", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(d)}`;
  } catch {
    return "";
  }
}

export function connectivityTone(
  status?: string | null,
): "ok" | "warning" | "neutral" | "outage" {
  const s = present(status);
  if (s === "operational") return "ok";
  if (s === "outage") return "outage";
  if (s === "impaired") return "warning";
  return "neutral";
}

