"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useApp } from "@/contexts/AppContext";
import { EstadoCasoBadge, LineaCambiadaBanner, NetworkAlertBanner } from "./NetworkAlertBanner";
import { StatusBadge } from "@/components/ui/StatusBadge";

/** Consola del agente: trabajo sobre el ticket tomado. Sin ticket → ir a Cola. */
export function ChatPanel() {
  const {
    historial,
    sending,
    sendMessage,
    sendAccionOperador,
    isAdmin,
    intencionPendiente,
    lineaCambiada,
    ticketFormacion,
  } = useApp();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historial]);

  if (isAdmin) return null;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending || lineaCambiada || !ticketFormacion) return;
    setInput("");
    sendMessage(text);
  };

  const bloqueado = Boolean(lineaCambiada);

  if (!ticketFormacion) {
    return (
      <div className="flex flex-col flex-1 min-h-0 items-center justify-center p-8 text-center gap-4">
        <div className="max-w-md space-y-2">
          <h2 className="font-semibold text-slate-50 text-lg">Consola N2</h2>
          <p className="text-sm text-slate-400 leading-relaxed">
            Acá trabajás el caso con el cliente una vez que tomaste un ticket de la cola.
          </p>
          <p className="text-xs text-slate-500 leading-relaxed">
            Todavía no hay un ticket activo en esta sesión.
          </p>
        </div>
        <Link
          href="/tickets"
          className="text-sm font-medium px-4 py-2.5 rounded-xl border border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/12"
        >
          Ir a la Cola para tomar un ticket
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <NetworkAlertBanner />
      <LineaCambiadaBanner />

      <div className="chat-action-bar px-4 py-3 flex justify-between items-start flex-wrap gap-3">
        <div>
          <h2 className="font-semibold text-slate-50 text-base">Consola N2</h2>
          <p className="text-[11px] font-mono text-slate-400 mt-0.5">
            Ticket {ticketFormacion.id}
            {ticketFormacion.linea ? ` · ${ticketFormacion.linea}` : ""}
            {ticketFormacion.categoria ? ` · ${ticketFormacion.categoria}` : ""}
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5 items-center">
            {ticketFormacion.nivel && <StatusBadge value={ticketFormacion.nivel} />}
            <StatusBadge value={ticketFormacion.estado} />
            <EstadoCasoBadge />
          </div>
        </div>
        <Link
          href="/tickets"
          className="text-xs font-medium px-3.5 py-2 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800/50"
        >
          Volver a Cola
        </Link>
      </div>

      {intencionPendiente && (
        <div className="chat-pending-actions px-4 py-2.5 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-mono text-emerald-400/90 uppercase tracking-wide mr-1">
            Acción pendiente
          </span>
          {intencionPendiente === "confirmar_ticket" && (
            <button
              type="button"
              onClick={() => sendAccionOperador("confirmar_ticket")}
              disabled={sending}
              className="text-xs font-medium px-3.5 py-1.5 rounded-lg border border-emerald-500/45 text-emerald-200 hover:bg-emerald-500/12"
            >
              Confirmar ticket
            </button>
          )}
          {intencionPendiente === "confirmar_resolucion" && (
            <button
              type="button"
              onClick={() => sendAccionOperador("caso_resuelto")}
              disabled={sending}
              className="text-xs font-medium px-3.5 py-1.5 rounded-lg border border-emerald-500/45 text-emerald-200 hover:bg-emerald-500/12"
            >
              Caso resuelto
            </button>
          )}
          {intencionPendiente === "continuar_kb" && (
            <button
              type="button"
              onClick={() => sendAccionOperador("continuar_kb")}
              disabled={sending}
              className="text-xs font-medium px-3.5 py-1.5 rounded-lg border border-emerald-500/45 text-emerald-200 hover:bg-emerald-500/12"
            >
              Continuar con KB
            </button>
          )}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 min-h-0">
        {!historial.length ? (
          <p className="text-sm text-slate-500">
            Escribí notas o mensajes del caso. El detalle del ticket está en el panel derecho.
          </p>
        ) : (
          historial.map((m, i) => {
            const user = m.rol === "usuario";
            return (
              <div
                key={i}
                className={`max-w-[90%] px-3 py-2 rounded-xl text-sm whitespace-pre-wrap ${
                  user
                    ? "ml-auto bg-cyan-500/15 text-slate-100"
                    : "bg-slate-800/70 text-slate-200"
                }`}
              >
                {m.contenido}
              </div>
            );
          })
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={onSubmit}
        className="px-4 py-3 border-t border-slate-800/80 flex gap-2 shrink-0"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            bloqueado
              ? "Cambio de línea pendiente…"
              : "Notas del caso / mensaje al asistente…"
          }
          disabled={sending || bloqueado}
          className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={sending || bloqueado || !input.trim()}
          className="px-4 py-2 rounded-lg text-sm font-semibold text-slate-950 disabled:opacity-40"
          style={{ background: "var(--brand)" }}
        >
          Enviar
        </button>
      </form>
    </div>
  );
}
