"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";
import { api, setUnauthorizedHandler } from "@/lib/api-client";
import {
  clearHistorial,
  clearSessionId,
  clearTenantSlug,
  clearToken,
  getSessionId,
  getTenantSlug,
  getToken,
  loadHistorial,
  newSessionId,
  saveHistorial,
  setTenantSlug,
  setToken,
} from "@/lib/storage";
import type {
  AlertaRed,
  CasoConversacion,
  ChatMessage,
  FichaJsc,
  LineaCambiada,
  KBArticle,
  LoginResponse,
  MeResponse,
  Organization,
  StatsResponse,
  TelemetryElement,
  TenantContext,
  Ticket,
  TicketEvent,
  TicketNotification,
  TicketSimilar,
  FlujoOperativo,
} from "@/lib/types";

interface AppContextValue {
  ready: boolean;
  user: MeResponse | null;
  isAdmin: boolean;
  orgs: Organization[];
  tenantSlug: string;
  tenantContext: TenantContext | null;
  historial: ChatMessage[];
  traces: string[];
  sessionId: string;
  estadoConversacion: string | null;
  fichaJsc: FichaJsc | null;
  lineaDetectada: string;
  ticketFormacion: Ticket | null;
  ticketTimeline: TicketEvent[];
  notifications: TicketNotification[];
  tickets: Ticket[];
  telemetry: TelemetryElement[];
  kb: KBArticle[];
  stats: StatsResponse | null;
  sending: boolean;
  networkAlert: string | null;
  alertasRed: AlertaRed[];
  casoActivo: CasoConversacion | null;
  lineaCambiada: LineaCambiada | null;
  ticketsSimilares: TicketSimilar[];
  ticketExistente: TicketSimilar | null;
  intencionPendiente: string | null;
  flujoOperativo: FlujoOperativo | null;
  login: (usuario: string, password: string) => Promise<void>;
  logout: () => void;
  setTenant: (slug: string) => Promise<void>;
  refreshData: () => Promise<void>;
  sendMessage: (
    text: string,
    forzar?: boolean,
    accionOperador?: string,
    historialBase?: ChatMessage[],
  ) => Promise<void>;
  sendAccionOperador: (accion: string) => Promise<void>;
  startNewClaim: () => void;
  confirmarNuevoReclamoLinea: () => Promise<void>;
  selectTicket: (id: string) => Promise<void>;
  updateTicket: (body: Record<string, string>) => Promise<void>;
  loadStats: (desde?: string, hasta?: string) => Promise<void>;
  simulateFailure: (elemento: string) => Promise<void>;
  createKbArticle: (titulo: string, categoria: string, contenido: string) => Promise<void>;
  appendTrace: (lines: string[]) => void;
  clearTraces: () => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<MeResponse | null>(null);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [tenantSlug, setTenantSlugState] = useState("");
  const [tenantContext, setTenantContext] = useState<TenantContext | null>(null);
  const [historial, setHistorial] = useState<ChatMessage[]>([]);
  const [traces, setTraces] = useState<string[]>([]);
  const [sessionId, setSessionIdState] = useState("");
  const [estadoConversacion, setEstadoConversacion] = useState<string | null>(null);
  const [fichaJsc, setFichaJsc] = useState<FichaJsc | null>(null);
  const [lineaDetectada, setLineaDetectada] = useState("");
  const [ticketFormacion, setTicketFormacion] = useState<Ticket | null>(null);
  const [ticketTimeline, setTicketTimeline] = useState<TicketEvent[]>([]);
  const [notifications, setNotifications] = useState<TicketNotification[]>([]);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [telemetry, setTelemetry] = useState<TelemetryElement[]>([]);
  const [kb, setKb] = useState<KBArticle[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [sending, setSending] = useState(false);
  const [networkAlert, setNetworkAlert] = useState<string | null>(null);
  const [alertasRed, setAlertasRed] = useState<AlertaRed[]>([]);
  const [casoActivo, setCasoActivo] = useState<CasoConversacion | null>(null);
  const [lineaCambiada, setLineaCambiada] = useState<LineaCambiada | null>(null);
  const [ticketsSimilares, setTicketsSimilares] = useState<TicketSimilar[]>([]);
  const [ticketExistente, setTicketExistente] = useState<TicketSimilar | null>(null);
  const [intencionPendiente, setIntencionPendiente] = useState<string | null>(null);
  const [flujoOperativo, setFlujoOperativo] = useState<FlujoOperativo | null>(null);

  const isAdmin = user?.rol === "admin";

  const aplicarAlertasRed = useCallback((alertas: AlertaRed[]) => {
    setAlertasRed(alertas);
    if (!alertas.length) return;
    const correlacionadas = alertas.filter((a) => a.correlacionada);
    const fuente = correlacionadas.length ? correlacionadas : alertas;
    const msg = fuente
      .map(
        (a) =>
          `${a.elemento_red} (${a.estado_actual})${a.correlacionada ? " — posible impacto en este caso" : " — incidencia general"}`,
      )
      .join(" · ");
    setNetworkAlert(msg);
  }, []);

  const appendTrace = useCallback((lines: string[]) => {
    setTraces((prev) => [...prev, ...lines].slice(-150));
  }, []);

  const clearTraces = useCallback(() => setTraces([]), []);

  const logout = useCallback(() => {
    clearToken();
    clearTenantSlug();
    clearSessionId();
    setUser(null);
    setTenantContext(null);
    setHistorial([]);
    setTraces([]);
    setSessionIdState("");
    setEstadoConversacion(null);
    setFichaJsc(null);
    setLineaDetectada("");
    setTicketFormacion(null);
    setTicketTimeline([]);
    setNetworkAlert(null);
    setAlertasRed([]);
    setCasoActivo(null);
    setLineaCambiada(null);
    setTicketsSimilares([]);
    setTicketExistente(null);
    setIntencionPendiente(null);
    router.replace("/login");
  }, [router]);

  useEffect(() => {
    setUnauthorizedHandler(() => logout());
  }, [logout]);

  const refreshData = useCallback(async () => {
    const slug = isAdmin ? tenantSlug || getTenantSlug() : undefined;
    const ctx = await api.sessionContext(slug);
    setTenantContext(ctx);

    const loads = [
      api.tickets(slug).then((d) => setTickets(d.tickets || [])),
      api.notifications(slug).then((d) => setNotifications(d.notificaciones || [])),
      api.telemetry(slug).then((d) => {
        const elementos = d.elementos || [];
        setTelemetry(elementos);
        const anomalias: AlertaRed[] = elementos
          .filter((e) => e.estado_actual !== "Normal")
          .map((e) => ({
            elemento_red: e.elemento_red,
            metrica: e.metrica,
            valor_actual: e.valor_actual,
            estado_actual: e.estado_actual,
            correlacionada: false,
          }));
        if (anomalias.length) aplicarAlertasRed(anomalias);
      }).catch(() => {}),
    ];

    if (isAdmin) {
      loads.push(
        api.kb(slug).then((d) => setKb(d.articulos || [])),
        api.stats(undefined, slug).then(setStats).catch(() => setStats(null)),
      );
    }

    const results = await Promise.allSettled(loads);
    const failed = results
      .filter((r) => r.status === "rejected")
      .map((r) => (r as PromiseRejectedResult).reason?.message || "módulo no disponible");
    if (failed.length) appendTrace(failed.map((m) => `⚠️ Carga parcial: ${m}`));
  }, [tenantSlug, isAdmin, appendTrace, aplicarAlertasRed]);

  const boot = useCallback(
    async (loginData?: LoginResponse) => {
      const me = loginData
        ? {
            usuario: loginData.usuario,
            rol: loginData.rol,
            cooperativa: loginData.cooperativa,
            nombre: loginData.nombre,
            org_slug: loginData.org_slug,
          }
        : await api.me();

      setUser(me);
      const { organizaciones } = await api.tenants();
      setOrgs(organizaciones);

      if (me.rol === "admin") {
        const defaultSlug = getTenantSlug() || "imowi";
        setTenantSlugState(defaultSlug);
        setTenantSlug(defaultSlug);
      } else {
        clearTenantSlug();
        setTenantSlugState(me.org_slug || "coop-batan");
      }

      const sid = getSessionId() || newSessionId();
      if (!getSessionId()) setSessionIdState(sid);
      else setSessionIdState(getSessionId());
      setHistorial(loadHistorial(getSessionId()));

      await refreshData();
      setReady(true);
    },
    [refreshData],
  );

  // Bootstrap de sesión al recargar — patrón client-only intencional
  useEffect(() => {
    const token = getToken();
    if (!token) {
      const id = requestAnimationFrame(() => setReady(true));
      return () => cancelAnimationFrame(id);
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- restore session
    void boot().catch(() => logout());
  }, [boot, logout]);

  const login = useCallback(
    async (usuario: string, password: string) => {
      const data = await api.login(usuario, password);
      setToken(data.token);
      newSessionId();
      setSessionIdState(getSessionId());
      await boot(data);
      router.replace("/soporte");
    },
    [boot, router],
  );

  const setTenant = useCallback(
    async (slug: string) => {
      setTenantSlug(slug);
      setTenantSlugState(slug);
      setHistorial([]);
      setTraces([]);
      setTicketFormacion(null);
      setTicketTimeline([]);
      setEstadoConversacion(null);
      setFichaJsc(null);
      setLineaDetectada("");
      setNetworkAlert(null);
      await refreshData();
      appendTrace([`🔀 Vista NOC → ${slug}`]);
    },
    [refreshData, appendTrace],
  );

  const startNewClaim = useCallback(() => {
    const oldId = sessionId || getSessionId();
    if (oldId) clearHistorial(oldId);
    const newId = newSessionId();
    setSessionIdState(newId);
    setHistorial([]);
    setTraces([]);
    setEstadoConversacion(null);
    setCasoActivo(null);
    setLineaCambiada(null);
    setIntencionPendiente(null);
    setFlujoOperativo(null);
    setTicketsSimilares([]);
    setTicketExistente(null);
    setFichaJsc(null);
    setLineaDetectada("");
    setTicketFormacion(null);
    setTicketTimeline([]);
    appendTrace(["🆕 Nuevo reclamo iniciado — sesión limpia"]);
  }, [appendTrace, sessionId]);

  const selectTicket = useCallback(
    async (id: string) => {
      const hdr = isAdmin ? tenantSlug : undefined;
      const detail = await api.ticketDetail(id, hdr);
      setTicketFormacion(detail.ticket);
      setTicketTimeline(detail.timeline || []);
    },
    [tenantSlug, isAdmin],
  );

  const procesarRespuestaChat = useCallback(
    async (res: Awaited<ReturnType<typeof api.chat>>) => {
      setEstadoConversacion(res.estado_conversacion);
      setCasoActivo(res.caso_conversacion);
      setLineaCambiada(res.linea_cambiada || null);
      setTicketsSimilares(res.tickets_similares || []);
      setTicketExistente(res.ticket_existente || null);
      setIntencionPendiente(
        res.intencion_pendiente || res.caso_conversacion?.intencion_pendiente || null,
      );
      setFlujoOperativo(res.flujo_operativo || null);

      const linea =
        res.caso_conversacion?.linea_msisdn ||
        String(res.datos_triaje?.linea || "");
      if (linea) setLineaDetectada(linea);

      if (res.alertas_red?.length) aplicarAlertasRed(res.alertas_red);
      else if (res.informe_tecnico?.anomalia_red_correlacionada) {
        setNetworkAlert(
          `Anomalía correlacionada en ${String(res.informe_tecnico.elemento_afectado || "red")}.`,
        );
      }

      if (res.ficha_jsc) setFichaJsc(res.ficha_jsc);

      const ticketId =
        res.ticket?.id ||
        res.caso_conversacion?.ticket_id ||
        res.ticket_existente?.id ||
        null;

      if (res.ticket_timeline?.length && ticketId) {
        setTicketTimeline(res.ticket_timeline);
        if (!res.ticket && ticketId) {
          const hdr = isAdmin ? tenantSlug : undefined;
          const detail = await api.ticketDetail(ticketId, hdr);
          setTicketFormacion(detail.ticket);
        }
      }

      if (res.ticket) {
        setTicketFormacion(res.ticket);
        const hdr = isAdmin ? tenantSlug : undefined;
        const detail = await api.ticketDetail(res.ticket.id, hdr);
        setTicketTimeline(detail.timeline || []);
        const tix = await api.tickets(hdr);
        setTickets(tix.tickets || []);
        const notif = await api.notifications(hdr);
        setNotifications(notif.notificaciones || []);
        if (isAdmin) api.stats(undefined, hdr).then(setStats).catch(() => {});
      } else if (res.ticket_existente) {
        await selectTicket(res.ticket_existente.id);
      }
    },
    [aplicarAlertasRed, isAdmin, tenantSlug, selectTicket],
  );

  const sendMessage = useCallback(
    async (
      text: string,
      forzar = false,
      accionOperador?: string,
      historialBase?: ChatMessage[],
    ) => {
      if (sending) return;
      const trimmed = text.trim();
      if (!trimmed && !forzar && !accionOperador) return;
      if (lineaCambiada && !accionOperador && trimmed) return;

      setSending(true);
      const prevHist = historialBase ? [...historialBase] : [...historial];
      if (trimmed) {
        setHistorial((h) => [...h, { rol: "usuario", contenido: trimmed }]);
      }

      try {
        const sid = sessionId || getSessionId() || newSessionId();
        const res = await api.chat({
          historial: prevHist,
          mensaje: trimmed,
          forzar_escalamiento: forzar,
          session_id: sid,
          accion_operador: accionOperador,
        }, isAdmin ? tenantSlug : undefined);

        const nuevoHist: ChatMessage[] = [
          ...prevHist,
          ...(trimmed ? [{ rol: "usuario" as const, contenido: trimmed }] : []),
          { rol: "asistente", contenido: res.respuesta },
        ];
        setHistorial(nuevoHist);
        saveHistorial(sid, nuevoHist);
        appendTrace(res.agent_traces || []);
        if (res.usar_ia === false) appendTrace(["💬 Motor: respuesta sin IA"]);
        try {
          await procesarRespuestaChat(res);
        } catch (e) {
          appendTrace([
            `⚠️ Respuesta recibida, pero falló actualizar paneles: ${
              e instanceof Error ? e.message : "Error"
            }`,
          ]);
        }
      } catch (e) {
        appendTrace([`❌ ${e instanceof Error ? e.message : "Error"}`]);
      } finally {
        setSending(false);
      }
    },
    [
      sending,
      historial,
      sessionId,
      appendTrace,
      lineaCambiada,
      tenantSlug,
      isAdmin,
      procesarRespuestaChat,
    ],
  );

  const sendAccionOperador = useCallback(
    (accion: string) => sendMessage("", false, accion),
    [sendMessage],
  );

  const confirmarNuevoReclamoLinea = useCallback(async () => {
    startNewClaim();
    await sendMessage("", false, "nuevo_reclamo");
  }, [startNewClaim, sendMessage]);

  const updateTicket = useCallback(
    async (body: Record<string, string>) => {
      if (!ticketFormacion || !isAdmin) return;
      const res = await api.updateTicket(ticketFormacion.id, body, tenantSlug);
      setTicketFormacion(res.ticket);
      await selectTicket(ticketFormacion.id);
      const tix = await api.tickets(tenantSlug);
      setTickets(tix.tickets || []);
      const notif = await api.notifications(tenantSlug);
      setNotifications(notif.notificaciones || []);
      if (isAdmin) api.stats(undefined, tenantSlug).then(setStats).catch(() => {});
      appendTrace([`📬 Seguimiento actualizado para ${ticketFormacion.id}`]);
    },
    [ticketFormacion, isAdmin, tenantSlug, selectTicket, appendTrace],
  );

  const loadStats = useCallback(
    async (desde?: string, hasta?: string) => {
      const data = await api.stats({ desde, hasta }, tenantSlug);
      setStats(data);
    },
    [tenantSlug],
  );

  const simulateFailure = useCallback(
    async (elemento: string) => {
      appendTrace([`⚡ Simulando falla en ${elemento}…`]);
      const res = await api.simulateTelemetry(elemento, tenantSlug);
      const auto = res.reaccion_autonoma;
      appendTrace(auto?.agent_traces || []);
      if (auto?.ficha_jsc) setFichaJsc(auto.ficha_jsc);
      if (auto?.ticket) {
        setTicketFormacion(auto.ticket);
        await selectTicket(auto.ticket.id);
      }
      if (auto?.respuesta) {
        setHistorial((h) => [
          ...h,
          { rol: "asistente", contenido: `[Proactivo] ${auto.respuesta}` },
        ]);
      }
      await refreshData();
      router.push("/soporte");
    },
    [tenantSlug, appendTrace, selectTicket, refreshData, router],
  );

  const createKbArticle = useCallback(
    async (titulo: string, categoria: string, contenido: string) => {
      await api.createKb({ titulo, categoria, contenido }, tenantSlug);
      const data = await api.kb(tenantSlug);
      setKb(data.articulos || []);
      appendTrace([`📚 Artículo publicado: ${titulo}`]);
    },
    [tenantSlug, appendTrace],
  );

  const value = useMemo<AppContextValue>(
    () => ({
      ready,
      user,
      isAdmin,
      orgs,
      tenantSlug,
      tenantContext,
      historial,
      traces,
      sessionId,
      estadoConversacion,
      fichaJsc,
      lineaDetectada,
      ticketFormacion,
      ticketTimeline,
      notifications,
      tickets,
      telemetry,
      kb,
      stats,
      sending,
      networkAlert,
      alertasRed,
      casoActivo,
      lineaCambiada,
      ticketsSimilares,
      ticketExistente,
      intencionPendiente,
      flujoOperativo,
      login,
      logout,
      setTenant,
      refreshData,
      sendMessage,
      sendAccionOperador,
      startNewClaim,
      confirmarNuevoReclamoLinea,
      selectTicket,
      updateTicket,
      loadStats,
      simulateFailure,
      createKbArticle,
      appendTrace,
      clearTraces,
    }),
    [
      ready,
      user,
      isAdmin,
      orgs,
      tenantSlug,
      tenantContext,
      historial,
      traces,
      sessionId,
      estadoConversacion,
      fichaJsc,
      lineaDetectada,
      ticketFormacion,
      ticketTimeline,
      notifications,
      tickets,
      telemetry,
      kb,
      stats,
      sending,
      networkAlert,
      alertasRed,
      casoActivo,
      lineaCambiada,
      ticketsSimilares,
      ticketExistente,
      intencionPendiente,
      flujoOperativo,
      login,
      logout,
      setTenant,
      refreshData,
      sendMessage,
      sendAccionOperador,
      startNewClaim,
      confirmarNuevoReclamoLinea,
      selectTicket,
      updateTicket,
      loadStats,
      simulateFailure,
      createKbArticle,
      appendTrace,
      clearTraces,
    ],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp debe usarse dentro de AppProvider");
  return ctx;
}
