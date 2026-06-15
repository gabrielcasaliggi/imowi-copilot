import { clearToken, getToken } from "./storage";
import type {
  ChatV1Response,
  DemoEscenariosResponse,
  ExecutiveAnalytics,
  KBSuggestion,
  TicketLearning,
  KBArticle,
  AdminUser,
  ImportCsvResult,
  LoginResponse,
  MeResponse,
  Organization,
  PilotMetricas,
  StatsResponse,
  TelemetryElement,
  TenantContext,
  Ticket,
  TicketEvent,
  TicketNotification,
} from "./types";

const API_BASE =
  (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

type RequestOpts = RequestInit & {
  tenantSlug?: string;
  skipAuth?: boolean;
};

let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

async function request<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(opts.headers as Record<string, string>),
  };

  if (!opts.skipAuth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (opts.tenantSlug) headers["X-Tenant-Slug"] = opts.tenantSlug;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers,
  });

  if (res.status === 401) {
    clearToken();
    onUnauthorized?.();
    throw new ApiError("Sesión expirada", 401);
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail =
      typeof err.detail === "string"
        ? err.detail
        : Array.isArray(err.detail)
          ? err.detail.map((d: { msg?: string }) => d.msg).join(", ")
          : res.statusText;
    throw new ApiError(detail || res.statusText, res.status);
  }

  return res.json() as Promise<T>;
}

export const api = {
  login(usuario: string, password: string) {
    return request<LoginResponse>("/api/login", {
      method: "POST",
      body: JSON.stringify({ usuario, password }),
      skipAuth: true,
    });
  },

  me() {
    return request<MeResponse>("/api/me");
  },

  tenants() {
    return request<{ organizaciones: Organization[] }>("/api/v1/tenants");
  },

  sessionContext(tenantSlug?: string) {
    return request<TenantContext>("/api/v1/session/context", { tenantSlug });
  },

  chat(
    body: {
      historial: { rol: string; contenido: string }[];
      mensaje: string;
      forzar_escalamiento?: boolean;
      session_id: string;
      accion_operador?: string;
    },
    tenantSlug?: string,
  ) {
    return request<ChatV1Response>("/api/v1/chat", {
      method: "POST",
      body: JSON.stringify(body),
      tenantSlug,
    });
  },

  tickets(tenantSlug?: string) {
    return request<{ tenant: string; tickets: Ticket[] }>("/api/v1/tickets", {
      tenantSlug,
    });
  },

  ticketDetail(id: string, tenantSlug?: string) {
    return request<{
      tenant: string;
      ticket: Ticket;
      timeline: TicketEvent[];
      tickets_similares?: import("./types").TicketSimilar[];
      kb_sugerencias?: KBSuggestion[];
      learning?: TicketLearning | null;
    }>(`/api/v1/tickets/${id}`, { tenantSlug });
  },

  updateTicket(
    id: string,
    body: Record<string, string>,
    tenantSlug?: string,
  ) {
    return request<{ status: string; ticket: Ticket }>(`/api/v1/tickets/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
      tenantSlug,
    });
  },

  notifications(tenantSlug?: string) {
    return request<{ tenant: string; notificaciones: TicketNotification[] }>(
      "/api/v1/tickets/notifications",
      { tenantSlug },
    );
  },

  telemetry(tenantSlug?: string) {
    return request<{ tenant: string; elementos: TelemetryElement[] }>(
      "/api/v1/telemetry",
      { tenantSlug },
    );
  },

  simulateTelemetry(elemento_red: string, tenantSlug?: string) {
    return request<{ status: string; reaccion_autonoma: ChatV1Response }>(
      "/api/v1/telemetry/simulate",
      {
        method: "POST",
        body: JSON.stringify({ elemento_red }),
        tenantSlug,
      },
    );
  },

  kb(tenantSlug?: string) {
    return request<{ tenant: string; articulos: KBArticle[] }>("/api/v1/kb", {
      tenantSlug,
    });
  },

  createKb(
    body: { titulo: string; categoria: string; contenido: string },
    tenantSlug?: string,
  ) {
    return request<{ status: string; articulo: KBArticle }>("/api/v1/kb", {
      method: "POST",
      body: JSON.stringify(body),
      tenantSlug,
    });
  },

  stats(params?: { desde?: string; hasta?: string }, tenantSlug?: string) {
    const qs = new URLSearchParams();
    if (params?.desde) qs.set("desde", params.desde);
    if (params?.hasta) qs.set("hasta", params.hasta);
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<StatsResponse>(`/api/v1/analytics/tickets${suffix}`, {
      tenantSlug,
    });
  },

  executiveAnalytics(tenantSlug?: string) {
    return request<ExecutiveAnalytics>("/api/v1/analytics/executive", { tenantSlug });
  },

  prioritizedTickets(tenantSlug?: string) {
    return request<{
      tenant: string;
      cola: { ticket: Ticket; intelligence: Ticket["intelligence"] }[];
    }>("/api/v1/tickets/prioritized", { tenantSlug });
  },

  explainEscalation(id: string, tenantSlug?: string) {
    return request<{ ticket_id: string; explicacion: string }>(
      `/api/v1/tickets/${id}/explain-escalation`,
      { tenantSlug },
    );
  },

  demoEscenarios(tenantSlug?: string) {
    return request<DemoEscenariosResponse>("/api/v1/demo/escenarios", { tenantSlug });
  },

  demoReset(incluirTickets = true, tenantSlug?: string) {
    return request<{
      status: string;
      tenant: string;
      casos_eliminados: number;
      tickets_eliminados: number;
      eventos_piloto_eliminados?: number;
    }>("/api/v1/demo/reset", {
      method: "POST",
      body: JSON.stringify({ incluir_tickets: incluirTickets }),
      tenantSlug,
    });
  },

  demoMetricas(tenantSlug?: string) {
    return request<{ tenant: string; metricas: PilotMetricas }>("/api/v1/demo/metricas", {
      tenantSlug,
    });
  },

  demoEvento(
    body: {
      tipo: string;
      session_id?: string;
      escenario_id?: string;
      categoria?: string;
      paso_id?: string;
      ticket_id?: string;
      detalle?: Record<string, unknown>;
    },
    tenantSlug?: string,
  ) {
    return request<{ status: string; evento: { id: string } }>("/api/v1/demo/evento", {
      method: "POST",
      body: JSON.stringify(body),
      tenantSlug,
    });
  },

  adminOrganizations() {
    return request<{ organizaciones: Organization[] }>("/api/v1/admin/organizations");
  },

  createOrganization(body: {
    nombre: string;
    slug?: string;
    logo_label?: string;
    brand_color?: string;
  }) {
    return request<{ status: string; organizacion: Organization }>(
      "/api/v1/admin/organizations",
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  updateOrganization(
    slug: string,
    body: { nombre?: string; logo_label?: string; brand_color?: string },
  ) {
    return request<{ status: string; organizacion: Organization }>(
      `/api/v1/admin/organizations/${slug}`,
      { method: "PUT", body: JSON.stringify(body) },
    );
  },

  adminUsers(slug: string) {
    return request<{ slug: string; usuarios: AdminUser[] }>(
      `/api/v1/admin/organizations/${slug}/users`,
    );
  },

  createAdminUser(
    slug: string,
    body: {
      email: string;
      nombre: string;
      password?: string;
      rol?: string;
      telefono?: string;
      linea_principal?: string;
    },
  ) {
    return request<{ status: string; usuario: AdminUser }>(
      `/api/v1/admin/organizations/${slug}/users`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  async importUsersCsv(slug: string, file: File): Promise<ImportCsvResult> {
    const headers: Record<string, string> = {};
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;

    const form = new FormData();
    form.append("file", file);

    const res = await fetch(`${API_BASE}/api/v1/admin/organizations/${slug}/import-csv`, {
      method: "POST",
      headers,
      body: form,
    });

    if (res.status === 401) {
      clearToken();
      onUnauthorized?.();
      throw new ApiError("Sesión expirada", 401);
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail =
        typeof err.detail === "string"
          ? err.detail
          : Array.isArray(err.detail)
            ? err.detail.map((d: { msg?: string }) => d.msg).join(", ")
            : res.statusText;
      throw new ApiError(detail || res.statusText, res.status);
    }

    return res.json() as Promise<ImportCsvResult>;
  },
};
