import { ApiError } from "./api";

export const MSG_NETWORK =
  "No pudimos conectarnos. Revisá tu conexión e intentá nuevamente.";
export const MSG_SERVER = "No pudimos completar la operación. Intentá nuevamente.";
const MSG_VALIDATION = "Revisá los datos e intentá nuevamente.";
export const MSG_SESSION = "Tu sesión venció. Ingresá de nuevo.";

export function isAuthExpired(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

function looksTechnical(msg: string): boolean {
  const t = msg.trim();
  if (!t) return true;
  if (t.startsWith("{") || t.startsWith("[")) return true;
  if (/traceback|postgres|sqlalchemy|exception|internal server/i.test(t)) return true;
  if (/https?:\/\/(127\.|localhost|10\.|192\.168\.)/i.test(t)) return true;
  return false;
}

export function formatUserError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 0 || err.status === 408) return MSG_NETWORK;
    if (err.status === 401) return MSG_SESSION;
    if (err.status === 422) {
      return looksTechnical(err.message) ? MSG_VALIDATION : err.message.trim();
    }
    if (err.status >= 500) return MSG_SERVER;
    if (err.message && !looksTechnical(err.message)) return err.message.trim();
    return fallback;
  }
  if (err instanceof Error) {
    const m = err.message.toLowerCase();
    if (
      err.name === "AbortError" ||
      m.includes("network") ||
      m.includes("failed to fetch") ||
      m.includes("timeout") ||
      m.includes("timed out")
    ) {
      return MSG_NETWORK;
    }
  }
  return fallback;
}
