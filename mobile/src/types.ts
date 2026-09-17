export type InboxAbonado = {
  id: string;
  dni: string;
  telefono_e164: string;
  nombre: string;
  servicio: string;
  estado: string;
  deuda_monto?: string;
  plan?: string;
  client_number?: string;
  linea_msisdn?: string;
};

export type InboxConversation = {
  id: string;
  canal: string;
  canal_display?: string;
  estado: string;
  ticket_id: string;
  contexto?: Record<string, unknown>;
  abonado?: InboxAbonado | null;
  servicio_detectado?: string;
  updated_at?: string;
};

export type InboxMessage = {
  id: string;
  conversacion_id: string;
  direccion: string;
  autor: string;
  texto: string;
  created_at: string;
};

export type AuthPayload = {
  portal_token: string;
  org_slug: string;
  abonado_identificado: boolean;
  has_pin?: boolean;
  conversacion: InboxConversation;
  mensajes: InboxMessage[];
  contact_masked?: string;
};

export type AppTab = "home" | "eko" | "activity" | "account";

export type VoicePhase = "idle" | "recording" | "processing";

export type PortalTicket = {
  id: string;
  estado: string;
  categoria: string;
  origen: string;
  created_at: string;
  updated_at: string;
  conversacion_id: string;
};

export type PortalTicketEvent = {
  id: string;
  titulo: string;
  detalle: string;
  estado: string;
  created_at: string;
};

export type PortalTicketDetail = {
  ticket: PortalTicket;
  eventos: PortalTicketEvent[];
};

export type PortalAudioResult = {
  ok: boolean;
  transcripcion?: string;
  conversacion: InboxConversation | null;
  mensajes: InboxMessage[];
};

/** Contrato GET /portal/connectivity — sin campos de infraestructura. */
export type ConnectivityStatus =
  | "operational"
  | "impaired"
  | "outage"
  | "unknown";

export type ConnectivityFreshness = "live" | "cached" | "stale" | "none";

export type ConnectivityAccessTechnology =
  | "ftth"
  | "radio"
  | "other"
  | "unknown";

export type ConnectivityReasonCode =
  | "incident_active"
  | "access_link_down"
  | "no_session"
  | "link_quality_poor"
  | "insufficient_data"
  | "sources_unavailable"
  | "service_selection_required";

export type ConnectivityIncident = {
  id: string;
  started_at: string;
  eta_minutes: number | null;
  eta_confirmed: boolean;
  eta_at: string | null;
  message: string;
  scope: string;
};

export type ConnectivityServiceOption = {
  id: string;
  label: string;
  access_technology: ConnectivityAccessTechnology;
};

export type ConnectivityServiceSummary = {
  id: string;
  label: string;
};

export type ConnectivityActions = {
  can_open_chat: boolean;
  chat_hint?: string;
};

export type ConnectivityStatusResponse = {
  status: ConnectivityStatus;
  freshness: ConnectivityFreshness;
  checked_at: string;
  message: string;
  access_technology: ConnectivityAccessTechnology;
  service: ConnectivityServiceSummary | null;
  incident: ConnectivityIncident | null;
  actions: ConnectivityActions;
  needs_service_selection: boolean;
  services: ConnectivityServiceOption[] | null;
  reason_code: ConnectivityReasonCode | null;
};

/** Contrato GET /portal/ov-links — sin secretos ni payload OV crudo. */
export type OvLinkStatus = "ready" | "partial" | "unavailable" | "unknown";

export type OvLinkId = "pay" | "invoice" | "payment_slip";

export type OvLinkReasonCode =
  | "ov_unavailable"
  | "partial"
  | "insufficient_data";

export type OvLinkItem = {
  id: OvLinkId;
  label: string;
  url: string | null;
  available: boolean;
};

export type OvLinksActions = {
  can_open_chat: boolean;
  chat_hint?: string;
};

export type OvLinksResponse = {
  status: OvLinkStatus;
  checked_at: string;
  actions: OvLinksActions;
  links: OvLinkItem[];
  reason_code: OvLinkReasonCode | null;
};

/** Contrato GET /portal/services — catálogo administrativo (no operativo). */
export type PortalServiceType =
  | "internet"
  | "tv"
  | "movil"
  | "telefonia"
  | "other";

export type PortalServiceItem = {
  id: string;
  type: PortalServiceType;
  label: string;
  product: string | null;
  active: boolean;
  /** MSISDN de la línea (móvil); null si BillTrack no lo trae en identifier. */
  msisdn?: string | null;
};

export type PortalServicesResponse = {
  status: "ok" | "unavailable";
  checked_at: string;
  services: PortalServiceItem[];
  reason_code: string | null;
};
