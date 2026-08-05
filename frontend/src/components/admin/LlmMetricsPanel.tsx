"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type LlmMetricsResponse } from "@/lib/api-client";
import { GlassCard, KpiCard } from "@/components/ui/GlassCard";

function fmtTs(ts: number): string {
  if (!ts) return "—";
  try {
    return new Date(ts * 1000).toLocaleString("es-AR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      day: "2-digit",
      month: "2-digit",
    });
  } catch {
    return "—";
  }
}

export function LlmMetricsPanel() {
  const [data, setData] = useState<LlmMetricsResponse | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [auto, setAuto] = useState(true);

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const res = await api.llmMetrics(30);
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudieron cargar métricas");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!auto) return;
    const id = window.setInterval(() => {
      void load();
    }, 8000);
    return () => window.clearInterval(id);
  }, [auto, load]);

  const errRate =
    data && data.calls_total > 0
      ? Math.round((1000 * data.calls_error) / data.calls_total) / 10
      : 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">Métricas LLM</h3>
          <p className="text-[11px] text-slate-500 mt-0.5 max-w-xl">
            Contadores desde el último restart del API (memoria local). No es histórico largo ni
            Prometheus.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-[11px] text-slate-400 cursor-pointer">
            <input
              type="checkbox"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked)}
              className="rounded border-slate-600"
            />
            Auto 8s
          </label>
          <button
            type="button"
            disabled={busy}
            onClick={() => void load()}
            className="text-[11px] font-medium px-3 py-1.5 rounded-lg border border-slate-600/80 text-slate-300 hover:bg-slate-800/50 disabled:opacity-50"
          >
            {busy ? "Actualizando…" : "Actualizar"}
          </button>
        </div>
      </div>

      {error && (
        <p className="text-sm text-rose-300 border border-rose-500/30 rounded-xl px-4 py-2.5 bg-rose-500/10">
          {error}
        </p>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KpiCard label="Total llamadas" value={data.calls_total} tone="brand" />
            <KpiCard label="OK" value={data.calls_ok} tone="emerald" />
            <KpiCard
              label="Errores"
              value={data.calls_error}
              tone={data.calls_error > 0 ? "red" : "default"}
              helper={data.calls_total ? `${errRate}%` : undefined}
            />
            <KpiCard
              label="Latencia avg (OK)"
              value={`${Math.round(data.avg_latency_ms_ok)} ms`}
              tone="amber"
              helper={`ventana ${data.window_size} en memoria`}
            />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <GlassCard title="Por modelo" variant="technical">
              {!Object.keys(data.by_model || {}).length ? (
                <p className="text-xs text-slate-500">Sin llamadas aún.</p>
              ) : (
                <ul className="space-y-1.5">
                  {Object.entries(data.by_model).map(([model, n]) => (
                    <li
                      key={model}
                      className="flex justify-between gap-2 text-xs font-mono text-slate-300"
                    >
                      <span className="truncate">{model}</span>
                      <span className="text-ecolan-brand shrink-0">{n}</span>
                    </li>
                  ))}
                </ul>
              )}
            </GlassCard>

            <GlassCard title="Últimas llamadas" variant="technical" className="lg:col-span-2">
              {!data.recent?.length ? (
                <p className="text-xs text-slate-500">
                  Todavía no hubo tráfico LLM en este proceso. Usá el portal/diagnóstico o “Probar
                  IA” en Config.
                </p>
              ) : (
                <div className="overflow-x-auto -mx-1">
                  <table className="w-full text-[11px] text-left">
                    <thead>
                      <tr className="text-slate-500 border-b border-slate-800">
                        <th className="py-1.5 px-1 font-medium">Hora</th>
                        <th className="py-1.5 px-1 font-medium">Estado</th>
                        <th className="py-1.5 px-1 font-medium">ms</th>
                        <th className="py-1.5 px-1 font-medium">Modelo</th>
                        <th className="py-1.5 px-1 font-medium">Tokens</th>
                        <th className="py-1.5 px-1 font-medium">Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...data.recent].reverse().map((r, i) => (
                        <tr key={`${r.ts}-${i}`} className="border-b border-slate-800/60 text-slate-300">
                          <td className="py-1.5 px-1 font-mono whitespace-nowrap">{fmtTs(r.ts)}</td>
                          <td className="py-1.5 px-1">
                            <span
                              className={
                                r.ok ? "text-emerald-400" : "text-rose-400"
                              }
                            >
                              {r.ok ? "ok" : "error"}
                            </span>
                          </td>
                          <td className="py-1.5 px-1 font-mono">{Math.round(r.latency_ms)}</td>
                          <td className="py-1.5 px-1 font-mono truncate max-w-[140px]">
                            {r.model || "—"}
                          </td>
                          <td className="py-1.5 px-1 font-mono">
                            {r.total_tokens || "—"}
                          </td>
                          <td className="py-1.5 px-1 text-rose-300/90 truncate max-w-[180px]">
                            {r.error || ""}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </GlassCard>
          </div>
        </>
      )}
    </div>
  );
}
