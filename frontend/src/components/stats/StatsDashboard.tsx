"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useApp } from "@/contexts/AppContext";
import { KpiCard } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";

function ColumnChart({
  data,
  compactLabels,
}: {
  data: { label: string; count: number }[];
  compactLabels?: boolean;
}) {
  if (!data.length) return <p className="text-slate-500 text-sm">Sin datos.</p>;
  const max = Math.max(...data.map((x) => x.count), 1);
  return (
    <div className="h-48 flex items-end gap-1 border-b border-slate-800 pb-6">
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
              className="w-full rounded-t bg-cyan-400/70 border border-cyan-300/20"
              style={{ height: `${h}%` }}
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
}: {
  data: { label: string; count: number }[];
  unit: string;
}) {
  if (!data.length) return <p className="text-slate-500 text-sm">Sin datos.</p>;
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
                className="h-full rounded bg-violet-400/70"
                style={{ width: `${w}%` }}
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
  if (!data.length) return <p className="text-slate-500 text-sm">Sin datos.</p>;
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
  if (!data.length) return <p className="text-slate-500 text-sm">Sin datos.</p>;
  return (
    <div className="space-y-3">
      {data.map((x) => (
        <div key={x.label} className="p-2 rounded-lg border border-slate-800 bg-slate-950/40">
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

export function StatsDashboard() {
  const { stats, loadStats, selectTicket } = useApp();
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");

  const onFilter = (e: FormEvent) => {
    e.preventDefault();
    loadStats(desde || undefined, hasta || undefined);
  };

  const r = stats?.resumen;

  return (
    <div className="p-4 space-y-4 overflow-y-auto">
      <div className="flex flex-wrap justify-between gap-3 items-end">
        <div>
          <h2 className="font-semibold text-slate-100">Estadísticas</h2>
          <p className="text-[10px] font-mono text-slate-500">
            Reclamos · niveles · tiempos · backlog inteligente
          </p>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          <form onSubmit={onFilter} className="flex gap-2 items-center flex-wrap">
          <input
            type="date"
            value={desde}
            onChange={(e) => setDesde(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono"
          />
          <input
            type="date"
            value={hasta}
            onChange={(e) => setHasta(e.target.value)}
            className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs font-mono"
          />
          <button
            type="submit"
            className="text-xs px-3 py-1.5 rounded border border-cyan-500/30 text-cyan-300"
          >
            Filtrar
          </button>
          </form>
        </div>
      </div>

      {!stats ? (
        <p className="text-slate-500">Cargando estadísticas…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
            <KpiCard label="Reclamos" value={r?.total || 0} />
            <KpiCard label="Abiertos" value={r?.abiertos || 0} />
            <KpiCard label="Cerrados" value={r?.cerrados || 0} />
            <KpiCard label="N1" value={r?.n1 || 0} />
            <KpiCard label="N2" value={r?.n2 || 0} />
            <KpiCard label="Prom. hs" value={r?.promedio_horas || 0} />
            {typeof r?.tasa_cierre === "number" && (
              <KpiCard label="% cierre" value={r.tasa_cierre} />
            )}
            {typeof r?.porcentaje_n2 === "number" && (
              <KpiCard label="% N2" value={r.porcentaje_n2} />
            )}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Reclamos diarios
              </h3>
              <ColumnChart data={(stats.series?.diaria || []).slice(-30)} compactLabels />
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Reclamos mensuales
              </h3>
              <ColumnChart data={stats.series?.mensual || []} />
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Por categoría
              </h3>
              <BarList data={stats.distribuciones?.categoria || []} unit="reclamos" />
            </div>
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Por nivel
              </h3>
              <BarList data={stats.distribuciones?.nivel || []} unit="tickets" />
            </div>
            {(stats.distribuciones?.cooperativa?.length ?? 0) > 0 && (
              <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
                <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                  Por cooperativa
                </h3>
                <BarList data={stats.distribuciones?.cooperativa || []} unit="tickets" />
              </div>
            )}
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
              <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
                Por estado
              </h3>
              <BarList data={stats.distribuciones?.estado || []} unit="tickets" />
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

          <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4">
            <h3 className="text-xs font-mono uppercase text-slate-500 mb-3">
              Backlog crítico
            </h3>
            {!stats.backlog?.length ? (
              <p className="text-slate-500 text-sm">Sin backlog abierto.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {stats.backlog.map((t) => (
                  <Link
                    key={t.id}
                    href="/soporte"
                    onClick={() => selectTicket(t.id)}
                    className="block p-2 rounded-lg border border-slate-800 bg-slate-950/50 hover:border-cyan-500/40"
                  >
                    <div className="flex justify-between items-center gap-2">
                      <span className="font-mono text-cyan-300 text-[11px]">
                        {t.id}
                      </span>
                      <span className="text-[10px] text-slate-500">
                        {t.priority_score != null ? `${t.priority_score} pts` : `${t.horas_abierto} hs`}
                      </span>
                    </div>
                    <div className="flex gap-1 mt-1">
                      <StatusBadge value={t.nivel} />
                      <StatusBadge value={t.estado} />
                      {t.risk_level && t.risk_level !== "bajo" && (
                        <span className="text-[9px] font-mono text-amber-400">{t.risk_level}</span>
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
