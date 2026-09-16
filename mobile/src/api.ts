import { API_BASE, CANAL_HEADER } from "./config";
import type {
  AuthPayload,
  ConnectivityStatusResponse,
  InboxConversation,
  InboxMessage,
  PortalAudioResult,
  PortalTicket,
  PortalTicketDetail,
} from "./types";
import { defaultBranding, type Branding } from "./theme";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function parseError(res: Response): Promise<string> {
  const err = await res.json().catch(() => ({} as { detail?: unknown }));
  if (typeof err.detail === "string") return err.detail;
  return "";
}

async function request(
  path: string,
  init: RequestInit,
  timeoutMs = 25000,
): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await fetch(`${API_BASE}${path}`, { ...init, signal: ctrl.signal });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError("", 408);
    }
    throw new ApiError("", 0);
  } finally {
    clearTimeout(timer);
  }
}

async function postJson<T>(path: string, body: unknown, token?: string): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...CANAL_HEADER,
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await request(path, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  return res.json() as Promise<T>;
}

export const api = {
  async branding(): Promise<Branding> {
    try {
      const res = await request("/api/v1/public/branding", {
        headers: { Accept: "application/json" },
      });
      if (!res.ok) return defaultBranding;
      const data = await res.json();
      return {
        botDisplayName: data.bot_display_name || defaultBranding.botDisplayName,
        botDisplayNameShort:
          data.bot_display_name_short || defaultBranding.botDisplayNameShort,
        orgHint: data.org_hint || defaultBranding.orgHint,
        productDisplayName:
          data.product_display_name || defaultBranding.productDisplayName,
        assistantTagline:
          data.assistant_tagline || defaultBranding.assistantTagline,
        assistantIntro: data.assistant_intro || defaultBranding.assistantIntro,
      };
    } catch {
      return defaultBranding;
    }
  },

  authStart(dni: string, orgSlug: string) {
    return postJson<{
      status: string;
      challenge_id: string;
      contact_masked: string;
      debug_otp?: string;
    }>("/api/v1/portal/auth/start", { dni, org_slug: orgSlug });
  },

  authVerify(challengeId: string, otp: string, orgSlug: string) {
    return postJson<AuthPayload>("/api/v1/portal/auth/verify", {
      challenge_id: challengeId,
      otp,
      org_slug: orgSlug,
    });
  },

  loginPin(dni: string, pin: string, orgSlug: string) {
    return postJson<AuthPayload>("/api/v1/portal/auth/login-pin", {
      dni,
      pin,
      org_slug: orgSlug,
    });
  },

  setPin(pin: string, token: string) {
    return postJson<{ status: string; has_pin: boolean }>(
      "/api/v1/portal/auth/set-pin",
      { pin },
      token,
    );
  },

  deleteAccount(token: string) {
    return postJson<{ status: string }>("/api/v1/portal/account/delete", {}, token);
  },

  send(texto: string, token: string) {
    return postJson<{
      ok: boolean;
      conversacion: InboxConversation | null;
      mensajes: InboxMessage[];
    }>("/api/v1/portal/messages", { texto }, token);
  },

  async conversation(id: string, token: string) {
    const res = await request(`/api/v1/portal/conversations/${id}`, {
      headers: { Authorization: `Bearer ${token}`, ...CANAL_HEADER },
    });
    if (!res.ok) throw new ApiError(await parseError(res), res.status);
    return res.json() as Promise<{
      conversacion: InboxConversation;
      mensajes: InboxMessage[];
    }>;
  },

  registerDevice(
    token: string,
    body: { expo_push_token: string; platform: string; device_name?: string },
  ) {
    return postJson<{ status: string; device_id: string }>(
      "/api/v1/portal/devices",
      body,
      token,
    );
  },

  async unregisterDevice(
    token: string,
    body: { expo_push_token: string; platform?: string; device_name?: string },
  ) {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...CANAL_HEADER,
      Authorization: `Bearer ${token}`,
    };
    const res = await request("/api/v1/portal/devices", {
      method: "DELETE",
      headers,
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new ApiError(await parseError(res), res.status);
    return res.json() as Promise<{ status: string }>;
  },

  async sendAudio(uri: string, token: string) {
    const form = new FormData();
    form.append("file", {
      uri,
      name: "voice.m4a",
      type: "audio/mp4",
    } as unknown as Blob);
    const res = await request("/api/v1/portal/audio", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        ...CANAL_HEADER,
      },
      body: form,
    }, 60000);
    if (!res.ok) throw new ApiError(await parseError(res), res.status);
    return res.json() as Promise<PortalAudioResult>;
  },

  async listTickets(token: string) {
    const res = await request("/api/v1/portal/tickets", {
      headers: { Authorization: `Bearer ${token}`, ...CANAL_HEADER },
    });
    if (!res.ok) throw new ApiError(await parseError(res), res.status);
    return res.json() as Promise<{ items: PortalTicket[]; total: number }>;
  },

  async getTicket(ticketId: string, token: string) {
    const id = encodeURIComponent(ticketId);
    const res = await request(`/api/v1/portal/tickets/${id}`, {
      headers: { Authorization: `Bearer ${token}`, ...CANAL_HEADER },
    });
    if (!res.ok) throw new ApiError(await parseError(res), res.status);
    return res.json() as Promise<PortalTicketDetail>;
  },

  async getConnectivity(token: string, serviceId?: string) {
    const q = serviceId
      ? `?service_id=${encodeURIComponent(serviceId)}`
      : "";
    const res = await request(`/api/v1/portal/connectivity${q}`, {
      headers: { Authorization: `Bearer ${token}`, ...CANAL_HEADER },
    });
    if (!res.ok) throw new ApiError(await parseError(res), res.status);
    return res.json() as Promise<ConnectivityStatusResponse>;
  },
};
