"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useApp } from "@/contexts/AppContext";
import { KpiCard, SlaBadge } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api } from "@/lib/api-client";
import type { CsatAnalytics, CsatBlock, ExecutiveAnalytics, MeAnalytics, OpsAnalytics, StatsResponse } from "@/lib/types";

function defaultDesde(): string {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

function defaultHasta(): string {
  return new Date().toISOString().slice(0, 10);
}

function fmtMin(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (v < 60) return `${Math.round(v)} min`;
  const h = Math.floor(v / 60);
  const m = Math.round(v % 60);
  return `${h}h ${m}m`;
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/40 p-4 text-sm text-slate-500">
      {label}
    </div>
  );
}

function ColumnChart({
  data,
  compactLabels,
  color = "#2298A6",
}: {
  data: { label: string; count: number }[];
  compactLabels?: boolean;
  color?: string;
}) {
  if (!data.length) return <EmptyState label="Sin datos para graficar." />;
  const max = Math.max(...data.map((x) => x.count), 1);
  return (
    <div className="h-56 flex items-end gap-1 border-b border-slate-800/80 pb-7 relative">
      <div className="absolute inset-x-0 top-0 bottom-7 pointer-events-none bg-[linear-gradient(to_bottom,rgba(148,163,184,0.08)_1px,transparent_1px)] bg-[size:100%_25%]" />
      {data.map((x, i) => {
        const h = Math.max((x.count / max) * 100, x.count ? 8 : 2);
        const showLabel = !compactLabels || i % 5 === 0 || i === data.length - 1;
        return (
          <div
            key={`${x.label}-${i}`}
            className="flex-1 h-full flex flex-col justify-end items-center min-w-0"
          >
            <div
              title={`${x.label}: ${x.count}`}
              className="w-full rounded-t-md border transition-all hover:brightness-125"
              style={{
                height: `${h}%`,
                background: `linear-gradient(180deg, ${color}, ${color}55)`,
                borderColor: `${color}55`,
                boxShadow: `0 0 20px ${color}1f`,
              }}
            />
            <span className="mt-1 text-[9px] font-mono text-slate-600 truncate w-full text-center">
              {showLabel ? String(x.label).slice(5) : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function BarList({
  data,
  unit,
  color = "#2298A6",
}: {
  data: { label: string; count: number }[];
  unit: string;
  color?: string;
}) {
  if (!data.length) return <EmptyState label="Sin datos." />;
  const max = Math.max(...data.map((x) => x.count), 1);
  return (
    <div className="space-y-3">
      {data.slice(0, 8).map((x) => {
        const w = Math.max((x.count / max) * 100, 4);
        return (
          <div key={x.label}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-slate-300 truncate">{x.label}</span>
              <span className="font-mono text-slate-500">
                {x.count} {unit}
              </span>
            </div>
            <div className="h-2 rounded bg-slate-800 overflow-hidden">
              <div
                className="h-full rounded"
                style={{
                  width: `${w}%`,
                  background: `linear-gradient(90deg, ${color}, ${color}99)`,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MeActivityBlock({
  data,
  csat,
  loading,
}: {
  data: MeAnalytics | null;
  csat?: CsatBlock | null;
  loading: boolean;
}) {
  if (loading && !data) return <EmptyState label="Cargando mi actividad..." />;
  if (!data) return <EmptyState label="No se pudo cargar tu actividad." />;
  const t = data.tickets;
  const c = data.canal;
  const myCsat = csat || data.csat;
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
        <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">Mi actividad</h3>
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
          <KpiCard label="Claims" value={c.claims_en_rango} tone="cyan" helper="chats tomados" />
          <KpiCard label="Cierres canal" value={c.cierres_en_rango} tone="emerald" helper="en el período" />
          <KpiCard label="Chats activos" value={c.chats_activos} tone="amber" helper="ahora" />
          <KpiCard label="Tickets abiertos" value={t.abiertos} tone="amber" helper="asignados" />
          <KpiCard label="Tickets cerrados" value={t.cerrados} tone="emerald" helper="en el período" />
          <KpiCard
            label="% resolución"
            value={t.pct_resolucion}
            tone={t.pct_resolucion >= 80 ? "emerald" : "amber"}
            helper={`${t.con_resolucion}/${t.cerrados} documentados`}
          />
        </div>
      </div>
      {myCsat && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
          <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
            Mi satisfacción (CSAT)
          </h3>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KpiCard label="Respuestas" value={myCsat.total} tone="cyan" helper="calificaciones" />
            <KpiCard
              label="Promedio"
              value={myCsat.promedio == null ? "—" : myCsat.promedio}
              tone={
                myCsat.promedio == null
                  ? "cyan"
                  : myCsat.promedio >= 4
                    ? "emerald"
                    : myCsat.promedio >= 3
                      ? "amber"
                      : "red"
              }
              helper="sobre 5"
            />
            <KpiCard
              label="Notas bajas"
              value={myCsat.bajas}
              tone={myCsat.bajas ? "red" : "emerald"}
              helper={`${myCsat.pct_bajas}% del total`}
            />
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
              <p className="text-[10px] font-mono uppercase text-slate-500 mb-2">Distribución</p>
              <div className="flex items-end gap-1 h-12">
                {[1, 2, 3, 4, 5].map((n) => {
                  const count = myCsat.distribucion?.[String(n)] || 0;
                  const max = Math.max(
                    ...[1, 2, 3, 4, 5].map((x) => myCsat.distribucion?.[String(x)] || 0),
                    1,
                  );
                  const h = Math.max((count / max) * 100, count ? 12 : 2);
                  return (
                    <div key={n} className="flex-1 flex flex-col justify-end items-center h-full">
                      <div
                        className="w-full rounded-t bg-ecolan-brand/70"
                        style={{ height: `${h}%` }}
                        title={`${n}★: ${count}`}
                      />
                      <span className="text-[9px] font-mono text-slate-600 mt-0.5">{n}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CsatSection({ data }: { data: CsatAnalytics | null }) {
  if (!data) return null;
  const bot = data.bot;
  const tec = data.tecnicos;
  const resumen = data.resumen;
  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-slate-100">Satisfacción (CSAT)</h3>
        <p className="text-[11px] text-slate-500 mt-0.5">
          Calificaciones 1–5 tras cierre — bot N1 y atención humana.
        </p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Total respuestas" value={resumen?.total ?? 0} tone="cyan" helper="en el período" />
        <KpiCard
          label="Promedio general"
          value={resumen?.promedio == null ? "—" : resumen.promedio}
          tone={
            resumen?.promedio == null
              ? "cyan"
              : resumen.promedio >= 4
                ? "emerald"
                : resumen.promedio >= 3
                  ? "amber"
                  : "red"
          }
          helper="sobre 5"
        />
        <KpiCard
          label="Bot N1"
          value={bot?.promedio == null ? "—" : bot.promedio}
          tone="cyan"
          helper={`${bot?.total ?? 0} votos`}
        />
        <KpiCard
          label="Agentes"
          value={tec?.promedio == null ? "—" : tec.promedio}
          tone="emerald"
          helper={`${tec?.total ?? 0} votos · ${resumen?.bajas ?? 0} bajas`}
        />
      </div>

      {(bot || tec) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {bot && (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h4 className="text-xs font-mono uppercase text-slate-500 mb-3">Distribución bot</h4>
              <BarList
                data={[1, 2, 3, 4, 5].map((n) => ({
                  label: `${n} ★`,
                  count: bot.distribucion?.[String(n)] || 0,
                }))}
                unit="votos"
                color="#2298A6"
              />
            </div>
          )}
          {tec && (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h4 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Distribución agentes
              </h4>
              <BarList
                data={[1, 2, 3, 4, 5].map((n) => ({
                  label: `${n} ★`,
                  count: tec.distribucion?.[String(n)] || 0,
                }))}
                unit="votos"
                color="#10b981"
              />
            </div>
          )}
        </div>
      )}

      {!!data.agentes?.length && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-800">
            <h4 className="text-xs font-mono uppercase text-slate-500">CSAT por agente</h4>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] font-mono uppercase text-slate-500 border-b border-slate-800">
                  <th className="text-left px-3 py-2">Agente</th>
                  <th className="text-right px-3 py-2">Votos</th>
                  <th className="text-right px-3 py-2">Promedio</th>
                  <th className="text-right px-3 py-2">Bajas (1–2)</th>
                </tr>
              </thead>
              <tbody>
                {data.agentes.map((a) => (
                  <tr key={a.agente_id} className="border-b border-slate-800/60">
                    <td className="px-3 py-2.5 text-slate-200">{a.nombre || a.agente_id}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-slate-400">{a.total}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-ecolan-brand">
                      {a.promedio ?? "—"}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono text-rose-300/90">
                      {a.bajas}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

function OpsSections({
  ops,
  canTeam,
}: {
  ops: OpsAnalytics;
  canTeam: boolean;
}) {
  const canal = ops.canal;
  const tickets = ops.tickets;
  const estados = canal.abiertas_por_estado;

  return (
    <div className="space-y-5">
      <section className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">Canal en vivo</h3>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Snapshot de bandeja + actividad del rango seleccionado.
          </p>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
          <KpiCard
            label="En espera"
            value={canal.espera_count}
            tone={canal.espera_count ? "amber" : "emerald"}
            helper={`p50 ${fmtMin(canal.espera_minutos_mediana)} · p95 ${fmtMin(canal.espera_minutos_p95)}`}
          />
          <KpiCard label="Con agente" value={estados.con_agente || 0} tone="cyan" helper="abiertas" />
          <KpiCard label="Bot" value={estados.bot || 0} tone="default" helper="abiertas" />
          <KpiCard label="Handoffs" value={canal.claims_en_rango} tone="cyan" helper="tomados en rango" />
          <KpiCard
            label="Cierres c/ nota"
            value={canal.cierres_con_nota}
            tone={canal.pct_cierres_con_nota >= 80 ? "emerald" : "amber"}
            helper={`${canal.pct_cierres_con_nota}% de ${canal.cierres_en_rango}`}
          />
          <KpiCard
            label="1ª respuesta"
            value={canal.first_response_minutos_mediana != null ? Math.round(canal.first_response_minutos_mediana) : "—"}
            tone="default"
            helper="mediana min (aprox.)"
          />
        </div>
        {!!canal.por_canal.length && (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 max-w-xl">
            <h4 className="text-xs font-mono uppercase text-slate-500 mb-3">Mix de canal</h4>
            <BarList data={canal.por_canal} unit="abiertas" color="#2298A6" />
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">Tickets N1 / N2</h3>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Volumen y calidad de cierre documentado en el período.
          </p>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
          <KpiCard label="Creados" value={tickets.creados} tone="cyan" helper="en rango" />
          <KpiCard label="Cerrados" value={tickets.cerrados} tone="emerald" helper="en rango" />
          <KpiCard label="Abiertos" value={tickets.abiertos_ahora} tone="amber" helper="ahora" />
          <KpiCard
            label="% resolución"
            value={tickets.pct_resolucion_documentada}
            tone={tickets.pct_resolucion_documentada >= 80 ? "emerald" : "amber"}
            helper={`${tickets.con_resolucion}/${tickets.cerrados} con nota técnica`}
          />
          <KpiCard
            label="SLA vencido"
            value={tickets.sla_vencidos_abiertos}
            tone={tickets.sla_vencidos_abiertos ? "red" : "emerald"}
            helper="abiertos ahora"
          />
          <KpiCard
            label="Breach al cierre"
            value={tickets.cerrados_con_breach}
            tone={tickets.cerrados_con_breach ? "amber" : "emerald"}
            helper="cerrados en rango"
          />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
            <h4 className="text-xs font-mono uppercase text-slate-500 mb-3">Por nivel (creados)</h4>
            <BarList data={tickets.por_nivel} unit="tickets" color="#1A7985" />
          </div>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
            <h4 className="text-xs font-mono uppercase text-slate-500 mb-3">Top categorías</h4>
            <BarList data={tickets.top_categorias} unit="tickets" color="#f59e0b" />
          </div>
        </div>
      </section>

      {canTeam && (
        <section className="space-y-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-100">Equipo</h3>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Actividad por agente en la ventana de fechas.
            </p>
          </div>
          {!ops.agentes.length ? (
            <EmptyState label="Sin agentes activos en esta organización." />
          ) : (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/70 text-[10px] font-mono uppercase text-slate-500">
                    <tr>
                      <th className="px-3 py-2.5">Agente</th>
                      {ops.alcance === "global" && (
                        <th className="px-3 py-2.5">Org</th>
                      )}
                      <th className="px-3 py-2.5">Disp.</th>
                      <th className="px-3 py-2.5 text-right">Claims</th>
                      <th className="px-3 py-2.5 text-right">Cierres canal</th>
                      <th className="px-3 py-2.5 text-right">Chats</th>
                      <th className="px-3 py-2.5 text-right">Tk abiertos</th>
                      <th className="px-3 py-2.5 text-right">Tk cerrados</th>
                      <th className="px-3 py-2.5 text-right">% resolución</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ops.agentes.map((a) => (
                      <tr
                        key={`${a.email}-${a.organizacion || ""}`}
                        className="border-t border-slate-800/80 hover:bg-slate-950/40"
                      >
                        <td className="px-3 py-2.5">
                          <div className="text-slate-200 truncate max-w-[14rem]">{a.nombre}</div>
                          <div className="font-mono text-[10px] text-slate-500 truncate">
                            {a.email}
                          </div>
                        </td>
                        {ops.alcance === "global" && (
                          <td className="px-3 py-2.5 text-slate-400 truncate max-w-[10rem]">
                            {a.organizacion || "—"}
                          </td>
                        )}
                        <td className="px-3 py-2.5 text-slate-400">{a.disponibilidad || "—"}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-slate-300">{a.claims}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-slate-300">
                          {a.cierres_canal}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono text-slate-300">
                          {a.chats_activos}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono text-amber-200/90">
                          {a.tickets_abiertos}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono text-emerald-300/90">
                          {a.tickets_cerrados}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono text-slate-300">
                          {a.pct_resolucion}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

export function StatsDashboard() {
  const { selectTicket, tenantSlug, can, loadStats, stats } = useApp();
  const canOps = can("stats.global") || can("stats.bot") || can("stats.agents");
  const canTeam = can("stats.agents") || can("stats.global");
  const selfOnly = can("stats.self") && !canOps;

  const [desde, setDesde] = useState(defaultDesde);
  const [hasta, setHasta] = useState(defaultHasta);
  const [ops, setOps] = useState<OpsAnalytics | null>(null);
  const [me, setMe] = useState<MeAnalytics | null>(null);
  const [csat, setCsat] = useState<CsatAnalytics | null>(null);
  const [executive, setExecutive] = useState<ExecutiveAnalytics | null>(null);
  const [ticketStats, setTicketStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (selfOnly) {
        const [data, csatData] = await Promise.all([
          api.meAnalytics({ desde, hasta }, tenantSlug),
          api.csatAnalytics({ desde, hasta }, tenantSlug).catch(() => null),
        ]);
        setMe(data);
        setCsat(csatData);
        setOps(null);
      } else {
        const [opsData, tStats, csatData] = await Promise.all([
          api.opsAnalytics({ desde, hasta }, tenantSlug),
          api.stats({ desde, hasta }, tenantSlug).catch(() => null),
          api.csatAnalytics({ desde, hasta }, tenantSlug).catch(() => null),
        ]);
        setOps(opsData);
        setTicketStats(tStats);
        setCsat(csatData);
        setMe(null);
        void loadStats(desde, hasta);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar estadísticas");
    } finally {
      setLoading(false);
    }
  }, [desde, hasta, tenantSlug, selfOnly, loadStats]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!canOps || !can("stats.bot")) return;
    let mounted = true;
    api
      .executiveAnalytics(tenantSlug)
      .then((data) => {
        if (mounted) setExecutive(data);
      })
      .catch(() => {
        if (mounted) setExecutive(null);
      });
    return () => {
      mounted = false;
    };
  }, [tenantSlug, canOps, can]);

  const onFilter = (e: FormEvent) => {
    e.preventDefault();
    void load();
  };

  const series = ticketStats || stats;

  const slaVencidos = useMemo(
    () => series?.backlog?.filter((t) => t.estado_sla === "Vencido").length ?? 0,
    [series?.backlog],
  );

  return (
    <div className="p-4 space-y-5 overflow-y-auto">
      <div className="rounded-2xl border border-slate-800 bg-[linear-gradient(135deg,rgba(15,23,42,0.9),rgba(8,47,73,0.32))] p-5">
        <div className="flex flex-wrap justify-between gap-3 items-end">
          <div>
            <p className="text-[10px] font-mono uppercase tracking-widest text-ecolan-brand/80">
              {selfOnly ? "Rendimiento personal" : "Operaciones"}
            </p>
            <h2 className="mt-1 text-2xl font-semibold text-slate-50">
              {selfOnly ? "Mi actividad" : "Estadísticas"}
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              {selfOnly
                ? "Tu actividad de canal y tickets en el período."
                : ops?.alcance === "global"
                  ? "Alcance global (todas las cooperativas) — canal, tickets y equipo."
                  : "Canal, tickets y equipo — con ventana de fechas real."}
            </p>
          </div>
          <form onSubmit={onFilter} className="flex gap-2 items-center flex-wrap">
            <input
              type="date"
              value={desde}
              onChange={(e) => setDesde(e.target.value)}
              className="bg-slate-950/80 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono focus:ring-2 focus:ring-ecolan-brand focus:border-transparent outline-none"
            />
            <input
              type="date"
              value={hasta}
              onChange={(e) => setHasta(e.target.value)}
              className="bg-slate-950/80 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono focus:ring-2 focus:ring-ecolan-brand focus:border-transparent outline-none"
            />
            <button
              type="submit"
              className="text-xs px-3 py-1.5 rounded-lg border border-ecolan-brand/30 bg-ecolan-brand/10 text-ecolan-brand hover:bg-ecolan-brand/15"
            >
              Filtrar
            </button>
          </form>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
          {error}
        </div>
      )}

      {selfOnly ? (
        <MeActivityBlock data={me} csat={csat?.me || csat?.resumen} loading={loading} />
      ) : loading && !ops ? (
        <EmptyState label="Cargando tablero operativo..." />
      ) : ops ? (
        <>
          <OpsSections ops={ops} canTeam={canTeam} />
          <CsatSection data={csat} />

          {series && (
            <section className="space-y-3">
              <div>
                <h3 className="text-sm font-semibold text-slate-100">Series de tickets</h3>
                <p className="text-[11px] text-slate-500 mt-0.5">Volumen diario y distribución.</p>
              </div>
              <div className="grid grid-cols-1 xl:grid-cols-[1.4fr_0.9fr] gap-4">
                <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
                  <h4 className="text-xs font-mono uppercase text-slate-500 mb-3">Evolución diaria</h4>
                  <ColumnChart
                    data={(series.series?.diaria || []).slice(-30)}
                    compactLabels
                    color="#2298A6"
                  />
                </div>
                <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
                  <h4 className="text-xs font-mono uppercase text-slate-500 mb-3">Por categoría</h4>
                  <BarList
                    data={series.distribuciones?.categoria || []}
                    unit="reclamos"
                    color="#1A7985"
                  />
                </div>
              </div>

              <div className="rounded-2xl border border-amber-500/20 bg-[linear-gradient(135deg,rgba(15,23,42,0.92),rgba(69,26,3,0.18))] p-4">
                <div className="flex items-center justify-between gap-3 mb-3">
                  <div>
                    <h4 className="text-xs font-mono uppercase text-amber-300/80">Top riesgo</h4>
                    <p className="text-[11px] text-slate-500 mt-1">
                      Los 3 más urgentes. Cola completa en Tickets.
                    </p>
                  </div>
                  <Link
                    href="/tickets"
                    className="text-[11px] font-mono text-ecolan-brand hover:text-ecolan-brand shrink-0"
                  >
                    Ir a cola →
                  </Link>
                </div>
                {!series.backlog?.length ? (
                  <EmptyState label="Sin backlog abierto." />
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                    {series.backlog.slice(0, 3).map((t) => (
                      <Link
                        key={t.id}
                        href={`/soporte?ticket=${encodeURIComponent(t.id)}`}
                        onClick={() => selectTicket(t.id)}
                        className="block p-3 rounded-xl border border-slate-800 bg-slate-950/55 hover:border-ecolan-brand/40 hover:bg-slate-950/80 transition-colors"
                      >
                        <div className="flex justify-between items-center gap-2">
                          <span className="font-mono text-ecolan-brand text-[11px]">{t.id}</span>
                          <span className="text-[10px] font-mono text-slate-400">
                            {t.priority_score != null
                              ? `${t.priority_score} pts`
                              : `${t.horas_abierto} hs`}
                          </span>
                        </div>
                        <div className="flex gap-1 mt-2 flex-wrap">
                          <StatusBadge value={t.nivel} />
                          <StatusBadge value={t.estado} />
                          {t.estado_sla && (
                            <SlaBadge label={t.estado_sla} estado={t.estado_sla} />
                          )}
                        </div>
                        <p className="text-[10px] text-slate-500 mt-1 truncate">
                          {t.linea || ""} · {t.categoria || ""}
                        </p>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}

          {(can("stats.bot") || can("stats.global")) && (
            <details
              className="rounded-2xl border border-slate-800 bg-slate-900/30"
              open={showAdvanced}
              onToggle={(e) => setShowAdvanced((e.target as HTMLDetailsElement).open)}
            >
              <summary className="cursor-pointer px-4 py-3 text-xs font-mono uppercase text-slate-500 select-none">
                Avanzado — lectura ejecutiva (ilustrativo)
              </summary>
              <div className="px-4 pb-4 space-y-3 border-t border-slate-800">
                {executive ? (
                  <>
                    <p className="text-sm text-slate-300 mt-3">{executive.resumen_ejecutivo}</p>
                    <div className="flex flex-wrap gap-2">
                      <span className="chip border-slate-600/40 bg-slate-800/40 text-slate-400">
                        {executive.ahorro_operativo.horas_ahorradas_estimadas} hs ahorradas
                        (estimación)
                      </span>
                      <span className="chip border-slate-600/40 bg-slate-800/40 text-slate-400">
                        {executive.ahorro_operativo.escalaciones_evitadas_estimadas} escalaciones
                        evitadas (estimación)
                      </span>
                      <span className="chip border-amber-500/20 bg-amber-500/5 text-amber-200/80">
                        SLA backlog vencido: {slaVencidos}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-600">
                      Estas métricas de ahorro son ilustrativas / heurísticas; no son KPIs formales
                      de producción.
                    </p>
                  </>
                ) : (
                  <p className="text-sm text-slate-500 mt-3">Sin lectura ejecutiva disponible.</p>
                )}
              </div>
            </details>
          )}
        </>
      ) : (
        <EmptyState label="Sin datos operativos." />
      )}
    </div>
  );
}
