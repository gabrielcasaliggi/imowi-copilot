"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useApp } from "@/contexts/AppContext";
import { SlaBadge } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api } from "@/lib/api-client";
import type { Ticket } from "@/lib/types";

function RiskBadge({ level, score }: { level?: string; score?: number }) {
  const colors: Record<string, string> = {
    critico: "border-rose-500/40 text-rose-700 bg-rose-50 dark:text-red-300 dark:bg-red-500/10",
    alto: "border-orange-500/40 text-orange-700 bg-orange-50 dark:text-orange-300 dark:bg-orange-500/10",
    medio: "border-amber-500/40 text-amber-700 bg-amber-50 dark:text-amber-300 dark:bg-amber-500/10",
    bajo: "border-slate-300 text-slate-600 bg-slate-50 dark:border-slate-600 dark:text-slate-400 dark:bg-slate-800/50",
  };
  const cls = colors[level || "bajo"] || colors.bajo;
  return (
    <span className={`px-2.5 py-0.5 text-[10px] font-medium rounded-full border ${cls}`}>
      {score ?? 0} · {level || "bajo"}
    </span>
  );
}

function PriorityTicketRow({
  t,
  onSelect,
}: {
  t: Ticket;
  onSelect: (id: string) => void;
}) {
  const intel = t.intelligence;
  return (
    <button
      type="button"
      onClick={() => onSelect(t.id)}
      className="w-full text-left py-3.5 px-4 rounded-xl border border-slate-700/80 bg-slate-900/50 hover:bg-slate-50/5 hover:border-ecolan-brand/35 shadow-sm transition-all duration-200 ease-in-out"
    >
      <div className="flex justify-between items-start gap-2">
        <span className="font-mono text-ecolan-brand text-xs font-semibold tabular-nums">{t.id}</span>
        <RiskBadge level={intel?.risk_level} score={intel?.priority_score} />
      </div>
      <div className="flex gap-1.5 mt-2 flex-wrap">
        {t.nivel && <StatusBadge value={t.nivel} />}
        <StatusBadge value={t.estado} />
        <SlaBadge label={t.sla_label} estado={t.estado_sla || intel?.sla?.estado_sla} />
      </div>
      <p className="text-xs text-slate-400 mt-2 truncate">
        {t.organizacion || ""} · {t.linea || ""} · {t.categoria || "General"}
      </p>
      {intel?.probable_cause && (
        <p className="text-[11px] text-slate-500 mt-1.5 truncate">
          Causa probable: <span className="text-slate-300">{intel.probable_cause}</span>
        </p>
      )}
      {intel?.next_best_action && (
        <p className="text-[11px] text-ecolan-brand mt-1 line-clamp-2 leading-relaxed">
          → {intel.next_best_action}
        </p>
      )}
    </button>
  );
}

/** Consola admin: solo acción (prioridad). Métricas → /estadisticas. Cola filtrable → /tickets. */
export function NocBoard() {
  const { isAdmin, tickets, selectTicket, tenantSlug } = useApp();
  const [kbPendientes, setKbPendientes] = useState(0);

  useEffect(() => {
    if (!isAdmin) return;
    void api
      .kbContributions({ estado: "pendiente" }, tenantSlug)
      .then((r) => setKbPendientes((r.contribuciones || []).length))
      .catch(() => setKbPendientes(0));
  }, [isAdmin, tenantSlug, tickets]);

  if (!isAdmin) return null;

  const abiertos = tickets.filter((t) => t.estado !== "Cerrado");
  const priority = [...abiertos]
    .sort(
      (a, b) =>
        (b.intelligence?.priority_score || 0) - (a.intelligence?.priority_score || 0),
    )
    .slice(0, 8);
  const criticos = abiertos.filter((t) => (t.intelligence?.priority_score || 0) >= 75).length;
  const slaVencidos = abiertos.filter(
    (t) => t.estado_sla === "Vencido" || t.intelligence?.sla?.vencido,
  ).length;

  return (
    <div className="flex-1 min-h-0 overflow-y-auto space-y-5 p-5">
      <div className="flex flex-wrap justify-between gap-3 items-start">
        <div className="space-y-1">
          <h2 className="font-semibold text-slate-100 text-lg tracking-tight">Prioridad operativa</h2>
          <p className="text-xs text-slate-500">
            Top riesgo · causa probable · próxima acción
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {kbPendientes > 0 && (
            <Link
              href="/conocimiento"
              className="text-xs font-medium px-3 py-1.5 rounded-lg border border-amber-500/30 text-amber-700 bg-amber-50 dark:text-amber-300 dark:bg-transparent hover:bg-amber-500/10 transition-all duration-200"
            >
              KB pendientes: {kbPendientes} →
            </Link>
          )}
          <Link
            href="/tickets"
            className="text-xs font-medium px-3 py-1.5 rounded-lg border border-ecolan-brand/35 text-ecolan-brand hover:bg-ecolan-brand/10 transition-all duration-200"
          >
            Cola filtrable →
          </Link>
          <Link
            href="/estadisticas"
            className="text-xs font-medium px-3 py-1.5 rounded-lg border border-slate-600/80 text-slate-400 hover:bg-slate-800/40 transition-all duration-200"
          >
            Estadísticas →
          </Link>
        </div>
      </div>

      <div className="flex flex-wrap gap-2.5 text-xs">
        <span className="px-3 py-1.5 rounded-full border border-slate-700/80 bg-slate-950/50 text-slate-400">
          Abiertos <strong className="tabular-nums text-slate-100 ml-1">{abiertos.length}</strong>
        </span>
        <span className="px-3 py-1.5 rounded-full border border-rose-500/30 bg-rose-50 text-rose-700 dark:bg-red-500/10 dark:text-red-200">
          Críticos <strong className="tabular-nums ml-1">{criticos}</strong>
        </span>
        <span className="px-3 py-1.5 rounded-full border border-amber-500/30 bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-200">
          SLA vencido <strong className="tabular-nums ml-1">{slaVencidos}</strong>
        </span>
      </div>

      <div className="rounded-xl border border-slate-700/80 bg-slate-950/30 p-4 shadow-sm">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3.5">
          Cola por riesgo
        </h3>
        <div className="space-y-2.5">
          {priority.length ? (
            priority.map((t) => (
              <PriorityTicketRow key={t.id} t={t} onSelect={selectTicket} />
            ))
          ) : (
            <p className="text-sm text-slate-500 py-6 text-center">Sin tickets abiertos.</p>
          )}
        </div>
      </div>
    </div>
  );
}
