"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useApp } from "@/contexts/AppContext";
import {
  api,
  type InboxConversation,
  type InboxMessage,
} from "@/lib/api-client";
import { StatusBadge } from "@/components/ui/StatusBadge";

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
      return "En cola";
    case "con_agente":
      return "Con agente";
    case "cerrado":
      return "Cerrada";
    default:
      return estado;
  }
}

export function InboxPanel() {
  const { tenantSlug, isAdmin, selectTicket } = useApp();
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
  const [hint, setHint] = useState("");

  const refreshList = useCallback(async () => {
    const res = await api.inboxConversations(
      filtro ? { estado: filtro } : undefined,
      slug,
    );
    setConvs(res.conversaciones || []);
  }, [filtro, slug]);

  const openConv = useCallback(
    async (id: string) => {
      setSelected(id);
      const res = await api.inboxConversation(id, slug);
      setDetail(res.conversacion);
      setMensajes(res.mensajes || []);
    },
    [slug],
  );

  useEffect(() => {
    refreshList().catch(() => setConvs([]));
  }, [refreshList]);

  // Sincroniza hilo abierto + cola (mensajes del portal en vivo)
  useEffect(() => {
    const tick = () => {
      void refreshList().catch(() => {});
      if (selected) {
        void openConv(selected).catch(() => {});
      }
    };
    const id = window.setInterval(tick, 3000);
    return () => window.clearInterval(id);
  }, [selected, refreshList, openConv]);

  const onInject = async (e: FormEvent) => {
    e.preventDefault();
    if (!isAdmin) return;
    setBusy(true);
    setHint("");
    try {
      const res = await api.inboxSimulate(
        { telefono: injectTel, texto: injectText, usar_llama: false },
        slug,
      );
      setHint(res.respuesta || `Estado: ${res.estado}`);
      await refreshList();
      if (res.conversacion_id) await openConv(res.conversacion_id);
    } catch (err) {
      setHint(err instanceof Error ? err.message : "Error");
    } finally {
      setBusy(false);
    }
  };

  const onClaim = async () => {
    if (!selected) return;
    await api.inboxClaim(selected, slug);
    await openConv(selected);
    await refreshList();
  };

  const onAssignSelf = async () => {
    if (!selected || !isAdmin) return;
    await api.inboxAssign(
      selected,
      { agente_id: "admin@ops-hub.demo", agente_nombre: "Administración" },
      slug,
    );
    await openConv(selected);
    await refreshList();
  };

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!selected || !reply.trim()) return;
    setBusy(true);
    try {
      await api.inboxSend(selected, reply.trim(), slug);
      setReply("");
      await openConv(selected);
      await refreshList();
    } finally {
      setBusy(false);
    }
  };

  const onClose = async () => {
    if (!selected) return;
    await api.inboxClose(selected, slug);
    await openConv(selected);
    await refreshList();
  };

  const openConvs = convs.filter((c) => c.estado !== "cerrado");
  const visible = filtro ? convs : openConvs;

  return (
    <div className="flex-1 min-h-0 flex flex-col p-4 gap-3 overflow-hidden">
      <div className="flex flex-wrap justify-between gap-2 items-end">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-widest text-cyan-400/80">
            Canal abonado
          </p>
          <h2 className="text-xl font-semibold text-slate-50">Bandeja de conversaciones</h2>
          <p className="text-sm text-slate-400">
            Portal web · N1 automático · transferencia a agente
          </p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <select
            value={filtro}
            onChange={(e) => setFiltro(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
          >
            <option value="">Abiertas</option>
            <option value="bot">Bot N1</option>
            <option value="espera_agente">En cola</option>
            <option value="con_agente">Con agente</option>
            <option value="cerrado">Cerradas</option>
          </select>
          {isAdmin && (
            <button
              type="button"
              onClick={() => setInjectOpen((v) => !v)}
              className="text-[11px] px-2.5 py-1.5 rounded-lg border border-slate-700 text-slate-400 hover:border-slate-500"
            >
              {injectOpen ? "Ocultar herramientas" : "Herramientas de canal"}
            </button>
          )}
        </div>
      </div>

      {isAdmin && injectOpen && (
        <form
          onSubmit={onInject}
          className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 grid grid-cols-1 md:grid-cols-[1fr_2fr_auto] gap-2"
        >
          <p className="md:col-span-3 text-[11px] text-slate-500">
            Inyectar mensaje entrante (solo administración · pruebas internas).
          </p>
          <input
            value={injectTel}
            onChange={(e) => setInjectTel(e.target.value)}
            placeholder="Teléfono E.164"
            className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono"
            required
          />
          <input
            value={injectText}
            onChange={(e) => setInjectText(e.target.value)}
            placeholder="Texto del mensaje entrante…"
            className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
            required
          />
          <button
            type="submit"
            disabled={busy}
            className="text-xs px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200"
          >
            Inyectar entrada
          </button>
          {hint && (
            <p className="md:col-span-3 text-[11px] text-slate-400 font-mono">{hint}</p>
          )}
        </form>
      )}

      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-3 overflow-hidden">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 overflow-y-auto p-2 space-y-1.5">
          {!visible.length ? (
            <p className="text-xs text-slate-500 p-2">
              No hay conversaciones abiertas. Los mensajes entrantes aparecerán aquí.
            </p>
          ) : (
            visible.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => openConv(c.id)}
                className={`w-full text-left p-2.5 rounded-lg border transition-colors ${
                  selected === c.id
                    ? "border-cyan-500/40 bg-cyan-500/10"
                    : "border-slate-800 hover:border-slate-600"
                }`}
              >
                <div className="flex justify-between gap-1">
                  <span className="font-mono text-[11px] text-cyan-300">{c.telefono}</span>
                  <StatusBadge value={estadoLabel(c.estado)} />
                </div>
                <p className="text-[11px] text-slate-400 truncate mt-0.5">
                  {c.abonado?.nombre || "Sin identificar"} · {canalLabel(c)}
                </p>
                {c.ticket_id && (
                  <p className="text-[10px] text-amber-400/90 mt-0.5">{c.ticket_id}</p>
                )}
              </button>
            ))
          )}
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950/40 flex flex-col min-h-0 overflow-hidden">
          {!detail ? (
            <p className="text-sm text-slate-500 p-4">Seleccioná una conversación de la cola.</p>
          ) : (
            <>
              <div className="p-3 border-b border-slate-800 flex flex-wrap gap-2 items-center justify-between">
                <div>
                  <p className="text-sm text-slate-100">
                    {detail.abonado?.nombre || "Cliente"} · {detail.telefono}
                  </p>
                  <p className="text-[11px] text-slate-500 font-mono">
                    {estadoLabel(detail.estado)} · {canalLabel(detail)}
                    {detail.agente_id ? ` · ${detail.agente_id}` : ""}
                    {detail.abonado
                      ? ` · ${detail.abonado.servicio} · ${detail.abonado.estado} · deuda $${detail.abonado.deuda_monto}`
                      : ""}
                  </p>
                </div>
                <div className="flex gap-2 flex-wrap">
                  {(detail.estado === "espera_agente" || detail.estado === "bot") && (
                    <button
                      type="button"
                      onClick={onClaim}
                      className="text-[11px] px-2 py-1 rounded border border-emerald-500/30 text-emerald-300"
                    >
                      Tomar
                    </button>
                  )}
                  {isAdmin && detail.estado !== "cerrado" && (
                    <button
                      type="button"
                      onClick={onAssignSelf}
                      className="text-[11px] px-2 py-1 rounded border border-violet-500/30 text-violet-300"
                    >
                      Reasignar (admin)
                    </button>
                  )}
                  {detail.estado !== "cerrado" && (
                    <button
                      type="button"
                      onClick={onClose}
                      className="text-[11px] px-2 py-1 rounded border border-slate-600 text-slate-300"
                    >
                      Cerrar
                    </button>
                  )}
                  {detail.ticket_id && (
                    <Link
                      href="/soporte"
                      onClick={() => selectTicket(detail.ticket_id)}
                      className="text-[11px] px-2 py-1 rounded border border-amber-500/30 text-amber-300"
                    >
                      Ticket {detail.ticket_id}
                    </Link>
                  )}
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {mensajes.map((m) => (
                  <div
                    key={m.id}
                    className={`max-w-[85%] px-3 py-2 rounded-xl text-sm ${
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
                    <p className="whitespace-pre-wrap">{m.texto}</p>
                  </div>
                ))}
              </div>
              {detail.estado !== "cerrado" && (
                <form onSubmit={onSend} className="p-3 border-t border-slate-800 flex gap-2">
                  <input
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    placeholder="Escribí la respuesta al abonado…"
                    className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm"
                    disabled={busy || detail.estado === "bot"}
                  />
                  <button
                    type="submit"
                    disabled={busy || !reply.trim() || detail.estado === "bot"}
                    className="px-4 py-2 rounded-lg text-sm font-semibold text-slate-950 disabled:opacity-40"
                    style={{ background: "var(--brand)" }}
                  >
                    Enviar
                  </button>
                </form>
              )}
              {detail.estado === "bot" && (
                <p className="px-3 pb-3 text-[11px] text-slate-500">
                  El bot N1 está atendiendo. Tomá la conversación para responder como agente.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
