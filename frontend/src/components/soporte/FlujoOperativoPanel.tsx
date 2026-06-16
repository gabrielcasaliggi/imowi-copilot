"use client";

import type { FlujoOperativo } from "@/lib/types";

function chipClass(hecho: string): string {
  if (hecho.endsWith("=ok")) return "hecho-chip-ok";
  if (hecho.endsWith("=falla")) return "hecho-chip-falla";
  if (hecho.endsWith("=?")) return "hecho-chip-pending";
  return "hecho-chip-neutral";
}

function formatHechoLabel(hecho: string): string {
  const [key, val] = hecho.split("=");
  const labels: Record<string, string> = {
    datos_móviles: "Datos móviles",
    apn: "APN",
    roaming_jsc: "Roaming JSC",
    roaming_off: "Roaming off",
    roaming_on: "Roaming on",
    reinicio: "Reinicio",
    llamadas: "Llamadas",
    navegación: "Navegación",
    zona_unica: "Zona única",
    varias_zonas: "Varias zonas",
    sim: "SIM",
  };
  const name = labels[key] || key.replace(/_/g, " ");
  if (val === "ok") return `${name}: OK`;
  if (val === "falla") return `${name}: falla`;
  if (val === "?") return `${name}: pendiente`;
  return hecho;
}

function calcularProgreso(hechos: string[] | undefined): { pct: number; confirmados: number; total: number } {
  if (!hechos?.length) return { pct: 0, confirmados: 0, total: 0 };
  const total = hechos.length;
  const confirmados = hechos.filter((h) => h.includes("=ok") || h.includes("=falla")).length;
  const pct = total > 0 ? Math.round((confirmados / total) * 100) : 0;
  return { pct, confirmados, total };
}

function extraerNumeroPaso(pasoLabel?: string | null): string | null {
  if (!pasoLabel) return null;
  const match = pasoLabel.match(/^(\d+)\./);
  return match ? match[1] : null;
}

export function FlujoOperativoPanel({ flujo }: { flujo: FlujoOperativo | null }) {
  if (!flujo?.paso_id && !flujo?.hechos_resumen?.length) {
    return null;
  }

  const { pct, confirmados, total } = calcularProgreso(flujo.hechos_resumen);
  const pasoNum = extraerNumeroPaso(flujo.paso_label);

  return (
    <div className="operational-guide-card rounded-2xl p-4">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-wider text-emerald-400/90 mb-1">
            Guía operativa
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-2.5 py-0.5 rounded-md border border-emerald-500/35 bg-emerald-500/12 text-emerald-200 font-mono text-[11px] uppercase">
              {flujo.categoria_label || flujo.categoria}
            </span>
            {flujo.completado && (
              <span className="text-[11px] text-emerald-300 font-medium">Listo para NOC</span>
            )}
          </div>
        </div>
        {pasoNum && (
          <span className="text-2xl font-semibold tabular-nums text-emerald-300/80 leading-none">
            {pasoNum}
          </span>
        )}
      </div>

      {total > 0 && (
        <div className="mb-3">
          <div className="flex justify-between text-[11px] text-slate-400 mb-1.5">
            <span>Hechos confirmados</span>
            <span className="font-mono text-emerald-300">
              {confirmados}/{total} · {pct}%
            </span>
          </div>
          <div className="operational-progress-track">
            <div className="operational-progress-fill" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      {flujo.paso_label && (
        <p className="text-sm font-semibold text-slate-100 mb-1">{flujo.paso_label}</p>
      )}

      {flujo.paso_mensaje && (
        <p className="text-sm text-slate-300 leading-relaxed border-l-2 border-emerald-500/40 pl-3 mb-3">
          {flujo.paso_mensaje}
        </p>
      )}

      {!!flujo.hechos_resumen?.length && (
        <div>
          <p className="text-[11px] text-slate-500 mb-1.5 uppercase tracking-wide font-mono">
            Estado técnico
          </p>
          <div className="flex flex-wrap gap-1.5">
            {flujo.hechos_resumen.map((h) => (
              <span
                key={h}
                className={`px-2 py-0.5 rounded-md border font-mono text-[11px] ${chipClass(h)}`}
                title={h}
              >
                {formatHechoLabel(h)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
