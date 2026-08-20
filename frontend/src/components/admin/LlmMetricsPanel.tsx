"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, type LlmMetricsResponse } from "@/lib/api-client";
import { GlassCard, KpiCard } from "@/components/ui/GlassCard";

function localYmd(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function defaultDesde(): string {
  const d = new Date();
  d.setDate(d.getDate() - 7);
  return localYmd(d);
}

function defaultHasta(): string {
  return localYmd(new Date());
}

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
  const [probing, setProbing] = useState(false);
  const [probeMsg, setProbeMsg] = useState("");
  const [auto, setAuto] = useState(true);
  const [desde, setDesde] = useState(defaultDesde);
  const [hasta, setHasta] = useState(defaultHasta);

  const load = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const res = await api.llmMetrics({ recent: 30, desde, hasta });
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudieron cargar métricas");
    } finally {
      setBusy(false);
    }
  }, [desde, hasta]);

  const probe = useCallback(async () => {
    setProbing(true);
    setProbeMsg("");
    setError("");
    try {
      const res = await api.testAdminAi();
      if (res.ok) {
        setProbeMsg(`OK · ${res.model || "modelo"} · ${res.reply || "respuesta recibida"}`);
      } else {
        setProbeMsg(`Error · ${res.error || "sin detalle"}`);
      }
      await load();
    } catch (err) {
      setProbeMsg(err instanceof Error ? err.message : "Falló la prueba de IA");
    } finally {
      setProbing(false);
    }
  }, [load]);

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

  const onFilter = (e: FormEvent) => {
    e.preventDefault();
    void load();
  };

  const hist = data?.history;
  const live = data?.live || data;
  const histErrRate =
    hist && hist.calls_total > 0
      ? Math.round((1000 * hist.calls_error) / hist.calls_total) / 10
      : 0;
  const histModels = Object.entries(hist?.by_model || {}).sort(
    (a, b) => b[1].calls - a[1].calls,
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">Métricas LLM</h3>
          <p className="text-[11px] text-slate-500 mt-0.5 max-w-xl">
            Uso persistente en base de datos (sobrevive reinicios) + contadores live del proceso
            actual.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <form onSubmit={onFilter} className="flex gap-1.5 items-center flex-wrap">
            <input
              type="date"
              value={desde}
              onChange={(e) => setDesde(e.target.value)}
              className="bg-slate-950/80 border border-slate-700 rounded-lg px-2 py-1.5 text-[11px] font-mono outline-none focus:ring-1 focus:ring-ecolan-brand"
            />
            <input
              type="date"
              value={hasta}
              onChange={(e) => setHasta(e.target.value)}
              className="bg-slate-950/80 border border-slate-700 rounded-lg px-2 py-1.5 text-[11px] font-mono outline-none focus:ring-1 focus:ring-ecolan-brand"
            />
            <button
              type="submit"
              className="text-[11px] px-2.5 py-1.5 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800/50"
            >
              Filtrar
            </button>
          </form>
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
            disabled={probing || busy}
            onClick={() => void probe()}
            className="text-[11px] font-medium px-3 py-1.5 rounded-lg border border-ecolan-brand/40 bg-ecolan-brand/10 text-ecolan-brand hover:bg-ecolan-brand/15 disabled:opacity-50"
          >
            {probing ? "Probando…" : "Probar IA"}
          </button>
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

      {probeMsg && (
        <p
          className={`text-sm rounded-xl px-4 py-2.5 border ${
            probeMsg.startsWith("OK")
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
              : "border-rose-500/30 bg-rose-500/10 text-rose-200"
          }`}
        >
          {probeMsg}
        </p>
      )}

      {error && (
        <p className="text-sm text-rose-300 border border-rose-500/30 rounded-xl px-4 py-2.5 bg-rose-500/10">
          {error}
        </p>
      )}

      {data && (
        <>
          <section className="space-y-3">
            <div>
              <h4 className="text-xs font-mono uppercase text-slate-500">Uso en el período</h4>
              <p className="text-[11px] text-slate-600 mt-0.5">
                Persistido · {hist?.desde?.slice(0, 10) || desde} → {hist?.hasta?.slice(0, 10) || hasta}
              </p>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
              <KpiCard label="Total llamadas" value={hist?.calls_total ?? 0} tone="brand" />
              <KpiCard label="OK" value={hist?.calls_ok ?? 0} tone="emerald" />
              <KpiCard
                label="Errores"
                value={hist?.calls_error ?? 0}
                tone={(hist?.calls_error ?? 0) > 0 ? "red" : "default"}
                helper={hist?.calls_total ? `${histErrRate}%` : undefined}
              />
              <KpiCard
                label="Latencia avg"
                value={`${Math.round(hist?.avg_latency_ms_ok ?? 0)} ms`}
                tone="amber"
              />
              <KpiCard
                label="Tokens"
                value={hist?.tokens_total ?? 0}
                tone="cyan"
                helper="suma del período"
              />
            </div>
          </section>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <GlassCard title="Por modelo (período)" variant="technical">
              {!histModels.length ? (
                <p className="text-xs text-slate-500">Sin llamadas en el rango.</p>
              ) : (
                <ul className="space-y-2">
                  {histModels.map(([model, m]) => (
                    <li key={model} className="text-xs">
                      <div className="flex justify-between gap-2 font-mono text-slate-300">
                        <span className="truncate">{model}</span>
                        <span className="text-ecolan-brand shrink-0">{m.calls}</span>
                      </div>
                      <p className="text-[10px] text-slate-500 mt-0.5 font-mono">
                        {m.ok} ok · {m.error} err · {m.tokens} tok · {Math.round(m.avg_latency_ms_ok)} ms
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </GlassCard>

            <GlassCard title="Últimas del período" variant="technical" className="lg:col-span-2">
              {!hist?.recent?.length ? (
                <p className="text-xs text-slate-500">
                  Todavía no hay filas persistidas en este rango. Tocá «Probar IA» o generá tráfico
                  Eco/consola.
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
                      {[...hist.recent].reverse().map((r, i) => (
                        <tr key={`${r.ts}-${i}`} className="border-b border-slate-800/60 text-slate-300">
                          <td className="py-1.5 px-1 font-mono whitespace-nowrap">{fmtTs(r.ts)}</td>
                          <td className="py-1.5 px-1">
                            <span className={r.ok ? "text-emerald-400" : "text-rose-400"}>
                              {r.ok ? "ok" : "error"}
                            </span>
                          </td>
                          <td className="py-1.5 px-1 font-mono">{Math.round(r.latency_ms)}</td>
                          <td className="py-1.5 px-1 font-mono truncate max-w-[140px]">
                            {r.model || "—"}
                          </td>
                          <td className="py-1.5 px-1 font-mono">{r.total_tokens || "—"}</td>
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

          <details className="rounded-2xl border border-slate-800 bg-slate-900/30">
            <summary className="cursor-pointer px-4 py-3 text-xs font-mono uppercase text-slate-500 select-none">
              Live desde restart · {live?.calls_total ?? 0} llamadas en memoria
            </summary>
            <div className="px-4 pb-4 border-t border-slate-800 space-y-3">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 pt-3">
                <KpiCard label="Total live" value={live?.calls_total ?? 0} tone="default" />
                <KpiCard label="OK live" value={live?.calls_ok ?? 0} tone="emerald" />
                <KpiCard label="Errores live" value={live?.calls_error ?? 0} tone="red" />
                <KpiCard
                  label="Latencia live"
                  value={`${Math.round(live?.avg_latency_ms_ok ?? 0)} ms`}
                  tone="amber"
                  helper={`ventana ${live?.window_size ?? 0}`}
                />
              </div>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
