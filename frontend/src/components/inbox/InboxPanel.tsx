"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import {
  api,
  type InboxConversation,
  type InboxMessage,
} from "@/lib/api-client";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useToast } from "@/components/ui/Toast";
import {
  ChatMessageBubble,
  MessagesEmptyIcon,
  SendIcon,
} from "@/components/ui/ChatMessageBubble";

function canalLabel(c: InboxConversation): string {
  const raw = c.canal_display || c.canal || "";
  if (raw === "Web" || raw === "web") return "Web";
  if (raw === "simulate" || raw === "whatsapp" || raw === "WhatsApp" || !raw) return "WhatsApp";
  return raw;
}

function estadoLabel(estado: string): string {
  switch (estado) {
    case "bot":
      return "Bot N1";
    case "espera_agente":
      return "Espera agente";
    case "con_agente":
      return "Con agente";
    case "cerrado":
      return "Cerrada";
    default:
      return estado;
  }
}

export function InboxPanel() {
  const { tenantSlug, isAdmin, can, selectTicket } = useApp();
  const router = useRouter();
  const { push: toast } = useToast();
  const slug = isAdmin ? tenantSlug : undefined;
  const [convs, setConvs] = useState<InboxConversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [mensajes, setMensajes] = useState<InboxMessage[]>([]);
  const [detail, setDetail] = useState<InboxConversation | null>(null);
  const [filtro, setFiltro] = useState("");
  const [reply, setReply] = useState("");
  const [injectOpen, setInjectOpen] = useState(false);
  const [injectTel, setInjectTel] = useState("");
  const [injectText, setInjectText] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const detailSeq = useRef(0);
  const claimingRef = useRef(false);

  const refreshList = useCallback(async () => {
    const res = await api.inboxConversations(
      filtro ? { estado: filtro } : undefined,
      slug,
    );
    setConvs(res.conversaciones || []);
  }, [filtro, slug]);

  const openConv = useCallback(
    async (id: string) => {
      const seq = ++detailSeq.current;
      setSelected(id);
      const res = await api.inboxConversation(id, slug);
      if (seq !== detailSeq.current) return;
      setDetail(res.conversacion);
      setMensajes(res.mensajes || []);
    },
    [slug],
  );

  const closeDetail = () => {
    setSelected(null);
    setDetail(null);
    setMensajes([]);
  };

  useEffect(() => {
    refreshList().catch(() => setConvs([]));
  }, [refreshList]);

  useEffect(() => {
    const tick = () => {
      if (claimingRef.current) return;
      void refreshList().catch(() => {});
      if (selected) {
        void openConv(selected).catch(() => {});
      }
    };
    const id = window.setInterval(tick, 3000);
    return () => window.clearInterval(id);
  }, [selected, refreshList, openConv]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes]);

  const onInject = async (e: FormEvent) => {
    e.preventDefault();
    if (!isAdmin) return;
    setBusy(true);
    try {
      const res = await api.inboxSimulate(
        { telefono: injectTel, texto: injectText, usar_llama: false },
        slug,
      );
      toast(res.respuesta || `Estado: ${res.estado}`, "info");
      await refreshList();
      if (res.conversacion_id) await openConv(res.conversacion_id);
    } catch (err) {
      toast(err instanceof Error ? err.message : "Error", "danger");
    } finally {
      setBusy(false);
    }
  };

  const onClaimChannel = async () => {
    if (!selected) return;
    setBusy(true);
    claimingRef.current = true;
    try {
      const res = await api.inboxClaim(selected, slug);
      detailSeq.current += 1;
      if (res.conversacion) setDetail(res.conversacion);
      await openConv(selected);
      await refreshList();
      toast("Caso tomado en el canal", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "No se pudo tomar el caso", "danger");
    } finally {
      claimingRef.current = false;
      setBusy(false);
    }
  };

  const onClaimAndOpenConsole = async () => {
    if (!detail?.ticket_id) return;
    setBusy(true);
    claimingRef.current = true;
    try {
      const res = await api.claimTicket(detail.ticket_id, slug);
      await selectTicket(res.ticket.id);
      toast("Ticket tomado · abriendo Consola", "success");
      router.push(`/soporte?ticket=${encodeURIComponent(res.ticket.id)}`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "No se pudo tomar el ticket", "danger");
    } finally {
      claimingRef.current = false;
      setBusy(false);
    }
  };

  const onAssignSelf = async () => {
    if (!selected || !isAdmin) return;
    setBusy(true);
    claimingRef.current = true;
    try {
      const res = await api.inboxAssign(
        selected,
        { agente_id: "admin@ops-hub.demo", agente_nombre: "Administración" },
        slug,
      );
      detailSeq.current += 1;
      if (res.conversacion) setDetail(res.conversacion);
      await openConv(selected);
      await refreshList();
      toast("Conversación reasignada", "success");
    } catch (err) {
      toast(err instanceof Error ? err.message : "No se pudo reasignar", "danger");
    } finally {
      claimingRef.current = false;
      setBusy(false);
    }
  };

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!selected || !reply.trim()) return;
    setBusy(true);
    claimingRef.current = true;
    try {
      if (detail?.estado === "bot" || detail?.estado === "espera_agente") {
        try {
          const claimed = await api.inboxClaim(selected, slug);
          if (claimed.conversacion) setDetail(claimed.conversacion);
        } catch {
          /* inboxSend también auto-toma */
        }
      }
      await api.inboxSend(selected, reply.trim(), slug);
      setReply("");
      await openConv(selected);
      await refreshList();
    } catch (err) {
      toast(err instanceof Error ? err.message : "Error al enviar", "danger");
    } finally {
      claimingRef.current = false;
      setBusy(false);
    }
  };

  const onCloseConfirmed = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await api.inboxClose(selected, slug);
      await openConv(selected);
      await refreshList();
      toast("Conversación cerrada", "success");
      setConfirmClose(false);
    } catch (err) {
      toast(err instanceof Error ? err.message : "No se pudo cerrar", "danger");
    } finally {
      setBusy(false);
    }
  };

  const openConvs = convs.filter((c) => c.estado !== "cerrado");
  const visible = filtro ? convs : openConvs;
  const puedeEscribir = Boolean(detail && detail.estado !== "cerrado");
  const showList = !selected;
  const showDetail = Boolean(selected);

  return (
    <div className="flex-1 min-h-0 flex flex-col p-4 gap-4 overflow-hidden">
      <div className="flex flex-wrap justify-between gap-3 items-end">
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-ecolan-brand">
            Canal abonado
          </p>
          <h2 className="text-xl font-semibold text-slate-50 tracking-tight">Bandeja</h2>
          <p className="text-sm text-slate-400 max-w-xl">
            {isAdmin
              ? "Canal en vivo (WhatsApp / portal). Monitoreo y herramientas de canal."
              : can("tickets.reassign")
                ? "Canal en vivo: monitoreá bot y abonados. La asignación de trabajo N2 se hace en Cola."
                : "Canal en vivo: ves lo que entra. Si hay ticket N2, podés tomarlo y abrir Consola desde acá."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <label className="sr-only" htmlFor="inbox-filtro">
            Filtrar conversaciones
          </label>
          <select
            id="inbox-filtro"
            value={filtro}
            onChange={(e) => setFiltro(e.target.value)}
            className="bg-slate-950 border border-slate-600/80 rounded-lg px-3 py-2 text-xs transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent"
          >
            <option value="">Abiertas</option>
            <option value="bot">Bot N1</option>
            <option value="espera_agente">Espera agente</option>
            <option value="con_agente">Con agente</option>
            <option value="cerrado">Cerradas</option>
          </select>
          {isAdmin && (
            <button
              type="button"
              onClick={() => setInjectOpen((v) => !v)}
              className="text-[11px] px-3 py-2 rounded-lg border border-slate-600/80 text-slate-400 hover:border-slate-500 hover:bg-slate-800/40 transition-all duration-200 ease-in-out"
            >
              {injectOpen ? "Ocultar herramientas" : "Herramientas de canal"}
            </button>
          )}
        </div>
      </div>

      {isAdmin && injectOpen && (
        <form
          onSubmit={onInject}
          className="rounded-xl border border-slate-700/80 bg-slate-950/50 p-4 grid grid-cols-1 md:grid-cols-[1fr_2fr_auto] gap-2.5 shadow-sm"
        >
          <p className="md:col-span-3 text-[11px] text-slate-400">
            Inyectar mensaje entrante (solo administración · pruebas internas).
          </p>
          <label className="sr-only" htmlFor="inject-tel">
            Teléfono
          </label>
          <input
            id="inject-tel"
            value={injectTel}
            onChange={(e) => setInjectTel(e.target.value)}
            placeholder="Teléfono E.164"
            className="bg-slate-950 border border-slate-600/80 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent transition-all duration-200 ease-in-out"
            required
          />
          <label className="sr-only" htmlFor="inject-text">
            Texto del mensaje
          </label>
          <input
            id="inject-text"
            value={injectText}
            onChange={(e) => setInjectText(e.target.value)}
            placeholder="Texto del mensaje entrante…"
            className="bg-slate-950 border border-slate-600/80 rounded-lg px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent transition-all duration-200 ease-in-out"
            required
          />
          <button
            type="submit"
            disabled={busy}
            className="text-xs font-semibold px-3.5 py-2 rounded-lg bg-ecolan-brand text-white hover:bg-ecolan-brand-dark disabled:opacity-50 transition-all duration-200 ease-in-out"
          >
            Inyectar entrada
          </button>
        </form>
      )}

      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-3 overflow-hidden">
        <div
          className={`rounded-xl border border-slate-700/80 bg-slate-950/40 overflow-y-auto p-2 space-y-1 shadow-sm ${
            showDetail ? "hidden lg:block" : ""
          } ${showList ? "block" : ""}`}
        >
          {!visible.length ? (
            <div className="flex flex-col items-center gap-2 p-6 text-center">
              <MessagesEmptyIcon className="h-8 w-8 text-slate-600" />
              <p className="text-xs text-slate-400">
                No hay conversaciones abiertas. Los mensajes entrantes aparecerán aquí.
              </p>
            </div>
          ) : (
            visible.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => void openConv(c.id)}
                className={`w-full text-left px-3 py-3.5 rounded-lg border transition-all duration-200 ease-in-out ${
                  selected === c.id
                    ? "border-ecolan-brand/45 bg-ecolan-brand/10 shadow-sm"
                    : "border-transparent hover:bg-slate-50/5 hover:border-slate-700/60"
                }`}
              >
                <div className="flex justify-between gap-2 items-center">
                  <span className="font-mono text-[11px] font-medium text-ecolan-brand">
                    {c.telefono}
                  </span>
                  <StatusBadge value={estadoLabel(c.estado)} />
                </div>
                <p className="text-[11px] text-slate-400 truncate mt-1">
                  {c.abonado?.nombre || "Sin identificar"} · {canalLabel(c)}
                </p>
                {c.ticket_id && (
                  <p className="text-[10px] font-mono text-amber-400/90 mt-1">{c.ticket_id}</p>
                )}
              </button>
            ))
          )}
        </div>

        <div
          className={`rounded-xl border border-slate-700/80 bg-slate-950/40 flex flex-col min-h-0 overflow-hidden shadow-sm ${
            showDetail ? "flex" : "hidden lg:flex"
          }`}
        >
          {!detail ? (
            <div className="flex flex-col items-center justify-center gap-3 flex-1 p-8 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-ecolan-dark border border-ecolan-brand/20 text-ecolan-brand/60">
                <MessagesEmptyIcon className="h-6 w-6" />
              </div>
              <p className="text-sm font-medium text-slate-300">Seleccioná una conversación</p>
              <p className="text-xs text-slate-500 max-w-xs">
                El hilo en vivo del canal aparecerá aquí.
              </p>
            </div>
          ) : (
            <>
              <div className="chat-action-bar px-4 py-3.5 flex flex-wrap gap-3 items-center justify-between">
                <div className="flex items-start gap-2.5 min-w-0">
                  <button
                    type="button"
                    onClick={closeDetail}
                    className="lg:hidden shrink-0 text-[11px] px-2.5 py-1.5 rounded-lg border border-slate-600/80 text-slate-300 hover:bg-slate-800/50 transition-all duration-200 ease-in-out"
                  >
                    Volver
                  </button>
                  <div className="min-w-0 space-y-1.5">
                    <p className="text-sm font-semibold text-slate-50 truncate tracking-tight">
                      {detail.abonado?.nombre || "Cliente"} · {detail.telefono}
                    </p>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <StatusBadge value={estadoLabel(detail.estado)} />
                      <span className="text-[10px] font-mono text-slate-400">
                        {canalLabel(detail)}
                        {detail.agente_id ? ` · ${detail.agente_id}` : ""}
                      </span>
                    </div>
                    {detail.abonado && (
                      <p className="text-[11px] text-slate-500">
                        {detail.abonado.servicio} · {detail.abonado.estado} · deuda $
                        {detail.abonado.deuda_monto}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex gap-2 flex-wrap">
                  {!isAdmin && detail.ticket_id && detail.estado !== "cerrado" && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onClaimAndOpenConsole()}
                      className="text-[11px] font-semibold px-3 py-1.5 rounded-lg bg-ecolan-brand text-white hover:bg-ecolan-brand-dark disabled:opacity-50 transition-all duration-200 ease-in-out"
                    >
                      Tomar y abrir Consola
                    </button>
                  )}
                  {isAdmin &&
                    (detail.estado === "espera_agente" || detail.estado === "bot") && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onClaimChannel()}
                        className="text-[11px] font-medium px-2.5 py-1.5 rounded-lg border border-emerald-500/40 text-emerald-200 hover:bg-emerald-500/10 disabled:opacity-50 transition-all duration-200 ease-in-out"
                      >
                        Tomar
                      </button>
                    )}
                  {isAdmin && detail.estado !== "cerrado" && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onAssignSelf()}
                      className="text-[11px] font-medium px-2.5 py-1.5 rounded-lg border border-slate-600/80 text-slate-300 hover:bg-slate-800/50 disabled:opacity-50 transition-all duration-200 ease-in-out"
                    >
                      Reasignar (admin)
                    </button>
                  )}
                  {isAdmin && detail.estado !== "cerrado" && (
                    <button
                      type="button"
                      onClick={() => setConfirmClose(true)}
                      className="text-[11px] font-medium px-2.5 py-1.5 rounded-lg border border-slate-600/80 text-slate-300 hover:bg-slate-800/50 transition-all duration-200 ease-in-out"
                    >
                      Cerrar
                    </button>
                  )}
                  {detail.ticket_id && (
                    <Link
                      href={
                        isAdmin
                          ? `/soporte?ticket=${encodeURIComponent(detail.ticket_id)}`
                          : `/tickets`
                      }
                      onClick={() => {
                        if (isAdmin) void selectTicket(detail.ticket_id);
                      }}
                      className="text-[11px] font-medium px-2.5 py-1.5 rounded-lg border border-amber-500/35 text-amber-200 hover:bg-amber-500/10 transition-all duration-200 ease-in-out"
                    >
                      {isAdmin
                        ? `Ticket ${detail.ticket_id}`
                        : `Ver en Cola (${detail.ticket_id})`}
                    </Link>
                  )}
                  {!isAdmin &&
                    !detail.ticket_id &&
                    detail.estado === "espera_agente" && (
                      <Link
                        href="/tickets"
                        className="text-[11px] font-medium px-2.5 py-1.5 rounded-lg border border-ecolan-brand/40 text-ecolan-brand hover:bg-ecolan-brand/10 transition-all duration-200 ease-in-out"
                      >
                        Ir a Cola
                      </Link>
                    )}
                </div>
              </div>
              <div className="chat-thread flex-1 overflow-y-auto p-4 space-y-3">
                {!mensajes.length ? (
                  <p className="text-sm text-slate-500 text-center py-8">Sin mensajes en este hilo.</p>
                ) : (
                  mensajes.map((m) => <ChatMessageBubble key={m.id} message={m} />)
                )}
                <div ref={messagesEndRef} />
              </div>
              {isAdmin && detail.estado !== "cerrado" && (
                <form onSubmit={onSend} className="chat-composer px-4 py-3.5 flex gap-2.5">
                  <label className="sr-only" htmlFor="inbox-reply">
                    Respuesta al abonado
                  </label>
                  <input
                    id="inbox-reply"
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    placeholder="Escribí la respuesta al abonado…"
                    className="flex-1 bg-slate-950/80 border border-slate-600/80 rounded-xl px-4 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 disabled:opacity-50 transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent"
                    disabled={busy || !puedeEscribir}
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
              {!isAdmin && (
                <p className="px-4 py-3 text-[11px] text-slate-400 border-t border-slate-800/80">
                  {detail.ticket_id
                    ? "Monitoreo del canal. Usá “Tomar y abrir Consola” para atender al abonado."
                    : (
                      <>
                        Solo monitoreo. Cuando el bot arme el ticket N2, podés tomarlo acá o en{" "}
                        <Link href="/tickets" className="text-ecolan-brand hover:text-ecolan-brand-dark transition-colors duration-200">
                          Cola
                        </Link>
                        .
                      </>
                    )}
                </p>
              )}
              {isAdmin && detail.estado === "bot" && (
                <p className="px-4 pb-3 text-[11px] text-slate-500">
                  El bot N1 está atendiendo. Podés pulsar Tomar o escribir y se te asigna el caso.
                </p>
              )}
            </>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmClose}
        title="¿Cerrar conversación?"
        description="El abonado no podrá seguir escribiendo en este hilo. Esta acción no se puede deshacer desde la bandeja."
        confirmLabel="Cerrar conversación"
        danger
        busy={busy}
        onCancel={() => setConfirmClose(false)}
        onConfirm={() => void onCloseConfirmed()}
      />
    </div>
  );
}
