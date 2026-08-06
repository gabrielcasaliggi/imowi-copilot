"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
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
import { botEstadoLabel, getBranding } from "@/lib/brand";
import { useStickToBottom } from "@/hooks/useStickToBottom";
import {
  formatDateTime,
  formatRelative,
  formatWaitChip,
} from "@/lib/formatTime";
import {
  isInboxSoundEnabled,
  playHandoffBeep,
  setInboxSoundEnabled,
} from "@/lib/inboxSound";

function canalLabel(c: InboxConversation): string {
  const raw = c.canal_display || c.canal || "";
  if (raw === "Web" || raw === "web") return "Web";
  if (raw === "Telegram" || raw === "telegram") return "Telegram";
  if (raw === "simulate" || raw === "whatsapp" || raw === "WhatsApp" || !raw) return "WhatsApp";
  return raw;
}

function estadoLabel(estado: string): string {
  switch (estado) {
    case "bot":
      return botEstadoLabel();
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

function autorPreviewLabel(autor: string | undefined): string {
  if (autor === "cliente") return "Cliente";
  if (autor === "agente") return "Agente";
  if (autor === "bot") return getBranding().botDisplayNameShort || getBranding().botDisplayName;
  return "";
}

const POLL_LIST_MS = 4000;
const POLL_LIVE_MS = 1500;
const PAGE_SIZE = 50;

export function InboxPanel() {
  const { tenantSlug, isAdmin, can, selectTicket } = useApp();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { push: toast } = useToast();
  const slug = isAdmin ? tenantSlug : undefined;
  const [convs, setConvs] = useState<InboxConversation[]>([]);
  const [listTotal, setListTotal] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [mensajes, setMensajes] = useState<InboxMessage[]>([]);
  const [detail, setDetail] = useState<InboxConversation | null>(null);
  const [filtro, setFiltro] = useState("");
  const [soloMias, setSoloMias] = useState(false);
  const [search, setSearch] = useState("");
  const [searchDebounced, setSearchDebounced] = useState("");
  const [soundOn, setSoundOn] = useState(true);
  const [nowTs, setNowTs] = useState(() => Date.now());
  const [reply, setReply] = useState("");
  const [injectOpen, setInjectOpen] = useState(false);
  const [injectTel, setInjectTel] = useState("");
  const [injectText, setInjectText] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [livePulse, setLivePulse] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const { threadRef, bottomRef, onScroll, forceStick } = useStickToBottom([mensajes]);
  const detailSeq = useRef(0);
  const claimingRef = useRef(false);
  const prevEstadosRef = useRef<Record<string, string>>({});
  const handoffNotifiedRef = useRef<Set<string>>(new Set());
  const selectedRef = useRef<string | null>(null);
  const detailEstadoRef = useRef<string>("");
  const loadedCountRef = useRef(PAGE_SIZE);
  const deepLinkedRef = useRef<string | null>(null);

  selectedRef.current = selected;
  detailEstadoRef.current = detail?.estado || "";

  useEffect(() => {
    setSoundOn(isInboxSoundEnabled());
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => setSearchDebounced(search.trim().toLowerCase()), 200);
    return () => window.clearTimeout(id);
  }, [search]);

  useEffect(() => {
    const id = window.setInterval(() => setNowTs(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  const listParams = useCallback(
    (opts?: { limit?: number; offset?: number }) => {
      const params: {
        estado?: string;
        mias?: boolean;
        limit?: number;
        offset?: number;
      } = {
        limit: opts?.limit ?? Math.min(100, Math.max(PAGE_SIZE, loadedCountRef.current)),
        offset: opts?.offset ?? 0,
      };
      if (filtro) params.estado = filtro;
      if (soloMias) params.mias = true;
      return params;
    },
    [filtro, soloMias],
  );

  const refreshList = useCallback(async () => {
    const params = listParams();
    const res = await api.inboxConversations(params, slug);
    const next = res.conversaciones || [];
    loadedCountRef.current = next.length;
    setListTotal(res.total ?? next.length);
    const prev = prevEstadosRef.current;
    for (const c of next) {
      const before = prev[c.id];
      if (
        before &&
        before !== "espera_agente" &&
        c.estado === "espera_agente" &&
        !handoffNotifiedRef.current.has(c.id)
      ) {
        handoffNotifiedRef.current.add(c.id);
        const quien = c.abonado?.nombre || c.telefono || "Cliente";
        toast(
          `${quien} · ${canalLabel(c)} espera agente`,
          "warning",
        );
        playHandoffBeep();
      }
      prev[c.id] = c.estado;
    }
    prevEstadosRef.current = prev;
    setConvs(next);
  }, [listParams, slug, toast]);

  const loadMore = useCallback(async () => {
    if (loadingMore || convs.length >= listTotal) return;
    setLoadingMore(true);
    try {
      const res = await api.inboxConversations(
        listParams({ limit: PAGE_SIZE, offset: convs.length }),
        slug,
      );
      const more = res.conversaciones || [];
      setConvs((prev) => {
        const seen = new Set(prev.map((c) => c.id));
        const merged = [...prev];
        for (const c of more) {
          if (!seen.has(c.id)) merged.push(c);
        }
        loadedCountRef.current = merged.length;
        return merged;
      });
      setListTotal(res.total ?? listTotal);
    } finally {
      setLoadingMore(false);
    }
  }, [loadingMore, convs.length, listTotal, listParams, slug]);

  const refreshDetail = useCallback(
    async (id: string, opts?: { select?: boolean }) => {
      const seq = ++detailSeq.current;
      if (opts?.select) setSelected(id);
      const res = await api.inboxConversation(id, slug);
      if (seq !== detailSeq.current) return;
      setDetail(res.conversacion);
      setMensajes((prev) => {
        const next = res.mensajes || [];
        if (next.length > prev.length) {
          setLivePulse(true);
          window.setTimeout(() => setLivePulse(false), 600);
        }
        return next;
      });
      // GET detail ya marca leído en backend
      setConvs((prev) =>
        prev.map((c) =>
          c.id === id
            ? { ...c, ...res.conversacion, tiene_no_leidos: false }
            : c,
        ),
      );
    },
    [slug],
  );

  const openConv = useCallback(
    async (id: string) => {
      await refreshDetail(id, { select: true });
    },
    [refreshDetail],
  );

  const closeDetail = () => {
    setSelected(null);
    setDetail(null);
    setMensajes([]);
  };

  useEffect(() => {
    loadedCountRef.current = PAGE_SIZE;
  }, [filtro, soloMias]);

  useEffect(() => {
    refreshList().catch(() => setConvs([]));
  }, [refreshList]);

  useEffect(() => {
    const convId = searchParams.get("conv");
    if (!convId || deepLinkedRef.current === convId) return;
    deepLinkedRef.current = convId;
    void openConv(convId);
  }, [searchParams, openConv]);

  useEffect(() => {
    setSelected(null);
    setDetail(null);
    setMensajes([]);
    handoffNotifiedRef.current.clear();
    loadedCountRef.current = PAGE_SIZE;
    deepLinkedRef.current = null;
  }, [slug]);

  useEffect(() => {
    const watchingLive =
      Boolean(selected) &&
      (detailEstadoRef.current === "bot" || detailEstadoRef.current === "espera_agente");
    const intervalMs = watchingLive ? POLL_LIVE_MS : POLL_LIST_MS;
    const tick = () => {
      if (claimingRef.current) return;
      void refreshList().catch(() => {});
      const id = selectedRef.current;
      if (id) {
        void refreshDetail(id).catch(() => {});
      }
    };
    const id = window.setInterval(tick, intervalMs);
    return () => window.clearInterval(id);
  }, [selected, detail?.estado, refreshList, refreshDetail]);

  useEffect(() => {
    forceStick();
  }, [selected, forceStick]);

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
    forceStick();
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

  const openConvs = useMemo(
    () => convs.filter((c) => c.estado !== "cerrado"),
    [convs],
  );
  const baseVisible = filtro ? convs : openConvs;
  const visible = useMemo(() => {
    if (!searchDebounced) return baseVisible;
    return baseVisible.filter((c) => {
      const hay = [
        c.telefono,
        c.abonado?.nombre,
        c.ticket_id,
        c.ultimo_mensaje_texto,
        c.agente_id,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return hay.includes(searchDebounced);
    });
  }, [baseVisible, searchDebounced]);

  const countAbiertas = !filtro && !searchDebounced ? listTotal || openConvs.length : openConvs.length;
  const countEspera = openConvs.filter((c) => c.estado === "espera_agente").length;
  const canLoadMore = !searchDebounced && convs.length < listTotal;
  const puedeEscribir = Boolean(detail && detail.estado !== "cerrado");
  const showList = !selected;
  const showDetail = Boolean(selected);

  const toggleSound = () => {
    const next = !soundOn;
    setSoundOn(next);
    setInboxSoundEnabled(next);
  };

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
              ? `Canal en vivo (portal / WhatsApp / Telegram). Filtrá por ${getBranding().botDisplayName} (N1) para monitorear al bot.`
              : can("tickets.reassign")
                ? `Canal en vivo: monitoreá a ${getBranding().botDisplayName} (filtro N1) y tomá handoffs. Visitantes se atienden acá. La Cola es solo tickets N2.`
                : "Canal en vivo: tomá chats de abonados y visitantes acá. La Cola es solo para tickets N2 técnicos."}
          </p>
          <p className="text-[11px] font-mono text-slate-500">
            {countAbiertas} abiertas
            {countEspera > 0 ? ` · ${countEspera} en espera` : ""}
            {soloMias ? " · mis chats" : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <label className="sr-only" htmlFor="inbox-search">
            Buscar conversaciones
          </label>
          <input
            id="inbox-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar teléfono, nombre, ticket…"
            className="w-44 sm:w-56 bg-slate-950 border border-slate-600/80 rounded-lg px-3 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent transition-all duration-200 ease-in-out"
          />
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
            <option value="bot">{botEstadoLabel()}</option>
            <option value="espera_agente">Espera agente</option>
            <option value="con_agente">Con agente</option>
            <option value="cerrado">Cerradas</option>
          </select>
          <button
            type="button"
            onClick={() => setSoloMias((v) => !v)}
            className={`text-[11px] px-3 py-2 rounded-lg border transition-all duration-200 ease-in-out ${
              soloMias
                ? "border-ecolan-brand/50 bg-ecolan-brand/15 text-ecolan-brand"
                : "border-slate-600/80 text-slate-400 hover:border-slate-500 hover:bg-slate-800/40"
            }`}
            title="Solo chats asignados a vos"
          >
            Mis chats
          </button>
          <button
            type="button"
            onClick={toggleSound}
            className={`text-[11px] px-3 py-2 rounded-lg border transition-all duration-200 ease-in-out ${
              soundOn
                ? "border-slate-600/80 text-slate-300 hover:bg-slate-800/40"
                : "border-slate-700 text-slate-500 hover:bg-slate-800/40"
            }`}
            title={soundOn ? "Silenciar alerta de handoff" : "Activar alerta de handoff"}
          >
            {soundOn ? "Sonido" : "Mute"}
          </button>
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

      <div className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-3 overflow-hidden">
        <div
          className={`rounded-xl border border-slate-700/80 bg-slate-950/40 overflow-y-auto p-2 space-y-1 shadow-sm ${
            showDetail ? "hidden lg:block" : ""
          } ${showList ? "block" : ""}`}
        >
          {!visible.length ? (
            <div className="flex flex-col items-center gap-2 p-6 text-center">
              <MessagesEmptyIcon className="h-8 w-8 text-slate-600" />
              <p className="text-xs text-slate-400">
                {searchDebounced
                  ? "Ninguna conversación coincide con la búsqueda."
                  : "No hay conversaciones abiertas. Los mensajes entrantes aparecerán aquí."}
              </p>
            </div>
          ) : (
            <>
              {visible.map((c) => {
              const whenIso = c.ultimo_mensaje_at || c.updated_at;
              const rel = formatRelative(whenIso, nowTs);
              const abs = formatDateTime(whenIso);
              const previewAutor = autorPreviewLabel(c.ultimo_mensaje_autor);
              const preview = c.ultimo_mensaje_texto || "";
              return (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => void openConv(c.id)}
                  className={`w-full text-left px-3 py-2.5 rounded-lg border transition-all duration-200 ease-in-out ${
                    selected === c.id
                      ? "border-ecolan-brand/45 bg-ecolan-brand/10 shadow-sm"
                      : c.tiene_no_leidos
                        ? "border-amber-500/30 bg-amber-500/[0.05] hover:border-amber-500/45"
                      : c.estado === "bot"
                        ? "border-emerald-500/25 bg-emerald-500/[0.06] hover:border-emerald-500/40"
                        : c.estado === "espera_agente"
                          ? "border-amber-500/25 bg-amber-500/[0.06] hover:border-amber-500/40"
                          : "border-transparent hover:bg-slate-50/5 hover:border-slate-700/60"
                  }`}
                >
                  <div className="flex justify-between gap-2 items-start">
                    <div className="min-w-0">
                      <p className="font-mono text-[11px] font-medium text-ecolan-brand truncate">
                        {c.telefono}
                      </p>
                      <p className="text-[11px] text-slate-400 truncate mt-0.5">
                        {c.abonado?.nombre ||
                          (c.es_visitante || c.cola_prioridad === "baja"
                            ? "Visitante"
                            : "Sin identificar")}{" "}
                        · {canalLabel(c)}
                      </p>
                    </div>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      {rel && (
                        <time
                          className="text-[10px] font-mono text-slate-500 tabular-nums"
                          dateTime={whenIso}
                          title={abs || undefined}
                        >
                          {rel}
                        </time>
                      )}
                      <div className="flex items-center gap-1">
                        {c.tiene_no_leidos && (
                          <span
                            className="h-2 w-2 rounded-full bg-amber-400 shrink-0"
                            title="Mensaje nuevo del cliente"
                            aria-label="Sin leer"
                          />
                        )}
                        {c.estado === "bot" && (
                          <span className="inline-flex items-center gap-1 text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded border border-emerald-500/40 text-emerald-300">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                            En vivo
                          </span>
                        )}
                        {(c.es_visitante || c.cola_prioridad === "baja") && (
                          <span className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded border border-slate-600/80 text-slate-400">
                            Visitante
                          </span>
                        )}
                        <StatusBadge value={estadoLabel(c.estado)} />
                      </div>
                    </div>
                  </div>
                  {preview && (
                    <p className="text-[11px] text-slate-500 truncate mt-1.5">
                      {previewAutor ? (
                        <span className="text-slate-400">{previewAutor}: </span>
                      ) : null}
                      {preview}
                    </p>
                  )}
                  <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                    {c.estado === "espera_agente" && (
                      <span className="text-[9px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border border-amber-500/45 bg-amber-500/15 text-amber-200">
                        {formatWaitChip(c.updated_at || whenIso, nowTs)}
                      </span>
                    )}
                    {c.ticket_id && (
                      <span className="text-[10px] font-mono text-amber-400/90">{c.ticket_id}</span>
                    )}
                    {(c.es_visitante || c.cola_prioridad === "baja") && !c.ticket_id && (
                      <span className="text-[10px] text-slate-500">Atender acá · no es N2</span>
                    )}
                  </div>
                </button>
              );
            })}
              {canLoadMore && (
                <button
                  type="button"
                  disabled={loadingMore}
                  onClick={() => void loadMore()}
                  className="w-full text-[11px] py-2 rounded-lg border border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-500 disabled:opacity-50"
                >
                  {loadingMore ? "Cargando…" : `Cargar más (${convs.length}/${listTotal})`}
                </button>
              )}
            </>
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
                      {detail.estado === "bot" && (
                        <span
                          className={`inline-flex items-center gap-1 text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded border border-emerald-500/40 text-emerald-300 transition-opacity ${
                            livePulse ? "opacity-100" : "opacity-80"
                          }`}
                        >
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                          Monitoreo en vivo
                        </span>
                      )}
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
                  {/* Canal en vivo (visitantes / handoff sin N2): tomar en Bandeja */}
                  {(detail.estado === "espera_agente" || detail.estado === "bot") && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onClaimChannel()}
                      className="text-[11px] font-semibold px-3 py-1.5 rounded-lg bg-ecolan-brand text-white hover:bg-ecolan-brand-dark disabled:opacity-50 transition-all duration-200 ease-in-out"
                    >
                      Tomar chat
                    </button>
                  )}
                  {/* Ticket N2 armado: tomar + Consola (Cola) */}
                  {detail.ticket_id && detail.estado !== "cerrado" && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onClaimAndOpenConsole()}
                      className="text-[11px] font-medium px-3 py-1.5 rounded-lg border border-ecolan-brand/45 text-ecolan-brand hover:bg-ecolan-brand/10 disabled:opacity-50 transition-all duration-200 ease-in-out"
                    >
                      Tomar y abrir Consola
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
                  {detail.estado !== "cerrado" && (
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
                </div>
              </div>
              <div
                ref={threadRef}
                onScroll={onScroll}
                className="chat-thread flex-1 overflow-y-auto p-4 space-y-3"
              >
                {!mensajes.length ? (
                  <p className="text-sm text-slate-500 text-center py-8">Sin mensajes en este hilo.</p>
                ) : (
                  mensajes.map((m) => <ChatMessageBubble key={m.id} message={m} />)
                )}
                <div ref={bottomRef} />
              </div>
              {detail.estado !== "cerrado" && (
                <form onSubmit={onSend} className="chat-composer px-4 py-3.5 flex gap-2.5">
                  <label className="sr-only" htmlFor="inbox-reply">
                    Respuesta al abonado
                  </label>
                  <input
                    id="inbox-reply"
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    placeholder={
                      detail.es_visitante || detail.cola_prioridad === "baja"
                        ? "Respuesta al visitante…"
                        : "Escribí la respuesta al abonado…"
                    }
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
              {detail.estado === "espera_agente" && (
                <p className="px-4 pb-3 text-[11px] text-slate-500">
                  {detail.es_visitante || detail.cola_prioridad === "baja"
                    ? "Visitante comercial/consulta: tomá el chat acá en Bandeja (no va a Cola N2)."
                    : `Handoff de ${getBranding().botDisplayName}: tomá el chat acá. Si hay ticket N2, también podés abrir Consola.`}
                </p>
              )}
              {detail.estado === "bot" && (
                <p className="px-4 pb-3 text-[11px] text-emerald-400/80">
                  Monitoreo en vivo · {getBranding().botDisplayName} (N1) está atendiendo
                  (actualización ~1,5 s). Podés pulsar Tomar chat o escribir y se te asigna el caso.
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
