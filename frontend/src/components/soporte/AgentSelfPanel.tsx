"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { GlassCard, SidebarSection } from "@/components/ui/GlassCard";
import { useApp } from "@/contexts/AppContext";
import { api } from "@/lib/api-client";
import type { CsatBlock, MeAnalytics } from "@/lib/types";

function defaultDesde(): string {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return d.toISOString().slice(0, 10);
}

function defaultHasta(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Performance personal del agente — canal + tickets del período. */
export function AgentSelfPanel() {
  const { can, tenantSlug } = useApp();
  const [desde, setDesde] = useState(defaultDesde);
  const [hasta, setHasta] = useState(defaultHasta);
  const [data, setData] = useState<MeAnalytics | null>(null);
  const [csat, setCsat] = useState<CsatBlock | null>(null);
  const [loading, setLoading] = useState(false);

  const hidden =
    !can("stats.self") ||
    can("stats.agents") ||
    can("stats.global") ||
    can("stats.bot");

  const load = useCallback(async () => {
    if (hidden) return;
    setLoading(true);
    try {
      const [res, csatRes] = await Promise.all([
        api.meAnalytics({ desde, hasta }, tenantSlug),
        api.csatAnalytics({ desde, hasta }, tenantSlug).catch(() => null),
      ]);
      setData(res);
      setCsat(csatRes?.me || csatRes?.resumen || res.csat || null);
    } catch {
      setData(null);
      setCsat(null);
    } finally {
      setLoading(false);
    }
  }, [desde, hasta, tenantSlug, hidden]);

  useEffect(() => {
    void load();
  }, [load]);

  if (hidden) return null;

  const t = data?.tickets;
  const c = data?.canal;

  const onFilter = (e: FormEvent) => {
    e.preventDefault();
    void load();
  };

  return (
    <SidebarSection title="Mi actividad">
      <GlassCard title="Resumen personal" accent="cyan" variant="secondary">
        <form onSubmit={onFilter} className="flex gap-1.5 items-center flex-wrap mb-3">
          <input
            type="date"
            value={desde}
            onChange={(e) => setDesde(e.target.value)}
            className="bg-slate-950/80 border border-slate-700 rounded px-1.5 py-1 text-[10px] font-mono outline-none focus:ring-1 focus:ring-ecolan-brand"
          />
          <input
            type="date"
            value={hasta}
            onChange={(e) => setHasta(e.target.value)}
            className="bg-slate-950/80 border border-slate-700 rounded px-1.5 py-1 text-[10px] font-mono outline-none focus:ring-1 focus:ring-ecolan-brand"
          />
          <button
            type="submit"
            className="text-[10px] px-2 py-1 rounded border border-ecolan-brand/30 text-ecolan-brand hover:bg-ecolan-brand/10"
          >
            Ver
          </button>
        </form>
        {loading && !data ? (
          <p className="text-xs text-slate-500">Cargando...</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            <div>
              <p className="text-[10px] font-mono uppercase text-slate-500">Claims</p>
              <p className="text-lg font-mono text-ecolan-brand mt-0.5">
                {c?.claims_en_rango ?? 0}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase text-slate-500">Cierres</p>
              <p className="text-lg font-mono text-emerald-300 mt-0.5">
                {c?.cierres_en_rango ?? 0}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase text-slate-500">Tk abiertos</p>
              <p className="text-lg font-mono text-amber-300 mt-0.5">{t?.abiertos ?? 0}</p>
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase text-slate-500">CSAT</p>
              <p className="text-lg font-mono text-slate-100 mt-0.5">
                {csat?.promedio != null ? csat.promedio : "—"}
              </p>
              <p className="text-[9px] text-slate-600">{csat?.total ?? 0} votos</p>
            </div>
          </div>
        )}
        <p className="text-[11px] text-slate-500 mt-3">
          Período seleccionado ·{" "}
          <Link href="/estadisticas" className="text-ecolan-brand hover:underline">
            Ver en Estadísticas →
          </Link>
        </p>
      </GlassCard>
    </SidebarSection>
  );
}
