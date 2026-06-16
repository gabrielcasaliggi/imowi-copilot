"use client";

import { useState } from "react";
import { useApp } from "@/contexts/AppContext";

export function AgentConsole() {
  const { traces, clearTraces } = useApp();
  const [expanded, setExpanded] = useState(true);

  return (
    <div
      className={`trace-panel rounded-xl p-3 flex flex-col transition-all duration-200 ${
        expanded ? "trace-panel-expanded" : "trace-panel-compact"
      }`}
    >
      <div className="flex justify-between items-center mb-2 shrink-0">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400">
            Trazabilidad operativa
          </h3>
          {traces.length > 0 && (
            <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-cyan-400/90 border border-slate-700">
              {traces.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-[11px] font-mono text-slate-500 hover:text-slate-300 px-2 py-0.5 rounded border border-slate-700/80"
          >
            {expanded ? "Compactar" : "Expandir"}
          </button>
          <button
            type="button"
            onClick={clearTraces}
            className="text-[11px] font-mono text-slate-500 hover:text-slate-300"
          >
            Limpiar
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto text-[11px] font-mono space-y-0.5 min-h-0">
        {traces.length === 0 ? (
          <p className="text-slate-500">Sin eventos técnicos por ahora.</p>
        ) : (
          traces.map((t, i) => (
            <div key={i} className="trace-line text-slate-400">
              {t}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
