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

export type PortalAudioResult = {
  ok: boolean;
  transcripcion?: string;
  conversacion: InboxConversation | null;
  mensajes: InboxMessage[];
};
