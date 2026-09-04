"use client";

import type { ReactNode } from "react";
import type { InboxMessage } from "@/lib/api-client";
import { getBranding } from "@/lib/brand";
import { EkoAvatar } from "@/components/ui/EkoAvatar";

type AutorKind = "cliente" | "bot" | "agente" | string;

function trimUrlTrailingPunct(url: string): { href: string; trailing: string } {
  let href = url;
  let trailing = "";
  while (href && /[.,;:!?)]$/.test(href)) {
    trailing = href.slice(-1) + trailing;
    href = href.slice(0, -1);
  }
  return { href, trailing };
}

function ChatLink({ href, label }: { href: string; label?: string }) {
  const text = label || href;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="chat-msg-link"
      onClick={(e) => e.stopPropagation()}
      style={{
        color: "#2ec4d6",
        textDecoration: "underline",
        textUnderlineOffset: "2px",
        fontWeight: 600,
        wordBreak: "break-all",
        cursor: "pointer",
        pointerEvents: "auto",
      }}
    >
      {text}
    </a>
  );
}

/** Reconoce URL http(s) o host ov.batan.coop sin esquema. */
function extractHref(raw: string): string | null {
  const t = raw.trim();
  if (/^https?:\/\//i.test(t)) {
    return trimUrlTrailingPunct(t).href || null;
  }
  if (/^(www\.)?ov\.batan\.coop(\/|#|$)/i.test(t)) {
    return trimUrlTrailingPunct(`https://${t.replace(/^\/\//, "")}`).href || null;
  }
  return null;
}

export function linkifyText(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  let key = 0;
  // Incluye ov.batan.coop sin https
  const re = /(https?:\/\/[^\s<>"'`]+|(?:www\.)?ov\.batan\.coop(?:\/[^\s<>"'`]*)?)/gi;
  for (const match of text.matchAll(re)) {
    const raw = match[0];
    const idx = match.index ?? 0;
    if (idx > last) {
      nodes.push(text.slice(last, idx));
    }
    const href = extractHref(raw);
    if (href) {
      nodes.push(<ChatLink key={`url-${key++}`} href={href} />);
    } else {
      nodes.push(raw);
    }
    last = idx + raw.length;
  }
  if (last < text.length) {
    nodes.push(text.slice(last));
  }
  return nodes.length > 0 ? nodes : [text];
}

type GaugeKind = "optica" | "radio";
type GaugeTone = "green" | "orange" | "red";

/** Rangos alineados a app/services/barra_senal.py */
const OPTICA_MIN = -33;
const OPTICA_MAX = -8;
const RADIO_MIN = -90;
const RADIO_MAX = -40;

function clampNum(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function toneOptica(dbm: number): GaugeTone {
  if (dbm <= -27 || dbm >= -12) return "red";
  if (dbm <= -25 || dbm >= -15) return "orange";
  return "green";
}

function toneRadio(dbm: number): GaugeTone {
  if (dbm < -75) return "red";
  if (dbm < -65) return "orange";
  return "green";
}

function pctOptica(dbm: number): number {
  return ((clampNum(dbm, OPTICA_MIN, OPTICA_MAX) - OPTICA_MIN) / (OPTICA_MAX - OPTICA_MIN)) * 100;
}

function pctRadio(dbm: number): number {
  return ((clampNum(dbm, RADIO_MIN, RADIO_MAX) - RADIO_MIN) / (RADIO_MAX - RADIO_MIN)) * 100;
}

function parseGaugeHeader(line: string): { kind: GaugeKind; dbm: number } | null {
  const potencia = line.match(/^📊\s*Potencia de tu cajita:\s*(-?\d+(?:\.\d+)?)\s*dBm/i);
  if (potencia) return { kind: "optica", dbm: Number(potencia[1]) };
  const senal = line.match(/^📊\s*Señal de tu antena:\s*(-?\d+(?:\.\d+)?)\s*dBm/i);
  if (senal) return { kind: "radio", dbm: Number(senal[1]) };
  return null;
}

function isGaugeArtLine(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  if (/^[🟥🟧🟩🔴🟠🟢]+$/.test(t)) return true;
  if (/^floja\s*←/i.test(t)) return true;
  return false;
}

const TONE_HEX: Record<GaugeTone, string> = {
  green: "#22c55e",
  orange: "#f59e0b",
  red: "#ef4444",
};

function etiquetaGauge(kind: GaugeKind, dbm: number, tone: GaugeTone): string {
  if (kind === "optica") {
    if (tone === "green") return "ideal";
    if (tone === "orange") return "regular";
    return dbm >= -12 ? "muy fuerte" : "muy floja";
  }
  if (tone === "green") return "buena";
  if (tone === "orange") return "regular";
  return "floja";
}

function SignalGauge({ kind, dbm }: { kind: GaugeKind; dbm: number }) {
  const tone = kind === "optica" ? toneOptica(dbm) : toneRadio(dbm);
  const pct = kind === "optica" ? pctOptica(dbm) : pctRadio(dbm);
  const titulo = kind === "optica" ? "Potencia de tu cajita" : "Señal de tu antena";
  const valor = kind === "optica" ? `${dbm.toFixed(1)} dBm` : `${Math.round(dbm)} dBm`;
  const track =
    kind === "optica"
      ? "linear-gradient(to right, #ef4444 0%, #ef4444 24%, #f59e0b 32%, #22c55e 40%, #22c55e 64%, #f59e0b 76%, #ef4444 84%, #ef4444 100%)"
      : "linear-gradient(to right, #ef4444 0%, #ef4444 30%, #f59e0b 40%, #22c55e 54%, #22c55e 100%)";

  return (
    <div
      className="my-2 rounded-lg px-2.5 py-2"
      style={{
        background: "rgba(15, 23, 42, 0.55)",
        border: "1px solid rgba(148, 163, 184, 0.25)",
      }}
      role="img"
      aria-label={`${titulo}: ${valor}, ${etiquetaGauge(kind, dbm, tone)}`}
    >
      <div className="flex items-baseline justify-between gap-2 mb-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          {titulo}
        </span>
        <span className="text-[12px] font-semibold tabular-nums" style={{ color: TONE_HEX[tone] }}>
          {valor} · {etiquetaGauge(kind, dbm, tone)}
        </span>
      </div>
      <div className="relative h-3 rounded-full" style={{ background: track }}>
        <span
          className="absolute top-1/2 h-4 w-4 rounded-full shadow"
          style={{
            left: `${pct}%`,
            transform: "translate(-50%, -50%)",
            background: TONE_HEX[tone],
            border: "2px solid #f8fafc",
            boxSizing: "border-box",
          }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-slate-500">
        {kind === "optica" ? (
          <>
            <span>floja</span>
            <span>ideal</span>
            <span>fuerte</span>
          </>
        ) : (
          <>
            <span>floja</span>
            <span>buena</span>
          </>
        )}
      </div>
    </div>
  );
}

function renderPlainLine(line: string, i: number, last: boolean): ReactNode {
  const trimmed = line.trim();
  const href = extractHref(trimmed);
  if (href && trimmed.replace(/\s/g, "").length <= href.length + 8) {
    return (
      <span key={`line-${i}`} className="block my-1.5">
        <ChatLink href={href} />
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="ml-2 inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold"
          style={{
            background: "rgba(46, 196, 214, 0.18)",
            color: "#2ec4d6",
            border: "1px solid rgba(46, 196, 214, 0.45)",
            cursor: "pointer",
            pointerEvents: "auto",
            textDecoration: "none",
          }}
        >
          Abrir ↗
        </a>
        {!last ? "\n" : null}
      </span>
    );
  }
  return (
    <span key={`line-${i}`}>
      {linkifyText(line)}
      {!last ? "\n" : null}
    </span>
  );
}

/** Renderiza el cuerpo: medidor de señal, líneas URL → bloque link + chip Abrir. */
export function renderMessageBody(text: string): ReactNode {
  const raw = text || "";
  const lines = raw.split(/\r?\n/);
  if (lines.length <= 1 && !extractHref(raw.trim()) && !/https?:\/\//i.test(raw) && !parseGaugeHeader(raw.trim())) {
    return linkifyText(raw);
  }

  const nodes: ReactNode[] = [];
  for (let i = 0; i < lines.length; i++) {
    const gauge = parseGaugeHeader(lines[i].trim());
    if (gauge) {
      let j = i + 1;
      while (j < lines.length && isGaugeArtLine(lines[j])) j++;
      nodes.push(<SignalGauge key={`gauge-${i}`} kind={gauge.kind} dbm={gauge.dbm} />);
      i = j - 1;
      continue;
    }
    nodes.push(renderPlainLine(lines[i], i, i === lines.length - 1));
  }
  return nodes;
}

function originLabel(autor: AutorKind, portal?: boolean): string {
  if (autor === "cliente") return portal ? "VOS" : "ABONADO";
  if (autor === "bot") return getBranding().botDisplayNameShort;
  if (autor === "agente") return "AGENTE";
  return String(autor || "SISTEMA").toUpperCase();
}

function bubbleClass(autor: AutorKind): string {
  if (autor === "cliente") return "chat-bubble-cliente ml-auto";
  if (autor === "bot") return "chat-bubble-bot";
  return "chat-bubble-agente mr-auto";
}

function formatTime(iso?: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
}

function BotBubbleRow({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-end gap-2 mr-auto max-w-[min(90%,28rem)]">
      <EkoAvatar className="h-7 w-7 mb-0.5" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

export function ChatMessageBubble({
  message,
  portal = false,
}: {
  message: Pick<InboxMessage, "autor" | "texto" | "created_at"> & { id?: string };
  portal?: boolean;
}) {
  const isCliente = message.autor === "cliente";
  const isBot = message.autor === "bot";
  const time = formatTime(message.created_at);
  const origen = originLabel(message.autor, portal);

  const bubble = (
    <div
      className={`group px-3.5 py-2.5 rounded-xl text-sm shadow-sm transition-all duration-200 ease-in-out ${bubbleClass(message.autor)} ${isBot ? "w-full" : "max-w-[min(90%,28rem)]"}`}
    >
      <div
        className={`flex items-center gap-2 mb-1.5 ${isCliente ? "justify-end" : "justify-start"}`}
      >
        <span className={`chat-origin-label ${isBot ? "chat-origin-label-accent" : ""}`}>
          <span className="opacity-60">[ORIGEN:</span>
          <span className={isBot ? "text-ecolan-brand" : isCliente ? "text-ecolan-brand" : "text-slate-300"}>
            {origen}
          </span>
          <span className="opacity-60">]</span>
        </span>
        {time && (
          <span className="text-[10px] font-mono text-slate-500 tabular-nums opacity-0 group-hover:opacity-100 transition-opacity duration-200">
            {time}
          </span>
        )}
      </div>
      <div className="whitespace-pre-wrap leading-relaxed text-[13px] text-slate-100/95">
        {renderMessageBody(message.texto || "")}
      </div>
    </div>
  );

  if (isBot) {
    return <BotBubbleRow>{bubble}</BotBubbleRow>;
  }

  return bubble;
}

export function ChatTypingIndicator() {
  const { botDisplayName, botDisplayNameShort } = getBranding();
  return (
    <BotBubbleRow>
      <div
        className="chat-bubble-bot w-full px-3.5 py-2.5 rounded-xl text-sm shadow-sm"
        aria-live="polite"
        aria-label={`${botDisplayName} está escribiendo`}
      >
        <span className="chat-origin-label chat-origin-label-accent mb-1.5 block">
          <span className="opacity-60">[ORIGEN:</span>
          <span className="text-ecolan-brand">{botDisplayNameShort}</span>
          <span className="opacity-60">]</span>
        </span>
        <div className="flex items-center gap-1.5 py-0.5">
          <span className="h-1.5 w-1.5 rounded-full bg-ecolan-brand/80 animate-bounce [animation-delay:0ms]" />
          <span className="h-1.5 w-1.5 rounded-full bg-ecolan-brand/80 animate-bounce [animation-delay:150ms]" />
          <span className="h-1.5 w-1.5 rounded-full bg-ecolan-brand/80 animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    </BotBubbleRow>
  );
}

/** Ícono enviar (estilo Lucide Send) */
export function SendIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="m22 2-7 20-4-9-9-4Z" />
      <path d="M22 2 11 13" />
    </svg>
  );
}

export function MessagesEmptyIcon({ className = "h-10 w-10" }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z" />
    </svg>
  );
}
