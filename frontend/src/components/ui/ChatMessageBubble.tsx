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

/** Renderiza el cuerpo: líneas URL → bloque link + chip Abrir. */
export function renderMessageBody(text: string): ReactNode {
  const raw = text || "";
  const lines = raw.split(/\r?\n/);
  if (lines.length <= 1 && !extractHref(raw.trim()) && !/https?:\/\//i.test(raw)) {
    return linkifyText(raw);
  }

  return lines.map((line, i) => {
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
          {i < lines.length - 1 ? "\n" : null}
        </span>
      );
    }
    return (
      <span key={`line-${i}`}>
        {linkifyText(line)}
        {i < lines.length - 1 ? "\n" : null}
      </span>
    );
  });
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
