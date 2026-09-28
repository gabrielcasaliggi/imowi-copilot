/** Vista de cabeceras FC. Sin React Native: el script de verificación la importa. */

import type { PortalInvoiceHeader, PortalInvoiceStatus } from "./types";

export type InvoiceUiPhase = "loading" | "success" | "empty" | "unavailable";

export const INVOICE_PUBLIC_KEYS = [
  "invoice_number",
  "full_type",
  "amount",
  "issued_at",
  "status",
] as const;

/** La sección no ofrece pago, PDF ni Oficina Virtual. */
export function invoiceSectionActions(): readonly string[] {
  return [];
}

export function invoiceUiPhase(input: {
  loading: boolean;
  transportError: boolean;
  status: PortalInvoiceStatus | null;
  count: number;
}): InvoiceUiPhase {
  if (input.loading) return "loading";
  if (input.transportError) return "unavailable";
  if (input.status === "unavailable" || input.status === "error" || input.status == null) {
    return "unavailable";
  }
  if (input.status === "empty" || input.count === 0) return "empty";
  return "success";
}

/** Copia solo el contrato. Descarta vencimiento, cuenta e ids. */
export function projectInvoiceHeader(raw: unknown): PortalInvoiceHeader | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const invoiceNumber = row.invoice_number;
  if (typeof invoiceNumber !== "string" || !invoiceNumber.trim()) return null;
  return {
    invoice_number: invoiceNumber,
    full_type: typeof row.full_type === "string" ? row.full_type : "",
    amount: typeof row.amount === "string" ? row.amount : "",
    issued_at: typeof row.issued_at === "string" ? row.issued_at : null,
    status: typeof row.status === "string" ? row.status : "",
  };
}

export function projectInvoiceList(raw: unknown): PortalInvoiceHeader[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => projectInvoiceHeader(item))
    .filter((item): item is PortalInvoiceHeader => item !== null);
}

const ISSUED_CALENDAR = /^(\d{4})-(\d{2})-(\d{2})(?:$|T)/;

function isRealCalendarDay(year: number, month: number, day: number): boolean {
  if (month < 1 || month > 12 || day < 1) return false;
  const utc = new Date(Date.UTC(year, month - 1, day));
  return (
    utc.getUTCFullYear() === year &&
    utc.getUTCMonth() === month - 1 &&
    utc.getUTCDate() === day
  );
}

/**
 * Día calendario de `issued_at`, como el chat (`strftime %d/%m/%Y` sobre el valor).
 * No usa la zona del dispositivo: lee AAAA-MM-DD del string.
 */
export function formatInvoiceIssuedAt(issuedAt?: string | null): string {
  const raw = (issuedAt || "").trim();
  const match = ISSUED_CALENDAR.exec(raw);
  if (!match) return "";
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!isRealCalendarDay(year, month, day)) return "";
  const dd = String(day).padStart(2, "0");
  const mm = String(month).padStart(2, "0");
  return `${dd}/${mm}/${year}`;
}
