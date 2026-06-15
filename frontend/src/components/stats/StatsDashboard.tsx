"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useApp } from "@/contexts/AppContext";
import { KpiCard, SlaBadge } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api } from "@/lib/api-client";
import type { ExecutiveAnalytics } from "@/lib/types";

const PALETTE = ["#22d3ee", "#8b5cf6", "#34d399", "#f59e0b", "#f43f5e", "#60a5fa"];

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
  color = "#22d3ee",
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
        const showLabel =
          !compactLabels || i % 5 === 0 || i === data.length - 1;
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
  color = "#8b5cf6",
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

function AvgList({
  data,
}: {
  data: { label: string; count: number; avg_hours: number }[];
}) {
  if (!data.length) return <EmptyState label="Sin datos." />;
  const max = Math.max(...data.map((x) => x.avg_hours), 1);
  return (
    <div className="space-y-3">
      {data.slice(0, 8).map((x) => {
        const w = Math.max((x.avg_hours / max) * 100, 4);
        return (
          <div key={x.label}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-slate-300 truncate">{x.label}</span>
              <span className="font-mono text-slate-500">
                {x.avg_hours} hs · {x.count} casos
              </span>
            </div>
            <div className="h-2 rounded bg-slate-800 overflow-hidden">
              <div
                className="h-full rounded bg-amber-400/70"
                style={{ width: `${w}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function CoopKpiList({
  data,
}: {
  data: {
    label: string;
    count: number;
    abiertos: number;
    n2: number;
    tasa_cierre: number;
    promedio_horas: number;
  }[];
}) {
  if (!data.length) return <EmptyState label="Sin cooperativas para comparar." />;
  return (
    <div className="space-y-3">
      {data.map((x) => (
        <div key={x.label} className="p-3 rounded-xl border border-slate-800 bg-slate-950/50 hover:border-cyan-500/25 transition-colors">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-slate-300 truncate">{x.label}</span>
            <span className="font-mono text-slate-500">{x.count} tickets</span>
          </div>
          <div className="flex flex-wrap gap-2 text-[10px] font-mono text-slate-500">
            <span>{x.abiertos} abiertos</span>
            <span>{x.n2} N2</span>
            <span>{x.tasa_cierre}% cierre</span>
            <span>{x.promedio_horas} hs prom.</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function DonutChart({
  data,
  centerLabel,
}: {
  data: { label: string; count: number }[];
  centerLabel: string;
}) {
  const total = data.reduce((acc, x) => acc + x.count, 0);
  if (!total) return <EmptyState label="Sin distribución disponible." />;

  const gradient = data
    .slice(0, 6)
    .reduce(
      (acc, x, idx) => {
        const start = acc.cursor;
        const end = start + (x.count / total) * 100;
        return {
          cursor: end,
          stops: [
            ...acc.stops,
            `${PALETTE[idx % PALETTE.length]} ${start}% ${end}%`,
          ],
        };
      },
      { cursor: 0, stops: [] as string[] },
    )
    .stops.join(", ");

  return (
    <div className="flex flex-col sm:flex-row items-center gap-5">
      <div
        className="relative h-40 w-40 shrink-0 rounded-full border border-slate-800 shadow-2xl"
        style={{ background: `conic-gradient(${gradient})` }}
      >
        <div className="absolute inset-5 rounded-full bg-slate-950 border border-slate-800 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold text-slate-100 tabular-nums">{total}</span>
          <span className="text-[10px] font-mono text-slate-500 uppercase">{centerLabel}</span>
        </div>
      </div>
      <div className="space-y-2 w-full">
        {data.slice(0, 6).map((x, idx) => (
          <div key={x.label} className="flex items-center justify-between gap-3 text-xs">
            <span className="flex items-center gap-2 min-w-0 text-slate-300">
              <span
                className="h-2.5 w-2.5 rounded-full shrink-0"
                style={{ background: PALETTE[idx % PALETTE.length] }}
              />
              <span className="truncate">{x.label}</span>
            </span>
            <span className="font-mono text-slate-500">
              {x.count} · {Math.round((x.count / total) * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ExecutivePanel({ data }: { data: ExecutiveAnalytics | null }) {
  if (!data) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
        <h3 className="text-xs font-mono uppercase text-slate-500 mb-2">
          Resumen ejecutivo
        </h3>
        <p className="text-sm text-slate-500">Cargando lectura ejecutiva...</p>
      </div>
    );
  }

  const topRisk = data.ranking_riesgo?.[0];
  const criticalAlerts = data.alertas.filter((a) => a.severidad !== "info").slice(0, 3);

  return (
    <div className="rounded-2xl border border-cyan-500/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.16),rgba(15,23,42,0.55)_45%,rgba(2,6,23,0.45))] p-5 shadow-2xl shadow-cyan-950/20">
      <div className="flex flex-wrap justify-between gap-4">
        <div className="max-w-3xl">
          <p className="text-[10px] font-mono uppercase tracking-widest text-cyan-300/80">
            Resumen ejecutivo
          </p>
          <h3 className="mt-2 text-xl font-semibold text-slate-50 leading-snug">
            {data.resumen_ejecutivo}
          </h3>
          <div className="mt-4 flex flex-wrap gap-2">
            <span className="chip border-cyan-500/30 bg-cyan-500/10 text-cyan-200">
              {data.ahorro_operativo.horas_ahorradas_estimadas} hs ahorradas estimadas
            </span>
            <span className="chip border-emerald-500/30 bg-emerald-500/10 text-emerald-200">
              {data.ahorro_operativo.escalaciones_evitadas_estimadas} escalaciones evitadas
            </span>
            {topRisk && (
              <span className="chip border-amber-500/30 bg-amber-500/10 text-amber-200">
                Mayor riesgo: {topRisk.label}
              </span>
            )}
          </div>
        </div>
        <div className="min-w-56 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <p className="text-[10px] font-mono uppercase text-slate-500 mb-2">Alertas</p>
          {criticalAlerts.length ? (
            <div className="space-y-2">
              {criticalAlerts.map((a) => (
                <p key={a.mensaje} className="text-xs text-amber-200">
                  {a.mensaje}
                </p>
              ))}
            </div>
          ) : (
            <p className="text-xs text-emerald-300">Sin alertas críticas.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function RiskRanking({ data }: { data: ExecutiveAnalytics["ranking_riesgo"] }) {
  if (!data.length) return <EmptyState label="Sin ranking de riesgo." />;
  const max = Math.max(...data.map((x) => x.score_riesgo), 1);
  return (
    <div className="space-y-3">
      {data.slice(0, 6).map((x, idx) => {
        const width = Math.max((x.score_riesgo / max) * 100, 6);
        return (
          <div key={x.org_id} className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
            <div className="flex items-center justify-between gap-3 text-xs mb-2">
              <span className="text-slate-200 truncate">
                {idx + 1}. {x.label}
              </span>
              <span className="font-mono text-slate-500">
                {x.score_riesgo}/{x.score_max}
              </span>
            </div>
            <div className="h-2 rounded bg-slate-800 overflow-hidden">
              <div
                className="h-full rounded"
                style={{
                  width: `${width}%`,
                  background: `linear-gradient(90deg, ${PALETTE[idx % PALETTE.length]}, #f59e0b)`,
                }}
              />
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-mono text-slate-500">
              <span>{x.backlog} backlog</span>
              <span>{x.n2} N2</span>
              <span>{x.tickets_criticos} críticos</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function StatsDashboard() {
  const { stats, loadStats, selectTicket, tenantSlug } = useApp();
  const [executive, setExecutive] = useState<ExecutiveAnalytics | null>(null);
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");

  const onFilter = (e: FormEvent) => {
    e.preventDefault();
    loadStats(desde || undefined, hasta || undefined);
  };

  const r = stats?.resumen;
  const slaVencidos = useMemo(
    () => stats?.backlog?.filter((t) => t.estado_sla === "Vencido").length ?? 0,
    [stats?.backlog],
  );

  useEffect(() => {
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
  }, [tenantSlug, stats]);

  return (
    <div className="p-4 space-y-5 overflow-y-auto">
      <div className="rounded-2xl border border-slate-800 bg-[linear-gradient(135deg,rgba(15,23,42,0.9),rgba(8,47,73,0.32))] p-5">
        <div className="flex flex-wrap justify-between gap-3 items-end">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-widest text-cyan-400/80">
            Tablero de gestión
          </p>
          <h2 className="mt-1 text-2xl font-semibold text-slate-50">Estadísticas operativas</h2>
          <p className="mt-1 text-sm text-slate-400">
            SLA, backlog, riesgo por cooperativa y evolución de reclamos.
          </p>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <form onSubmit={onFilter} className="flex gap-2 items-center flex-wrap">
          <input
            type="date"
            value={desde}
            onChange={(e) => setDesde(e.target.value)}
            className="bg-slate-950/80 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono focus:border-cyan-500/40 outline-none"
          />
          <input
            type="date"
            value={hasta}
            onChange={(e) => setHasta(e.target.value)}
            className="bg-slate-950/80 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono focus:border-cyan-500/40 outline-none"
          />
          <button
            type="submit"
            className="text-xs px-3 py-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/10 text-cyan-200 hover:bg-cyan-500/15"
          >
            Filtrar
          </button>
          </form>
        </div>
      </div>
      </div>

      {!stats ? (
        <EmptyState label="Cargando tablero operativo..." />
      ) : (
        <>
          <ExecutivePanel data={executive} />

          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
            <KpiCard label="Reclamos" value={r?.total || 0} tone="cyan" helper="volumen total" />
            <KpiCard label="Abiertos" value={r?.abiertos || 0} tone="amber" helper="requieren gestión" />
            <KpiCard label="SLA vencido" value={slaVencidos} tone={slaVencidos ? "red" : "emerald"} helper="backlog actual" />
            <KpiCard label="N2" value={r?.n2 || 0} tone="violet" helper="escalados" />
            <KpiCard label="Cerrados" value={r?.cerrados || 0} tone="emerald" helper="resueltos" />
            <KpiCard label="Prom. hs" value={r?.promedio_horas || 0} tone="default" helper="tiempo abierto" />
            {typeof r?.tasa_cierre === "number" && (
              <KpiCard label="% cierre" value={r.tasa_cierre} tone="emerald" />
            )}
            {typeof r?.porcentaje_n2 === "number" && (
              <KpiCard label="% N2" value={r.porcentaje_n2} tone="violet" />
            )}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-[1.4fr_0.9fr] gap-4">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 shadow-xl shadow-slate-950/20">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Evolución diaria
              </h3>
              <ColumnChart data={(stats.series?.diaria || []).slice(-30)} compactLabels color="#22d3ee" />
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 shadow-xl shadow-slate-950/20">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Distribución por estado
              </h3>
              <DonutChart data={stats.distribuciones?.estado || []} centerLabel="tickets" />
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-[1fr_1fr_0.9fr] gap-4">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Por categoría
              </h3>
              <BarList data={stats.distribuciones?.categoria || []} unit="reclamos" color="#8b5cf6" />
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Por nivel
              </h3>
              <BarList data={stats.distribuciones?.nivel || []} unit="tickets" color="#34d399" />
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Riesgo por cooperativa
              </h3>
              <RiskRanking data={executive?.ranking_riesgo || []} />
            </div>
            {(stats.distribuciones?.cooperativa?.length ?? 0) > 0 && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
                <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                  Por cooperativa
                </h3>
                <BarList data={stats.distribuciones?.cooperativa || []} unit="tickets" color="#f59e0b" />
              </div>
            )}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Reclamos mensuales
              </h3>
              <ColumnChart data={stats.series?.mensual || []} color="#60a5fa" />
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Promedio por categoría
              </h3>
              <AvgList data={stats.promedios?.por_categoria || []} />
            </div>
            {(stats.promedios?.por_cooperativa?.length ?? 0) > 0 && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
                <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                  KPI por cooperativa
                </h3>
                <CoopKpiList data={stats.promedios?.por_cooperativa || []} />
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-amber-500/20 bg-[linear-gradient(135deg,rgba(15,23,42,0.92),rgba(69,26,3,0.18))] p-4">
            <div className="flex items-center justify-between gap-3 mb-3">
              <div>
                <h3 className="text-xs font-mono uppercase text-amber-300/80">
                  Backlog crítico
                </h3>
                <p className="text-[11px] text-slate-500 mt-1">
                  Tickets abiertos ordenados por riesgo, SLA y próxima acción.
                </p>
              </div>
              <span className="chip border-amber-500/30 bg-amber-500/10 text-amber-200">
                {stats.backlog?.length || 0} activos
              </span>
            </div>
            {!stats.backlog?.length ? (
              <EmptyState label="Sin backlog abierto." />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {stats.backlog.map((t) => (
                  <Link
                    key={t.id}
                    href="/soporte"
                    onClick={() => selectTicket(t.id)}
                    className="block p-3 rounded-xl border border-slate-800 bg-slate-950/55 hover:border-cyan-500/40 hover:bg-slate-950/80 transition-colors"
                  >
                    <div className="flex justify-between items-center gap-2">
                      <span className="font-mono text-cyan-300 text-[11px]">
                        {t.id}
                      </span>
                      <span className="text-[10px] font-mono text-slate-400">
                        {t.priority_score != null ? `${t.priority_score} pts` : `${t.horas_abierto} hs`}
                      </span>
                    </div>
                    <div className="flex gap-1 mt-2 flex-wrap">
                      <StatusBadge value={t.nivel} />
                      <StatusBadge value={t.estado} />
                      {t.risk_level && t.risk_level !== "bajo" && (
                        <span className="chip border-amber-500/30 bg-amber-500/10 text-amber-300">{t.risk_level}</span>
                      )}
                      {t.estado_sla && (
                        <SlaBadge label={t.estado_sla} estado={t.estado_sla} />
                      )}
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1 truncate">
                      {t.linea || ""} · {t.categoria || ""}
                    </p>
                    {t.next_best_action && (
                      <p className="text-[9px] text-cyan-500/80 mt-1 line-clamp-1">
                        → {t.next_best_action}
                      </p>
                    )}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
