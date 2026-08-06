"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useApp } from "@/contexts/AppContext";
import {
  api,
  type InboxConversation,
  type InboxMessage,
} from "@/lib/api-client";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { SlaBadge } from "@/components/ui/GlassCard";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/Toast";
import {
  ChatMessageBubble,
  MessagesEmptyIcon,
  SendIcon,
} from "@/components/ui/ChatMessageBubble";
import { getBranding } from "@/lib/brand";
import { useStickToBottom } from "@/hooks/useStickToBottom";
import { formatRelative, formatSlaRemaining } from "@/lib/formatTime";

const SILENT_FAIL_BANNER_AFTER = 3;

/**
 * Consola del agente: mesa de trabajo sobre el ticket tomado.
 * El chat es el hilo del canal (abonado), no el asistente N1.
 */
export function ChatPanel() {
  const {
    isAdmin,
    ticketFormacion,
    tenantSlug,
    updateTicket,
    registerConsoleComposer,
  } = useApp();
  const { push: toast } = useToast();
  const botName = getBranding().botDisplayName;
  const slug = isAdmin ? tenantSlug : undefined;

  const [conv, setConv] = useState<InboxConversation | null>(null);
  const [mensajes, setMensajes] = useState<InboxMessage[]>([]);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingConv, setLoadingConv] = useState(false);
  const [confirmResolve, setConfirmResolve] = useState(false);
  const [confirmRelease, setConfirmRelease] = useState(false);
  const [pollOffline, setPollOffline] = useState(false);
  const { threadRef, bottomRef, onScroll, forceStick } = useStickToBottom([mensajes]);
  const seq = useRef(0);
  const silentFails = useRef(0);
  const replyRef = useRef<HTMLTextAreaElement>(null);

  const loadCanal = useCallback(async (opts?: { silent?: boolean }) => {
    const tid = ticketFormacion?.id;
    if (!tid) {
      setConv(null);
      setMensajes([]);
      return;
    }
    const n = ++seq.current;
    if (!opts?.silent) setLoadingConv(true);
    try {
      const res = await api.ticketConversation(tid, slug);
      if (n !== seq.current) return;
      setConv(res.conversacion);
      setMensajes(res.mensajes || []);
      silentFails.current = 0;
      setPollOffline(false);
    } catch (err) {
      if (n !== seq.current) return;
      if (!opts?.silent) {
        toast(err instanceof Error ? err.message : "No se pudo cargar el chat del canal", "danger");
        setConv(null);
        setMensajes([]);
      } else {
        silentFails.current += 1;
        if (silentFails.current >= SILENT_FAIL_BANNER_AFTER) {
          setPollOffline(true);
        }
      }
    } finally {
      if (n === seq.current && !opts?.silent) setLoadingConv(false);
    }
  }, [ticketFormacion?.id, slug, toast]);

  useEffect(() => {
    void loadCanal();
  }, [loadCanal]);

  useEffect(() => {
    if (!ticketFormacion?.id || !conv?.id) return;
    const id = window.setInterval(() => {
      void loadCanal({ silent: true });
    }, 3000);
    return () => window.clearInterval(id);
  }, [ticketFormacion?.id, conv?.id, loadCanal]);

  useEffect(() => {
    forceStick();
  }, [ticketFormacion?.id, forceStick]);

  useEffect(() => {
    const insert = (text: string) => {
      const chunk = (text || "").trim();
      if (!chunk) return;
      setReply((prev) => (prev.trim() ? `${prev.trimEnd()}\n${chunk}` : chunk));
      window.setTimeout(() => {
        replyRef.current?.focus();
        const el = replyRef.current;
        if (el) {
          const len = el.value.length;
          el.setSelectionRange(len, len);
        }
      }, 0);
    };
    registerConsoleComposer(insert);
    return () => registerConsoleComposer(null);
  }, [registerConsoleComposer]);

  if (isAdmin) return null;

  if (!ticketFormacion) {
    return (
      <div className="flex flex-col flex-1 min-h-0 items-center justify-center p-8 text-center gap-5">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-ecolan-dark border border-ecolan-brand/25 text-ecolan-brand shadow-sm">
          <MessagesEmptyIcon className="h-7 w-7" />
        </div>
        <div className="max-w-md space-y-2">
          <h2 className="font-semibold text-slate-50 text-lg tracking-tight">Consola</h2>
          <p className="text-sm text-slate-400 leading-relaxed">
            Mesa de trabajo con el cliente: chat del canal + contexto del caso que tomaste.
          </p>
          <p className="text-xs text-slate-500 leading-relaxed">
            Todavía no hay un ticket activo. Tomá uno libre en la Cola o desde Bandeja con
            “Tomar y abrir Consola”.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 justify-center">
          <Link
            href="/tickets"
            className="inline-flex items-center gap-2 text-sm font-semibold px-4 py-2.5 rounded-xl bg-ecolan-brand text-white hover:bg-ecolan-brand-dark shadow-sm transition-all duration-200 ease-in-out"
          >
            Ir a la Cola
          </Link>
          <Link
            href="/inbox"
            className="text-sm font-medium px-4 py-2.5 rounded-xl border border-slate-600/80 text-slate-300 hover:bg-slate-800/50 hover:border-slate-500 transition-all duration-200 ease-in-out"
          >
            Ir a Bandeja
          </Link>
        </div>
      </div>
    );
  }

  const onSend = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!conv?.id || !reply.trim()) return;
    setBusy(true);
    forceStick();
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
      toast(err instanceof Error ? err.message : "Error al enviar", "danger");
    } finally {
      setBusy(false);
    }
  };

  const onComposerKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void onSend();
    }
  };

  const onMarcarResuelto = async () => {
    setBusy(true);
    try {
      await updateTicket({
        estado: "Cerrado",
        resolucion_tecnica: "Resuelto en consola N2",
      });
      toast("Ticket cerrado. Si aplica, proponé una mejora a la KB en el panel derecho.", "success");
      setConfirmResolve(false);
    } catch (err) {
      toast(err instanceof Error ? err.message : "No se pudo cerrar", "danger");
    } finally {
      setBusy(false);
    }
  };

  const onLiberar = async () => {
    if (!conv?.id) return;
    setBusy(true);
    try {
      await api.inboxRelease(conv.id, slug);
      toast("Chat liberado · volvió a la cola del canal", "success");
      setConfirmRelease(false);
      await loadCanal();
    } catch (err) {
      toast(err instanceof Error ? err.message : "No se pudo liberar", "danger");
    } finally {
      setBusy(false);
    }
  };

  const puedeEscribir = Boolean(conv && conv.estado !== "cerrado");
  const slaEstado = ticketFormacion.estado_sla || ticketFormacion.intelligence?.sla?.estado_sla;
  const slaRem = formatSlaRemaining({
    slaDueAt: ticketFormacion.sla_due_at || ticketFormacion.intelligence?.sla?.sla_due_at,
    horasRestantes: ticketFormacion.intelligence?.sla?.horas_restantes,
  });

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Header dark Ecolan */}
      <div className="chat-action-bar px-5 py-4 flex justify-between items-start flex-wrap gap-3">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-ecolan-brand animate-pulse" aria-hidden />
            <h2 className="font-semibold text-slate-50 text-base tracking-tight">Consola</h2>
          </div>
          <p className="text-[11px] font-mono text-slate-400">
            Ticket{" "}
            <span className="text-ecolan-brand font-semibold">{ticketFormacion.id}</span>
            {ticketFormacion.linea ? ` · ${ticketFormacion.linea}` : ""}
            {ticketFormacion.categoria ? ` · ${ticketFormacion.categoria}` : ""}
          </p>
          <div className="flex flex-wrap gap-1.5 items-center">
            {ticketFormacion.nivel && <StatusBadge value={ticketFormacion.nivel} />}
            <StatusBadge value={ticketFormacion.estado} />
            <SlaBadge label={ticketFormacion.sla_label} estado={slaEstado} />
            {slaRem && (
              <span className="text-[10px] font-mono text-slate-400 tabular-nums">{slaRem}</span>
            )}
            {ticketFormacion.created_at && (
              <span className="text-[10px] font-mono text-slate-500">
                Abierto {formatRelative(ticketFormacion.created_at)}
              </span>
            )}
            {conv && (
              <span className="inline-flex items-center gap-1.5 text-[10px] font-medium text-slate-400 px-2.5 py-0.5 rounded-full border border-slate-600/60 bg-slate-900/40">
                <span className="h-1.5 w-1.5 rounded-full bg-ecolan-brand/80" aria-hidden />
                Canal · {conv.abonado?.nombre || conv.telefono || "abonado"}
              </span>
            )}
            {conv?.estado === "espera_agente" && (
              <span className="text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border border-amber-500/45 bg-amber-500/15 text-amber-200">
                Espera · {formatRelative(conv.updated_at) || "ahora"}
              </span>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {conv?.estado === "con_agente" && (
            <button
              type="button"
              disabled={busy}
              onClick={() => setConfirmRelease(true)}
              className="text-xs font-medium px-3.5 py-2 rounded-lg border border-amber-500/40 text-amber-200 hover:bg-amber-500/12 disabled:opacity-50 transition-all duration-200 ease-in-out"
            >
              Liberar chat
            </button>
          )}
          {ticketFormacion.estado !== "Cerrado" && (
            <button
              type="button"
              disabled={busy}
              onClick={() => setConfirmResolve(true)}
              className="text-xs font-medium px-3.5 py-2 rounded-lg border border-emerald-500/40 text-emerald-200 hover:bg-emerald-500/12 disabled:opacity-50 transition-all duration-200 ease-in-out"
            >
              Resolver ticket
            </button>
          )}
          <Link
            href="/tickets"
            className="text-xs font-medium px-3.5 py-2 rounded-lg border border-slate-600/80 text-slate-300 hover:bg-slate-800/50 hover:border-slate-500 transition-all duration-200 ease-in-out"
          >
            Volver a Cola
          </Link>
        </div>
      </div>

      {pollOffline && (
        <p
          className="mx-5 mt-2 text-[11px] text-amber-200 border border-amber-500/30 bg-amber-500/10 rounded-lg px-3 py-2"
          role="status"
        >
          Sin conexión con el canal · reintentando…
        </p>
      )}

      {/* Thread */}
      <div
        ref={threadRef}
        onScroll={onScroll}
        className="chat-thread flex-1 overflow-y-auto px-5 py-4 space-y-3 min-h-0"
      >
        {loadingConv && !mensajes.length ? (
          <div className="space-y-3 animate-pulse" aria-busy="true" aria-label="Cargando chat">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className={`h-16 rounded-xl bg-slate-800/60 border border-slate-700/40 ${
                  i % 2 === 0 ? "ml-auto w-3/5" : "mr-auto w-2/3"
                }`}
              />
            ))}
          </div>
        ) : !conv ? (
          <div className="flex flex-col items-start gap-3 max-w-lg py-6">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-800/80 border border-slate-700/60 text-slate-400">
              <MessagesEmptyIcon className="h-5 w-5" />
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium text-slate-200">Sin conversación de canal</p>
              <p className="text-sm text-slate-400 leading-relaxed">
                Este ticket no tiene conversación ligada (WhatsApp / portal).
              </p>
              <p className="text-xs text-slate-500 leading-relaxed">
                Usá el panel derecho para notas, seguimiento y proponer a KB. El chat en vivo
                aparece cuando {botName} armó el ticket desde el canal.
              </p>
            </div>
          </div>
        ) : !mensajes.length ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-ecolan-dark border border-ecolan-brand/20 text-ecolan-brand/70">
              <MessagesEmptyIcon className="h-6 w-6" />
            </div>
            <p className="text-sm font-medium text-slate-300">Sin mensajes todavía</p>
            <p className="text-xs text-slate-500 max-w-xs">
              El hilo del canal aparecerá acá en cuanto haya actividad.
            </p>
          </div>
        ) : (
          mensajes.map((m) => <ChatMessageBubble key={m.id} message={m} />)
        )}
        <div ref={bottomRef} />
      </div>

      {/* Composer */}
      {conv && conv.estado !== "cerrado" && (
        <form onSubmit={(e) => void onSend(e)} className="chat-composer px-5 py-4 flex gap-2.5 shrink-0 items-end">
          <label className="sr-only" htmlFor="console-reply">
            Responder al abonado
          </label>
          <textarea
            id="console-reply"
            ref={replyRef}
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            onKeyDown={onComposerKeyDown}
            rows={2}
            placeholder="Responder al abonado… (Enter envía · Shift+Enter línea nueva)"
            disabled={busy || !puedeEscribir}
            className="flex-1 min-h-[2.75rem] max-h-36 resize-y bg-slate-950/80 border border-slate-600/80 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 disabled:opacity-50 transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent"
          />
          <button
            type="submit"
            disabled={busy || !reply.trim() || !puedeEscribir}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-ecolan-brand hover:bg-ecolan-brand-dark disabled:opacity-40 shadow-sm transition-all duration-200 ease-in-out"
          >
            <SendIcon className="h-4 w-4" />
            Enviar
          </button>
        </form>
      )}

      <ConfirmDialog
        open={confirmResolve}
        title="¿Resolver y cerrar el ticket?"
        description="El ticket pasará a Cerrado. Podés proponer una mejora a la KB después desde el panel de contexto."
        confirmLabel="Resolver ticket"
        busy={busy}
        onCancel={() => setConfirmResolve(false)}
        onConfirm={() => void onMarcarResuelto()}
      />
      <ConfirmDialog
        open={confirmRelease}
        title="¿Liberar el chat?"
        description="La conversación vuelve a la cola del canal (espera agente). Podés volver a tomarla desde Bandeja."
        confirmLabel="Liberar chat"
        busy={busy}
        onCancel={() => setConfirmRelease(false)}
        onConfirm={() => void onLiberar()}
      />
    </div>
  );
}
