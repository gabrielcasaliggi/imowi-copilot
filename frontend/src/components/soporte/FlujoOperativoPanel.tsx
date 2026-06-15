"use client";

import { GlassCard } from "@/components/ui/GlassCard";
import type { FlujoOperativo } from "@/lib/types";

function chipClass(hecho: string): string {
  if (hecho.endsWith("=ok")) return "border-emerald-500/40 bg-emerald-500/10 text-emerald-300";
  if (hecho.endsWith("=falla")) return "border-rose-500/40 bg-rose-500/10 text-rose-300";
  if (hecho.endsWith("=?")) return "border-slate-600 bg-slate-800/80 text-slate-400";
  return "border-slate-700 bg-slate-900/60 text-slate-300";
}

export function FlujoOperativoPanel({ flujo }: { flujo: FlujoOperativo | null }) {
  if (!flujo?.paso_id && !flujo?.hechos_resumen?.length) {
    return null;
  }

  return (
    <GlassCard title="Guía operativa" accent="emerald">
      <div className="space-y-2 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="px-2 py-0.5 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-200 font-mono text-[10px] uppercase">
            {flujo.categoria_label || flujo.categoria}
          </span>
          {flujo.completado && (
            <span className="text-[10px] text-slate-500">listo para NOC</span>
          )}
        </div>

        {flujo.paso_label && (
          <p className="text-slate-200 font-medium">{flujo.paso_label}</p>
        )}

        {flujo.paso_mensaje && (
          <p className="text-slate-400 leading-relaxed border-l-2 border-emerald-500/30 pl-2">
            {flujo.paso_mensaje}
          </p>
        )}

        {!!flujo.hechos_resumen?.length && (
          <div className="flex flex-wrap gap-1 pt-1">
            {flujo.hechos_resumen.map((h) => (
              <span
                key={h}
                className={`px-1.5 py-0.5 rounded border font-mono text-[9px] ${chipClass(h)}`}
              >
                {h}
              </span>
            ))}
          </div>
        )}
      </div>
    </GlassCard>
  );
}
