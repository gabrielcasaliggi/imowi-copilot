const TOKEN_KEY = "imowi_token";
const SESSION_KEY = "imowi_session";
const TENANT_KEY = "imowi_tenant";
const HIST_PREFIX = "imowi_hist_";

export interface StoredChatMessage {
  rol: "usuario" | "asistente";
  contenido: string;
}

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function getSessionId(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(SESSION_KEY) || "";
}

export function setSessionId(id: string): void {
  localStorage.setItem(SESSION_KEY, id);
}

export function clearSessionId(): void {
  localStorage.removeItem(SESSION_KEY);
}

export function newSessionId(): string {
  const id =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `s-${Date.now()}`;
  setSessionId(id);
  return id;
}

export function getTenantSlug(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(TENANT_KEY) || "";
}

export function setTenantSlug(slug: string): void {
  localStorage.setItem(TENANT_KEY, slug);
}

export function clearTenantSlug(): void {
  localStorage.removeItem(TENANT_KEY);
}

export function saveHistorial(sessionId: string, historial: StoredChatMessage[]): void {
  if (!sessionId) return;
  localStorage.setItem(`${HIST_PREFIX}${sessionId}`, JSON.stringify(historial));
}

export function loadHistorial(sessionId: string): StoredChatMessage[] {
  if (!sessionId || typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(`${HIST_PREFIX}${sessionId}`);
    return raw ? (JSON.parse(raw) as StoredChatMessage[]) : [];
  } catch {
    return [];
  }
}

export function clearHistorial(sessionId: string): void {
  if (sessionId) localStorage.removeItem(`${HIST_PREFIX}${sessionId}`);
}
