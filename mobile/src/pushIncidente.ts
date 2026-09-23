/**
 * Parseo de push (E′4 incidentes + 2.3G-M tickets).
 * Backend es la autoridad del contenido; mobile solo interpreta routing.
 * Nunca tratar title/body/data extra como verdad de ticket o outage.
 */

export type IncidentePushEvent = "declared" | "updated" | "resolved" | "";

export type IncidentePushPayload = {
  tipo: "incidente";
  outage_id: string;
  event: IncidentePushEvent;
};

/** Vocabulario canónico acordado (2.3G-M + 2.6A sla_breached). */
export type CanonicalTicketEvent =
  | "created"
  | "updated"
  | "resolved"
  | "closed"
  | "sla_breached"
  | "";

export type TicketPushPayload = {
  tipo: "ticket";
  ticket_id: string;
  event: CanonicalTicketEvent;
};

export type PushOpenIntent = {
  tab: "home" | "eko" | "activity" | "account";
  /** Si true, Home debe reconsultar GET /portal/connectivity (verdad actual). */
  refreshConnectivity: boolean;
  outage_id: string;
  /** Referencia de navegación; la API autenticada es la autoridad. */
  ticket_id: string;
};

function asRecord(raw: unknown): Record<string, unknown> {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  return {};
}

function normalizeIncidenteEvent(raw: unknown): IncidentePushEvent {
  const e = String(raw || "")
    .trim()
    .toLowerCase();
  if (e === "declared" || e === "create" || e === "created") return "declared";
  if (e === "updated" || e === "update") return "updated";
  if (e === "resolved" || e === "resolve") return "resolved";
  return "";
}

function normalizeTicketEvent(raw: unknown): CanonicalTicketEvent {
  const e = String(raw || "")
    .trim()
    .toLowerCase();
  // Acepta ticket.created o created (payload mínimo).
  const bare = e.startsWith("ticket.") ? e.slice("ticket.".length) : e;
  if (bare === "created" || bare === "create") return "created";
  if (bare === "updated" || bare === "update") return "updated";
  if (bare === "resolved" || bare === "resolve") return "resolved";
  if (bare === "closed" || bare === "close") return "closed";
  if (bare === "sla_breached" || bare === "sla-breached") return "sla_breached";
  return "";
}

function emptyIntent(
  partial: Partial<PushOpenIntent> & Pick<PushOpenIntent, "tab">,
): PushOpenIntent {
  return {
    refreshConnectivity: false,
    outage_id: "",
    ticket_id: "",
    ...partial,
  };
}

/** Extrae contrato incidente si tipo=incidente. No usa title/body. */
export function parseIncidentePush(raw: unknown): IncidentePushPayload | null {
  const data = asRecord(raw);
  const tipo = String(data.tipo || "").trim().toLowerCase();
  if (tipo !== "incidente") return null;
  const outage_id = String(data.outage_id || data.outageId || "").trim();
  return {
    tipo: "incidente",
    outage_id,
    event: normalizeIncidenteEvent(data.event),
  };
}

/** Extrae contrato ticket si tipo=ticket. Solo ids de navegación. */
export function parseTicketPush(raw: unknown): TicketPushPayload | null {
  const data = asRecord(raw);
  const tipo = String(data.tipo || "").trim().toLowerCase();
  if (tipo !== "ticket") return null;
  const ticket_id = String(data.ticket_id || data.ticketId || "").trim();
  return {
    tipo: "ticket",
    ticket_id,
    event: normalizeTicketEvent(data.event),
  };
}

/**
 * Intent de apertura desde data del push.
 * ticket → Activity (+ ticket_id si existe).
 * mensaje_agente / conversacion_id → Eko.
 * incidente → Home + refresh Connectivity.
 */
export function intentFromPushData(raw: unknown): PushOpenIntent {
  const data = asRecord(raw);
  const tipo = String(data.tipo || "").trim().toLowerCase();

  // Ticket primero: no confundir con conversacion_id colateral.
  const ticket = parseTicketPush(raw);
  if (ticket) {
    return emptyIntent({
      tab: "activity",
      ticket_id: ticket.ticket_id,
    });
  }

  const convId = String(data.conversacion_id || "").trim();
  if (tipo === "mensaje_agente" || convId) {
    return emptyIntent({ tab: "eko" });
  }

  const incidente = parseIncidentePush(raw);
  if (incidente) {
    return emptyIntent({
      tab: "home",
      refreshConnectivity: true,
      outage_id: incidente.outage_id,
    });
  }

  return emptyIntent({ tab: "home" });
}
