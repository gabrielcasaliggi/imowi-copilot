"use client";

import type { ReactNode } from "react";
import type { InboxMessage } from "@/lib/api-client";
import { getBranding } from "@/lib/brand";
import { EcoAvatar } from "@/components/ui/EcoAvatar";

type AutorKind = "cliente" | "bot" | "agente" | string;

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
      <EcoAvatar className="h-7 w-7 mb-0.5" />
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
      <p className="whitespace-pre-wrap leading-relaxed text-[13px] text-slate-100/95">
        {message.texto}
      </p>
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
