"use client";

import { useApp } from "@/contexts/AppContext";

export function AgentConsole() {
  const { traces, clearTraces } = useApp();

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-3 flex flex-col min-h-[140px] max-h-[200px]">
      <div className="flex justify-between items-center mb-2">
        <h3 className="text-xs font-mono uppercase tracking-wider text-slate-500">
          Consola agentic
        </h3>
        <button
          type="button"
          onClick={clearTraces}
          className="text-[10px] font-mono text-slate-600 hover:text-slate-400"
        >
          Limpiar
        </button>
      </div>
      <div className="flex-1 overflow-y-auto text-[11px] font-mono space-y-0.5">
        {traces.length === 0 ? (
          <p className="text-slate-600">Sin traces.</p>
        ) : (
          traces.map((t, i) => (
            <div key={i} className="text-slate-400">
              {t}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
