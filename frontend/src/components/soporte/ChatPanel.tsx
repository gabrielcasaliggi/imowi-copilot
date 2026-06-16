"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useApp } from "@/contexts/AppContext";
import { EstadoCasoBadge, LineaCambiadaBanner, NetworkAlertBanner } from "./NetworkAlertBanner";

export function ChatPanel() {
  const {
    historial,
    sending,
    sendMessage,
    sendAccionOperador,
    startNewClaim,
    isAdmin,
    intencionPendiente,
    lineaCambiada,
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
    if (!text || sending || lineaCambiada) return;
    setInput("");
    sendMessage(text);
  };

  const bloqueado = Boolean(lineaCambiada);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <NetworkAlertBanner />
      <LineaCambiadaBanner />

      <div className="chat-action-bar px-4 py-3 flex justify-between items-start flex-wrap gap-3">
        <div>
          <h2 className="font-semibold text-slate-50 text-base">Copilot de Reclamos</h2>
          <p className="text-[11px] font-mono text-slate-400 mt-0.5">
            Un caso por línea móvil · confirmaciones con botones
          </p>
          <div className="mt-1.5">
            <EstadoCasoBadge />
          </div>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            onClick={startNewClaim}
            className="text-xs font-medium px-3.5 py-2 rounded-lg border border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/12 transition-colors"
          >
            Nuevo reclamo
          </button>
          <button
            type="button"
            onClick={() => sendMessage("", true)}
            disabled={sending}
            className="text-xs font-medium px-3.5 py-2 rounded-lg border border-violet-500/40 text-violet-200 hover:bg-violet-500/12 disabled:opacity-50 transition-colors"
          >
            Registrar ticket NOC
          </button>
        </div>
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
              className="text-xs font-medium px-3.5 py-1.5 rounded-lg border border-cyan-500/45 text-cyan-200 hover:bg-cyan-500/12"
            >
              Seguir probando
            </button>
          )}
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-4">
        {historial.length === 0 && (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
            <p className="text-sm text-slate-400 leading-relaxed">
              Contá el inconveniente del cliente (línea, síntoma, equipo). Cada abonado
              distinto debe iniciarse con &quot;Nuevo reclamo&quot;.
            </p>
          </div>
        )}
        {historial.map((m, i) => {
          const user = m.rol === "usuario";
          return (
            <div key={i} className={`flex ${user ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[88%] min-w-0 ${user ? "text-right" : "text-left"}`}>
                <p
                  className={`text-[10px] font-mono uppercase tracking-wider mb-1 ${
                    user ? "text-cyan-500/80" : "text-slate-500"
                  }`}
                >
                  {user ? "Operador" : "Copilot"}
                </p>
                <div
                  className={`px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                    user ? "chat-bubble-user" : "chat-bubble-assistant"
                  }`}
                >
                  {m.contenido}
                </div>
              </div>
            </div>
          );
        })}
        {sending && (
          <div className="flex justify-start">
            <div className="chat-bubble-assistant px-4 py-2.5 rounded-2xl text-sm text-slate-400">
              <span className="inline-flex items-center gap-2">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                Analizando caso…
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={onSubmit}
        className="p-3 border-t border-slate-800/80 flex gap-2 shrink-0 bg-slate-950/30"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            bloqueado
              ? "Iniciá un nuevo reclamo para la otra línea…"
              : "Ej.: línea 223..., sin señal en zona centro, Samsung A54…"
          }
          className="flex-1 bg-slate-950/90 border border-slate-700/80 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-[var(--brand)] focus:ring-1 focus:ring-cyan-500/25 font-mono disabled:opacity-50"
          autoComplete="off"
          disabled={sending || bloqueado}
        />
        <button
          type="submit"
          disabled={sending || bloqueado || !input.trim()}
          className="px-5 py-2.5 rounded-xl font-semibold text-slate-950 text-sm disabled:opacity-40 transition-opacity min-w-[88px]"
          style={{ background: "var(--brand)" }}
        >
          {sending ? "Enviando…" : "Enviar"}
        </button>
      </form>
    </div>
  );
}
