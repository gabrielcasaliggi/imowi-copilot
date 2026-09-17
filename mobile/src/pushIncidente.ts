/**
 * Parseo de push de incidentes (E′4).
 * Backend es la autoridad; mobile solo interpreta routing + outage_id.
 */

export type IncidentePushEvent = "declared" | "updated" | "resolved" | "";

export type IncidentePushPayload = {
  tipo: "incidente";
  outage_id: string;
  event: IncidentePushEvent;
};

export type PushOpenIntent = {
  tab: "home" | "eko" | "activity" | "account";
  /** Si true, Home debe reconsultar GET /portal/connectivity (verdad actual). */
  refreshConnectivity: boolean;
  outage_id: string;
};

function asRecord(raw: unknown): Record<string, unknown> {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  return {};
}

function normalizeEvent(raw: unknown): IncidentePushEvent {
  const e = String(raw || "")
    .trim()
    .toLowerCase();
  if (e === "declared" || e === "create" || e === "created") return "declared";
  if (e === "updated" || e === "update") return "updated";
  if (e === "resolved" || e === "resolve") return "resolved";
  return "";
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
    event: normalizeEvent(data.event),
  };
}

/**
 * Intent de apertura desde data del push.
 * incidente → Home + refresh Connectivity (declared/updated/resolved).
 * mensaje_agente / conversacion_id → Eko.
 */
export function intentFromPushData(raw: unknown): PushOpenIntent {
  const data = asRecord(raw);
  const convId = String(data.conversacion_id || "").trim();
  const tipo = String(data.tipo || "").trim().toLowerCase();
  if (tipo === "mensaje_agente" || convId) {
    return { tab: "eko", refreshConnectivity: false, outage_id: "" };
  }
  const incidente = parseIncidentePush(raw);
  if (incidente) {
    return {
      tab: "home",
      refreshConnectivity: true,
      outage_id: incidente.outage_id,
    };
  }
  return { tab: "home", refreshConnectivity: false, outage_id: "" };
}
