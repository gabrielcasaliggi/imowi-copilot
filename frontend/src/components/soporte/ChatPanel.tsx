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
      <div className="px-4 py-3 border-b border-slate-800 flex justify-between items-start flex-wrap gap-2">
        <div>
          <h2 className="font-semibold text-slate-100">Copilot de Reclamos</h2>
          <p className="text-[10px] font-mono text-slate-500">
            Un caso por línea móvil · confirmaciones con botones
          </p>
          <EstadoCasoBadge />
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            onClick={startNewClaim}
            className="text-xs font-mono px-3 py-1.5 rounded-lg border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/10"
          >
            Nuevo reclamo
          </button>
          <button
            type="button"
            onClick={() => sendMessage("", true)}
            disabled={sending}
            className="text-xs font-mono px-3 py-1.5 rounded-lg border border-violet-500/40 text-violet-300 hover:bg-violet-500/10 disabled:opacity-50"
          >
            Registrar ticket NOC
          </button>
        </div>
      </div>

      {intencionPendiente && (
        <div className="px-4 py-2 border-b border-slate-800 flex flex-wrap gap-2">
          {intencionPendiente === "confirmar_ticket" && (
            <button
              type="button"
              onClick={() => sendAccionOperador("confirmar_ticket")}
              disabled={sending}
              className="text-xs font-mono px-3 py-1.5 rounded-lg border border-emerald-500/40 text-emerald-300"
            >
              Confirmar ticket
            </button>
          )}
          {intencionPendiente === "confirmar_resolucion" && (
            <button
              type="button"
              onClick={() => sendAccionOperador("caso_resuelto")}
              disabled={sending}
              className="text-xs font-mono px-3 py-1.5 rounded-lg border border-emerald-500/40 text-emerald-300"
            >
              Caso resuelto
            </button>
          )}
          {intencionPendiente === "continuar_kb" && (
            <button
              type="button"
              onClick={() => sendAccionOperador("continuar_kb")}
              disabled={sending}
              className="text-xs font-mono px-3 py-1.5 rounded-lg border border-cyan-500/40 text-cyan-300"
            >
              Seguir probando
            </button>
          )}
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
        {historial.length === 0 && (
          <p className="text-sm text-slate-500 font-mono">
            Contá el inconveniente del cliente (línea, síntoma, equipo). Cada abonado
            distinto debe iniciarse con &quot;Nuevo reclamo&quot;.
          </p>
        )}
        {historial.map((m, i) => {
          const user = m.rol === "usuario";
          return (
            <div key={i} className={`flex ${user ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm ${
                  user
                    ? "bg-cyan-500/15 border border-cyan-500/25"
                    : "bg-slate-800/80 border border-slate-700/60"
                }`}
              >
                {m.contenido}
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="p-3 border-t border-slate-800 flex gap-2 shrink-0">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            bloqueado
              ? "Iniciá un nuevo reclamo para la otra línea…"
              : "Cliente sin datos en Brasil, línea 2235551234, Samsung A54…"
          }
          className="flex-1 bg-slate-950/80 border border-slate-700 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-[var(--brand)] font-mono disabled:opacity-50"
          autoComplete="off"
          disabled={sending || bloqueado}
        />
        <button
          type="submit"
          disabled={sending || bloqueado}
          className="px-5 py-2.5 rounded-xl font-medium text-slate-950 text-sm disabled:opacity-50"
          style={{ background: "var(--brand)" }}
        >
          {sending ? "…" : "Enviar"}
        </button>
      </form>
    </div>
  );
}
