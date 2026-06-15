"use client";

import { useApp } from "@/contexts/AppContext";
import { StatusBadge } from "@/components/ui/StatusBadge";

export function TelemetryGrid() {
  const { telemetry, simulateFailure } = useApp();

  return (
    <div className="p-4 space-y-4">
      <div>
        <h2 className="font-semibold text-slate-100">Monitor de Red</h2>
        <p className="text-[10px] font-mono text-slate-500">
          Telemetría OSS/BSS · simulación de anomalías
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {telemetry.map((e) => (
          <div
            key={e.id}
            className="p-4 rounded-xl border border-slate-800 bg-slate-900/70"
          >
            <div className="flex justify-between mb-2">
              <span className="font-mono text-sm">{e.elemento_red}</span>
              <StatusBadge value={e.estado_actual} />
            </div>
            <p className="text-xs font-mono text-slate-500">
              {e.metrica} = {e.valor_actual}
            </p>
            <button
              type="button"
              onClick={() => simulateFailure(e.elemento_red)}
              className="mt-3 w-full text-xs py-1.5 rounded border border-amber-500/30 text-amber-300 hover:bg-amber-500/10"
            >
              Simular falla
            </button>
          </div>
        ))}
      </div>
      {!telemetry.length && (
        <p className="text-slate-500 text-sm">Sin elementos de telemetría.</p>
      )}
    </div>
  );
}
