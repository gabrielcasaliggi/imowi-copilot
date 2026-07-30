"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useApp } from "@/contexts/AppContext";
import {
  api,
  type InboxConversation,
  type InboxMessage,
} from "@/lib/api-client";
import { StatusBadge } from "@/components/ui/StatusBadge";

/**
 * Consola del agente: mesa de trabajo sobre el ticket tomado.
 * El chat es el hilo del canal (abonado), no el asistente N1.
 */
export function ChatPanel() {
  const { isAdmin, ticketFormacion, tenantSlug, updateTicket } = useApp();
  const slug = isAdmin ? tenantSlug : undefined;

  const [conv, setConv] = useState<InboxConversation | null>(null);
  const [mensajes, setMensajes] = useState<InboxMessage[]>([]);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState("");
  const [loadingConv, setLoadingConv] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const seq = useRef(0);

  const loadCanal = useCallback(async () => {
    const tid = ticketFormacion?.id;
    if (!tid) {
      setConv(null);
      setMensajes([]);
      return;
    }
    const n = ++seq.current;
    setLoadingConv(true);
    try {
      const res = await api.ticketConversation(tid, slug);
      if (n !== seq.current) return;
      setConv(res.conversacion);
      setMensajes(res.mensajes || []);
    } catch (err) {
      if (n !== seq.current) return;
      setHint(err instanceof Error ? err.message : "No se pudo cargar el chat del canal");
      setConv(null);
      setMensajes([]);
    } finally {
      if (n === seq.current) setLoadingConv(false);
    }
  }, [ticketFormacion?.id, slug]);

  useEffect(() => {
    void loadCanal();
  }, [loadCanal]);

  useEffect(() => {
    if (!ticketFormacion?.id || !conv?.id) return;
    const id = window.setInterval(() => {
      void loadCanal();
    }, 3000);
    return () => window.clearInterval(id);
  }, [ticketFormacion?.id, conv?.id, loadCanal]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes]);

  if (isAdmin) return null;

  if (!ticketFormacion) {
    return (
      <div className="flex flex-col flex-1 min-h-0 items-center justify-center p-8 text-center gap-4">
        <div className="max-w-md space-y-2">
          <h2 className="font-semibold text-slate-50 text-lg">Consola</h2>
          <p className="text-sm text-slate-400 leading-relaxed">
            Mesa de trabajo con el cliente: chat del canal + contexto del caso que tomaste.
          </p>
          <p className="text-xs text-slate-500 leading-relaxed">
            Todavía no hay un ticket activo. Tomá uno libre en la Cola.
          </p>
        </div>
        <Link
          href="/tickets"
          className="text-sm font-medium px-4 py-2.5 rounded-xl border border-cyan-500/40 text-cyan-200 hover:bg-cyan-500/12"
        >
          Ir a la Cola
        </Link>
      </div>
    );
  }

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!conv?.id || !reply.trim()) return;
    setBusy(true);
    setHint("");
    try {
      if (conv.estado === "bot" || conv.estado === "espera_agente") {
        try {
          await api.inboxClaim(conv.id, slug);
        } catch {
          /* inboxSend también puede auto-tomar */
        }
      }
      await api.inboxSend(conv.id, reply.trim(), slug);
      setReply("");
      await loadCanal();
    } catch (err) {
      setHint(err instanceof Error ? err.message : "Error al enviar");
    } finally {
      setBusy(false);
    }
  };

  const onMarcarResuelto = async () => {
    setBusy(true);
    setHint("");
    try {
      await updateTicket({
        estado: "Cerrado",
        resolucion_tecnica: "Resuelto en consola N2",
      });
      setHint("Ticket cerrado. Si aplica, proponé una mejora a la KB en el panel derecho.");
    } catch (err) {
      setHint(err instanceof Error ? err.message : "No se pudo cerrar");
    } finally {
      setBusy(false);
    }
  };

  const puedeEscribir = Boolean(conv && conv.estado !== "cerrado");

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="chat-action-bar px-4 py-3 flex justify-between items-start flex-wrap gap-3">
        <div>
          <h2 className="font-semibold text-slate-50 text-base">Consola</h2>
          <p className="text-[11px] font-mono text-slate-400 mt-0.5">
            Ticket {ticketFormacion.id}
            {ticketFormacion.linea ? ` · ${ticketFormacion.linea}` : ""}
            {ticketFormacion.categoria ? ` · ${ticketFormacion.categoria}` : ""}
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5 items-center">
            {ticketFormacion.nivel && <StatusBadge value={ticketFormacion.nivel} />}
            <StatusBadge value={ticketFormacion.estado} />
            {conv && (
              <span className="text-[10px] font-mono text-slate-500">
                Canal · {conv.abonado?.nombre || conv.telefono || "abonado"}
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {ticketFormacion.estado !== "Cerrado" && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void onMarcarResuelto()}
              className="text-xs font-medium px-3.5 py-2 rounded-lg border border-emerald-500/40 text-emerald-200 hover:bg-emerald-500/12 disabled:opacity-50"
            >
              Resolver ticket
            </button>
          )}
          <Link
            href="/tickets"
            className="text-xs font-medium px-3.5 py-2 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800/50"
          >
            Volver a Cola
          </Link>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2 min-h-0">
        {loadingConv && !mensajes.length ? (
          <p className="text-sm text-slate-500">Cargando chat del canal…</p>
        ) : !conv ? (
          <div className="space-y-2 max-w-lg">
            <p className="text-sm text-slate-400 leading-relaxed">
              Este ticket no tiene conversación de canal ligada (WhatsApp / portal).
            </p>
            <p className="text-xs text-slate-500 leading-relaxed">
              Usá el panel derecho para notas, seguimiento y proponer a KB. El chat en vivo
              aparece cuando el bot armó el ticket desde el canal.
            </p>
          </div>
        ) : !mensajes.length ? (
          <p className="text-sm text-slate-500">Sin mensajes todavía en este hilo.</p>
        ) : (
          mensajes.map((m) => (
            <div
              key={m.id}
              className={`max-w-[90%] px-3 py-2 rounded-xl text-sm whitespace-pre-wrap ${
                m.autor === "cliente"
                  ? "ml-auto bg-cyan-500/15 text-slate-100"
                  : m.autor === "bot"
                    ? "bg-slate-800/80 text-slate-300"
                    : "bg-violet-500/15 text-slate-100"
              }`}
            >
              <p className="text-[9px] font-mono uppercase text-slate-500 mb-0.5">
                {m.autor === "cliente" ? "abonado" : m.autor}
              </p>
              {m.texto}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>

      {conv && conv.estado !== "cerrado" && (
        <form
          onSubmit={onSend}
          className="px-4 py-3 border-t border-slate-800/80 flex gap-2 shrink-0"
        >
          <input
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            placeholder="Responder al abonado…"
            disabled={busy || !puedeEscribir}
            className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={busy || !reply.trim() || !puedeEscribir}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-slate-950 disabled:opacity-40"
            style={{ background: "var(--brand)" }}
          >
            Enviar
          </button>
        </form>
      )}
      {hint && (
        <p className="px-4 pb-3 text-[11px] text-amber-400/90 font-mono">{hint}</p>
      )}
    </div>
  );
}
