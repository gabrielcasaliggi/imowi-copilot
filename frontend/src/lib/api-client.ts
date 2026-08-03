import { clearToken, getToken } from "./storage";
import type {
  ChatV1Response,
  DemoEscenariosResponse,
  ExecutiveAnalytics,
  KBSuggestion,
  TicketLearning,
  KBArticle,
  KBContribution,
  AdminUser,
  AuditEvent,
  ImportCsvResult,
  LoginResponse,
  MeResponse,
  Organization,
  PilotMetricas,
  PlatformSettingsResponse,
  StatsResponse,
  TelemetryElement,
  TenantContext,
  Ticket,
  TicketEvent,
  TicketNotification,
} from "./types";

const API_BASE =
  (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

/** Timeout de red: evita que "Ingresando…" quede colgado si Render está despertando. */
const REQUEST_TIMEOUT_MS = 45_000;

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
  timeoutMs?: number;
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

  const timeoutMs = opts.timeoutMs ?? REQUEST_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...opts,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(
        "El servidor no respondió a tiempo. Si es la primera carga del día, esperá ~1 min y reintentá (cold start).",
        408,
      );
    }
    throw new ApiError(
      err instanceof Error ? err.message : "Error de red al contactar la API",
      0,
    );
  } finally {
    clearTimeout(timer);
  }

  if (res.status === 401) {
    // Login / endpoints sin token: mostrar el detalle real (credenciales, etc.)
    if (opts.skipAuth) {
      const err = await res.json().catch(() => ({}));
      const detail =
        typeof err.detail === "string"
          ? err.detail
          : Array.isArray(err.detail)
            ? err.detail.map((d: { msg?: string }) => d.msg).join(", ")
            : "";
      throw new ApiError(detail || "Usuario o contraseña incorrectos", 401);
    }
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
  publicBranding() {
    return request<{
      bot_display_name: string;
      bot_display_name_short: string;
      org_hint: string;
    }>("/api/v1/public/branding", { skipAuth: true, timeoutMs: 8_000 });
  },

  login(usuario: string, password: string) {
    return request<LoginResponse>("/api/login", {
      method: "POST",
      body: JSON.stringify({ usuario, password }),
      skipAuth: true,
    });
  },

  logout() {
    return request<{ status: string }>("/api/logout", { method: "POST" }).catch(() => ({
      status: "ok",
    }));
  },

  changePassword(current_password: string, new_password: string) {
    return request<{
      status: string;
      must_change_password: boolean;
      token?: string;
      rol?: string;
      usuario?: string;
      cooperativa?: string | null;
      nombre?: string;
      org_slug?: string;
      permisos?: string[];
    }>("/api/v1/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    });
  },

  createInvite(body: { email: string; nombre?: string; rol?: string }, tenantSlug?: string) {
    return request<{
      status: string;
      email: string;
      rol: string;
      expires_at: string;
      email_sent: boolean;
      purpose?: string;
      token?: string;
      invite_link?: string;
    }>("/api/v1/auth/invites", {
      method: "POST",
      body: JSON.stringify(body),
      tenantSlug,
    });
  },

  adminCreateInvite(
    slug: string,
    body: { email: string; nombre?: string; rol?: string },
  ) {
    return request<{
      status: string;
      email: string;
      rol: string;
      expires_at: string;
      email_sent: boolean;
      email_error?: string;
      purpose?: string;
      token?: string;
      invite_link?: string;
    }>(`/api/v1/admin/organizations/${encodeURIComponent(slug)}/invites`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  listInvites(tenantSlug?: string) {
    return request<{
      invites: {
        id: string;
        email: string;
        nombre: string;
        rol: string;
        expires_at: string | null;
        accepted_at: string | null;
        invited_by: string;
        purpose?: string;
        pendiente: boolean;
      }[];
    }>("/api/v1/auth/invites", { tenantSlug });
  },

  peekInvite(token: string) {
    return request<{
      email: string;
      nombre: string;
      rol: string;
      purpose?: string;
      org_slug: string;
      org_nombre: string;
      expires_at: string;
    }>(`/api/v1/auth/invite/${encodeURIComponent(token)}`, { skipAuth: true });
  },

  acceptInvite(body: { token: string; password: string; nombre?: string }) {
    return request<{
      status: string;
      email: string;
      nombre: string;
      rol: string;
      org_slug: string;
    }>("/api/v1/auth/invite/accept", {
      method: "POST",
      body: JSON.stringify(body),
      skipAuth: true,
    });
  },

  loginEvents(superficie = "console", limit = 50) {
    return request<{
      eventos: {
        id: string;
        superficie: string;
        actor: string;
        ip: string;
        ok: boolean;
        reason: string;
        org_slug: string;
        created_at: string | null;
      }[];
    }>(`/api/v1/auth/login-events?superficie=${superficie}&limit=${limit}`);
  },

  resetUserPassword(userId: string, tenantSlug?: string) {
    return request<{ status: string; email: string; must_change_password: boolean; temporary_password?: string }>(
      `/api/v1/org/users/${userId}/reset-password`,
      { method: "POST", body: JSON.stringify({ must_change: true }), tenantSlug },
    );
  },

  portalAuthStart(body: { dni: string; org_slug?: string; linea?: string }) {
    return request<{
      status: string;
      challenge_id: string;
      contact_masked: string;
      expires_in_seconds: number;
      org_slug: string;
      debug_otp?: string;
    }>("/api/v1/portal/auth/start", {
      method: "POST",
      body: JSON.stringify(body),
      skipAuth: true,
    });
  },

  portalAuthVerify(body: { challenge_id: string; otp: string; org_slug?: string }) {
    return request<{
      portal_token: string;
      org_slug: string;
      abonado_identificado: boolean;
      has_pin: boolean;
      conversacion: InboxConversation;
      mensajes: InboxMessage[];
      contact_masked?: string;
    }>("/api/v1/portal/auth/verify", {
      method: "POST",
      body: JSON.stringify(body),
      skipAuth: true,
    });
  },

  portalLoginPin(body: { dni: string; pin: string; org_slug?: string }) {
    return request<{
      portal_token: string;
      org_slug: string;
      abonado_identificado: boolean;
      has_pin: boolean;
      conversacion: InboxConversation;
      mensajes: InboxMessage[];
    }>("/api/v1/portal/auth/login-pin", {
      method: "POST",
      body: JSON.stringify(body),
      skipAuth: true,
    });
  },

  portalSetPin(pin: string, portalToken: string) {
    return fetch(`${API_BASE}/api/v1/portal/auth/set-pin`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${portalToken}`,
      },
      body: JSON.stringify({ pin }),
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new ApiError(
          typeof err.detail === "string" ? err.detail : res.statusText,
          res.status,
        );
      }
      return res.json() as Promise<{ status: string; has_pin: boolean }>;
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

  tickets(
    paramsOrTenant?: {
      estado?: string;
      nivel?: string;
      sla?: string;
      categoria?: string;
      q?: string;
      solo_abiertos?: boolean;
      asignacion?: string;
      asignado_a?: string;
    } | string,
    tenantSlug?: string,
  ) {
    let params: {
      estado?: string;
      nivel?: string;
      sla?: string;
      categoria?: string;
      q?: string;
      solo_abiertos?: boolean;
      asignacion?: string;
      asignado_a?: string;
    } | undefined;
    let slug = tenantSlug;
    if (typeof paramsOrTenant === "string") {
      slug = paramsOrTenant;
    } else {
      params = paramsOrTenant;
    }
    const qs = new URLSearchParams();
    if (params?.estado) qs.set("estado", params.estado);
    if (params?.nivel) qs.set("nivel", params.nivel);
    if (params?.sla) qs.set("sla", params.sla);
    if (params?.categoria) qs.set("categoria", params.categoria);
    if (params?.q) qs.set("q", params.q);
    if (params?.solo_abiertos) qs.set("solo_abiertos", "true");
    if (params?.asignacion) qs.set("asignacion", params.asignacion);
    if (params?.asignado_a) qs.set("asignado_a", params.asignado_a);
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<{ tenant: string; tickets: Ticket[] }>(`/api/v1/tickets${suffix}`, {
      tenantSlug: slug,
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

  reassignTicket(
    id: string,
    body: { asignado_a: string; nota?: string },
    tenantSlug?: string,
  ) {
    return request<{ status: string; ticket: Ticket }>(`/api/v1/tickets/${id}/reassign`, {
      method: "POST",
      body: JSON.stringify(body),
      tenantSlug,
    });
  },

  claimTicket(id: string, tenantSlug?: string) {
    return request<{
      status: string;
      ticket: Ticket;
      ya_asignado?: boolean;
      conversacion_id?: string;
    }>(`/api/v1/tickets/${id}/claim`, {
      method: "POST",
      tenantSlug,
    });
  },

  ticketConversation(id: string, tenantSlug?: string) {
    return request<{
      tenant: string;
      ticket_id: string;
      conversacion: InboxConversation | null;
      mensajes: InboxMessage[];
    }>(`/api/v1/tickets/${id}/conversation`, { tenantSlug });
  },

  setAvailability(disponibilidad: string) {
    return request<{ status: string; disponibilidad: string; persistido: boolean }>(
      "/api/v1/me/availability",
      { method: "PATCH", body: JSON.stringify({ disponibilidad }) },
    );
  },

  orgUsers() {
    return request<{ slug: string; usuarios: AdminUser[] }>("/api/v1/org/users");
  },

  createOrgUser(body: {
    email: string;
    nombre: string;
    password?: string;
    rol?: string;
    telefono?: string;
    linea_principal?: string;
  }) {
    return request<{ status: string; usuario: AdminUser }>("/api/v1/org/users", {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  updateOrgUser(
    userId: string,
    body: { nombre?: string; activo?: boolean; password?: string },
  ) {
    return request<{ status: string; usuario: AdminUser }>(`/api/v1/org/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    });
  },

  addTicketNote(
    id: string,
    body: { titulo?: string; detalle: string; interno?: boolean },
    tenantSlug?: string,
  ) {
    return request<{ status: string; evento: TicketEvent }>(
      `/api/v1/tickets/${id}/events`,
      {
        method: "POST",
        body: JSON.stringify(body),
        tenantSlug,
      },
    );
  },

  ticketKbDraft(id: string, tenantSlug?: string) {
    return request<{
      tenant: string;
      ticket_id: string;
      borrador: { titulo: string; categoria: string; contenido: string; ticket_id: string };
    }>(`/api/v1/tickets/${id}/kb-draft`, { tenantSlug });
  },

  publishTicketKb(
    id: string,
    body?: { titulo?: string; categoria?: string; contenido?: string },
    tenantSlug?: string,
  ) {
    return request<{
      status: string;
      pendiente_revision?: boolean;
      contribucion: {
        id: string;
        titulo: string;
        categoria: string;
        estado: string;
        origen: string;
      };
      articulo?: { id: string; titulo: string; categoria: string };
    }>(`/api/v1/tickets/${id}/publish-kb`, {
      method: "POST",
      body: JSON.stringify(body || {}),
      tenantSlug,
    });
  },

  responseTemplates(categoria?: string, tenantSlug?: string) {
    const qs = categoria ? `?categoria=${encodeURIComponent(categoria)}` : "";
    return request<{
      plantillas: { id: string; nombre: string; categoria: string; contenido: string }[];
    }>(`/api/v1/response-templates${qs}`, { tenantSlug });
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

  kbContributions(params?: { estado?: string; ticket_id?: string }, tenantSlug?: string) {
    const qs = new URLSearchParams();
    if (params?.estado) qs.set("estado", params.estado);
    if (params?.ticket_id) qs.set("ticket_id", params.ticket_id);
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<{ tenant: string; estado: string; contribuciones: KBContribution[] }>(
      `/api/v1/kb/contributions${suffix}`,
      { tenantSlug },
    );
  },

  createKbContribution(
    body: {
      titulo: string;
      categoria?: string;
      contenido: string;
      ticket_id?: string;
      origen?: string;
    },
    tenantSlug?: string,
  ) {
    return request<{ status: string; contribucion: KBContribution }>(
      "/api/v1/kb/contributions",
      {
        method: "POST",
        body: JSON.stringify(body),
        tenantSlug,
      },
    );
  },

  approveKbContribution(
    id: string,
    body?: {
      titulo?: string;
      categoria?: string;
      contenido?: string;
      motivo_revision?: string;
    },
    tenantSlug?: string,
  ) {
    return request<{
      status: string;
      contribucion: KBContribution;
      articulo: { id: string; titulo: string; categoria: string };
    }>(`/api/v1/kb/contributions/${id}/approve`, {
      method: "POST",
      body: JSON.stringify(body || {}),
      tenantSlug,
    });
  },

  rejectKbContribution(
    id: string,
    body?: { motivo_revision?: string },
    tenantSlug?: string,
  ) {
    return request<{ status: string; contribucion: KBContribution }>(
      `/api/v1/kb/contributions/${id}/reject`,
      {
        method: "POST",
        body: JSON.stringify(body || {}),
        tenantSlug,
      },
    );
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

  agentsPerformance(tenantSlug?: string) {
    return request<{
      tenant: string;
      agentes: import("./types").AgentPerformanceRow[];
      total_agentes: number;
      tickets_abiertos: number;
    }>("/api/v1/analytics/agents", { tenantSlug });
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

  deleteOrganization(slug: string) {
    return request<{
      status: string;
      eliminada: {
        slug: string;
        nombre: string;
        usuarios: number;
        tickets: number;
        abonados: number;
      };
    }>(`/api/v1/admin/organizations/${encodeURIComponent(slug)}?confirm_slug=${encodeURIComponent(slug)}`, {
      method: "DELETE",
    });
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
    return request<{ status: string; usuario: AdminUser; temporary_password?: string }>(
      `/api/v1/admin/organizations/${slug}/users`,
      { method: "POST", body: JSON.stringify(body) },
    );
  },

  updateAdminUser(
    slug: string,
    userId: string,
    body: {
      nombre?: string;
      rol?: string;
      telefono?: string;
      linea_principal?: string;
      activo?: boolean;
      password?: string;
    },
  ) {
    return request<{ status: string; usuario: AdminUser }>(
      `/api/v1/admin/organizations/${slug}/users/${userId}`,
      { method: "PATCH", body: JSON.stringify(body) },
    );
  },

  adminResetUserPassword(slug: string, userId: string) {
    return request<{
      status: string;
      email: string;
      must_change_password: boolean;
      via_email?: boolean;
      email_sent?: boolean;
      email_error?: string;
      temporary_password?: string;
      token?: string;
      invite_link?: string;
    }>(`/api/v1/admin/organizations/${encodeURIComponent(slug)}/users/${encodeURIComponent(userId)}/reset-password`, {
      method: "POST",
      body: JSON.stringify({}),
    });
  },

  rbacRoles() {
    return request<{ roles: import("./types").RbacRole[] }>("/api/v1/rbac/roles");
  },

  rbacPermissions() {
    return request<{
      permisos: import("./types").RbacPermission[];
      matriz: import("./types").RbacRole[];
    }>("/api/v1/rbac/permissions");
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

  adminAudit(limit = 20) {
    return request<{ eventos: AuditEvent[] }>(`/api/v1/admin/audit?limit=${limit}`);
  },

  adminSettings() {
    return request<PlatformSettingsResponse>("/api/v1/admin/settings");
  },

  updateAdminSettings(settings: Record<string, unknown>) {
    return request<PlatformSettingsResponse>("/api/v1/admin/settings", {
      method: "PUT",
      body: JSON.stringify({ settings }),
    });
  },

  testAdminAi() {
    return request<{ ok: boolean; model?: string; base_url?: string; reply?: string; error?: string }>(
      "/api/v1/admin/settings/test-ai",
      { method: "POST" },
    );
  },

  testAdminWhatsapp() {
    return request<{
      ok: boolean;
      phone_number_id_set?: boolean;
      token_set?: boolean;
      verify_token?: string;
      default_org_slug?: string;
      nota?: string;
    }>("/api/v1/admin/settings/test-whatsapp", { method: "POST" });
  },

  testAdminDatabase() {
    return request<{
      ok: boolean;
      connected?: boolean;
      dialect?: string;
      url_masked?: string;
      sslmode?: string | null;
      latency_ms?: number | null;
      server_version?: string | null;
      current_database?: string | null;
      current_user?: string | null;
      scope?: string;
      nota?: string;
      error?: string;
    }>("/api/v1/admin/settings/test-database", { method: "POST" });
  },

  testAdminBilltrack(payload?: {
    host?: string;
    port?: string | number;
    user?: string;
    password?: string;
    dbname?: string;
    url?: string;
    sslmode?: string;
  }) {
    return request<{
      ok: boolean;
      connected?: boolean;
      dialect?: string;
      url_masked?: string;
      sslmode?: string | null;
      latency_ms?: number | null;
      server_version?: string | null;
      current_database?: string | null;
      current_user?: string | null;
      scope?: string;
      nota?: string;
      hint?: string;
      error?: string;
    }>("/api/v1/admin/settings/test-billtrack", {
      method: "POST",
      body: JSON.stringify(payload || {}),
    });
  },

  inboxConversations(
    params?: { estado?: string; mias?: boolean },
    tenantSlug?: string,
  ) {
    const qs = new URLSearchParams();
    if (params?.estado) qs.set("estado", params.estado);
    if (params?.mias) qs.set("mias", "true");
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<{
      tenant: string;
      conversaciones: InboxConversation[];
    }>(`/api/v1/inbox/conversations${suffix}`, { tenantSlug });
  },

  inboxConversation(id: string, tenantSlug?: string) {
    return request<{
      tenant: string;
      conversacion: InboxConversation;
      mensajes: InboxMessage[];
    }>(`/api/v1/inbox/conversations/${id}`, { tenantSlug });
  },

  inboxClaim(id: string, tenantSlug?: string) {
    return request<{ status: string; conversacion: InboxConversation }>(
      `/api/v1/inbox/conversations/${id}/claim`,
      { method: "POST", tenantSlug },
    );
  },

  inboxRelease(id: string, tenantSlug?: string) {
    return request<{ status: string; conversacion: InboxConversation }>(
      `/api/v1/inbox/conversations/${id}/release`,
      { method: "POST", tenantSlug },
    );
  },

  inboxSend(id: string, texto: string, tenantSlug?: string) {
    return request<{ status: string; mensaje: InboxMessage }>(
      `/api/v1/inbox/conversations/${id}/messages`,
      { method: "POST", body: JSON.stringify({ texto }), tenantSlug },
    );
  },

  inboxClose(id: string, tenantSlug?: string) {
    return request<{ status: string; conversacion: InboxConversation }>(
      `/api/v1/inbox/conversations/${id}/close`,
      { method: "POST", tenantSlug },
    );
  },

  inboxAssign(
    id: string,
    body: { agente_id: string; agente_nombre?: string },
    tenantSlug?: string,
  ) {
    return request<{ status: string; conversacion: InboxConversation }>(
      `/api/v1/inbox/conversations/${id}/assign`,
      { method: "POST", body: JSON.stringify(body), tenantSlug },
    );
  },

  portalSession(body: { telefono?: string; dni?: string; org_slug?: string }) {
    return request<{
      portal_token: string;
      org_slug: string;
      conversacion: InboxConversation;
      mensajes: InboxMessage[];
      abonado_identificado: boolean;
      modo_invitado?: boolean;
    }>("/api/v1/portal/session", {
      method: "POST",
      body: JSON.stringify(body),
      skipAuth: true,
    });
  },

  portalSend(texto: string, portalToken: string) {
    return fetch(`${API_BASE}/api/v1/portal/messages`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${portalToken}`,
      },
      body: JSON.stringify({ texto }),
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new ApiError(
          typeof err.detail === "string" ? err.detail : res.statusText,
          res.status,
        );
      }
      return res.json() as Promise<{
        ok: boolean;
        conversacion_id?: string;
        respuesta?: string;
        estado?: string;
        ticket_id?: string;
        conversacion?: InboxConversation | null;
        mensajes: InboxMessage[];
      }>;
    });
  },

  portalConversation(id: string, portalToken: string) {
    return fetch(`${API_BASE}/api/v1/portal/conversations/${id}`, {
      headers: { Authorization: `Bearer ${portalToken}` },
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new ApiError(
          typeof err.detail === "string" ? err.detail : res.statusText,
          res.status,
        );
      }
      return res.json() as Promise<{
        conversacion: InboxConversation;
        mensajes: InboxMessage[];
      }>;
    });
  },

  inboxSimulate(
    body: { telefono: string; texto: string; usar_llama?: boolean },
    tenantSlug?: string,
  ) {
    return request<{
      ok: boolean;
      conversacion_id?: string;
      respuesta?: string;
      estado?: string;
      ticket_id?: string;
      modo?: string;
    }>("/api/v1/inbox/simulate", {
      method: "POST",
      body: JSON.stringify(body),
      tenantSlug,
    });
  },

  inboxAbonados(tenantSlug?: string) {
    return request<{ tenant: string; abonados: InboxAbonado[] }>("/api/v1/inbox/abonados", {
      tenantSlug,
    });
  },
};

export interface InboxAbonado {
  id: string;
  dni: string;
  telefono_e164: string;
  nombre: string;
  servicio: string;
  estado: string;
  deuda_monto: string;
  plan: string;
  linea_msisdn: string;
}

export interface InboxConversation {
  id: string;
  canal: string;
  canal_display?: string;
  wa_id: string;
  telefono: string;
  abonado_id: string;
  abonado?: InboxAbonado | null;
  estado: string;
  agente_id: string;
  session_id: string;
  servicio_detectado: string;
  ticket_id: string;
  created_at: string;
  updated_at: string;
}

export interface InboxMessage {
  id: string;
  conversacion_id: string;
  direccion: string;
  autor: string;
  texto: string;
  meta_message_id: string;
  created_at: string;
}