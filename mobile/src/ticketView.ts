/**
 * Presentación de reclamos para el abonado. Lógica pura (sin React ni módulos nativos):
 * la prueba scripts/verify-ticket-view.mjs con Node.
 *
 * El backend ya manda `titulo` legible y eventos con textos fijos. Lo de acá solo cubre
 * respuestas viejas o incompletas: nunca muestra un código interno crudo.
 */
import type { PortalTicket, PortalTicketEvent } from "./types";

function txt(value?: string | null): string {
  return (value || "").trim();
}

/** Estado del estate → etiqueta para el abonado. Cualquier otro valor (o vacío) → "En curso". */
const ESTADOS: Record<string, string> = {
  Abierto: "Recibido",
  "En Revisión": "En revisión",
  Escalado: "En curso",
  "Pendiente Cliente": "Esperando tu respuesta",
  Cerrado: "Cerrado",
};

export function ticketStatusLabel(estado?: string | null): string {
  return ESTADOS[txt(estado)] ?? "En curso";
}

export function isTicketClosed(estado?: string | null): boolean {
  return txt(estado) === "Cerrado";
}

export const TICKET_TITLE_FALLBACK = "Reclamo";

/** Mismas etiquetas que app/api/v1/portal_ticket_view.py (TITULOS_CATEGORIA). */
const TITULOS_CATEGORIA: Record<string, string> = {
  movil_llamadas: "Llamadas en tu línea móvil",
  movil_datos: "Datos móviles",
  corte_deuda: "Consulta por corte del servicio",
  internet_lento: "Internet lento",
  facturacion_reclamo: "Reclamo de factura",
  voz: "Llamadas",
  "apn_/_datos": "Datos móviles",
  internet: "Internet",
  fibra: "Internet por fibra",
  roaming: "Roaming",
  "red_/_core": "Problema en la red",
};

/** Igual que el backend: minúsculas, sin tildes, espacios a "_". */
export function normalizeCategory(raw?: string | null): string {
  return txt(raw)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .join("_");
}

/** `titulo` del backend; si falta, mapa local; si no hay etiqueta, "Reclamo". */
export function ticketTitle(ticket: Pick<PortalTicket, "titulo" | "categoria">): string {
  const fromApi = txt(ticket.titulo);
  if (fromApi) return fromApi;
  return TITULOS_CATEGORIA[normalizeCategory(ticket.categoria)] ?? TICKET_TITLE_FALLBACK;
}

export function ticketReference(id?: string | null): string {
  const ref = txt(id);
  return ref ? `Reclamo ${ref}` : TICKET_TITLE_FALLBACK;
}

/** Último movimiento que trajo la lista; sin dato no se inventa nada. */
export function lastMovementTitle(ticket: Pick<PortalTicket, "ultimo_movimiento">): string {
  return txt(ticket.ultimo_movimiento?.titulo);
}

/** Eventos de más viejo a más nuevo (orden estable; los que no tienen fecha van al principio). */
export function timelineEvents(eventos?: PortalTicketEvent[] | null): PortalTicketEvent[] {
  return [...(eventos || [])]
    .map((ev, i) => ({ ev, i }))
    .sort((a, b) => {
      const ta = txt(a.ev.created_at);
      const tb = txt(b.ev.created_at);
      if (ta === tb) return a.i - b.i;
      return ta < tb ? -1 : 1;
    })
    .map(({ ev }) => ev);
}

/** Título visible de un evento: el fijo del backend, o "Actualización" si faltara. */
export function eventTitle(ev: Pick<PortalTicketEvent, "titulo">): string {
  return txt(ev.titulo) || "Actualización";
}

/** "10 oct 2026, 14:32" en hora local; vacío si no hay fecha válida. */
export function formatTicketMoment(iso?: string | null): string {
  const raw = txt(iso);
  if (!raw) return "";
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return "";
  try {
    return new Intl.DateTimeFormat("es-AR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return raw.slice(0, 16).replace("T", " ");
  }
}
