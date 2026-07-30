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
    critico: "border-red-500/40 text-red-300 bg-red-500/10",
    alto: "border-orange-500/40 text-orange-300 bg-orange-500/10",
    medio: "border-amber-500/40 text-amber-300 bg-amber-500/10",
    bajo: "border-slate-600 text-slate-400 bg-slate-800/50",
  };
  const cls = colors[level || "bajo"] || colors.bajo;
  return (
    <span className={`px-2 py-0.5 text-[10px] font-mono rounded border ${cls}`}>
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
      className="w-full text-left p-3 rounded-lg border border-slate-800 bg-slate-900/70 hover:border-cyan-500/40"
    >
      <div className="flex justify-between items-start gap-2">
        <span className="font-mono text-cyan-300 text-xs">{t.id}</span>
        <RiskBadge level={intel?.risk_level} score={intel?.priority_score} />
      </div>
      <div className="flex gap-1 mt-1 flex-wrap">
        {t.nivel && <StatusBadge value={t.nivel} />}
        <StatusBadge value={t.estado} />
        <SlaBadge label={t.sla_label} estado={t.estado_sla || intel?.sla?.estado_sla} />
      </div>
      <p className="text-[11px] text-slate-400 mt-1 truncate">
        {t.organizacion || ""} · {t.linea || ""} · {t.categoria || "General"}
      </p>
      {intel?.probable_cause && (
        <p className="text-[10px] text-violet-300/90 mt-1 truncate">
          Causa probable: {intel.probable_cause}
        </p>
      )}
      {intel?.next_best_action && (
        <p className="text-[10px] text-cyan-400/80 mt-1 line-clamp-2">
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
    <div className="flex-1 min-h-0 overflow-y-auto space-y-4 p-4">
      <div className="flex flex-wrap justify-between gap-2 items-start">
        <div>
          <h2 className="font-semibold text-slate-100">Prioridad operativa</h2>
          <p className="text-[10px] font-mono text-slate-500">
            Top riesgo · causa probable · próxima acción
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {kbPendientes > 0 && (
            <Link
              href="/conocimiento"
              className="text-[10px] font-mono px-2.5 py-1 rounded border border-amber-500/30 text-amber-300 hover:bg-amber-500/10"
            >
              KB pendientes: {kbPendientes} →
            </Link>
          )}
          <Link
            href="/tickets"
            className="text-[10px] font-mono px-2.5 py-1 rounded border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/10"
          >
            Cola filtrable →
          </Link>
          <Link
            href="/estadisticas"
            className="text-[10px] font-mono px-2.5 py-1 rounded border border-slate-600 text-slate-300 hover:bg-slate-800/50"
          >
            Estadísticas →
          </Link>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 text-xs">
        <span className="px-2.5 py-1 rounded-lg border border-slate-700 bg-slate-950/60 text-slate-300">
          Abiertos <strong className="font-mono text-slate-100 ml-1">{abiertos.length}</strong>
        </span>
        <span className="px-2.5 py-1 rounded-lg border border-red-500/30 bg-red-500/10 text-red-200">
          Críticos <strong className="font-mono ml-1">{criticos}</strong>
        </span>
        <span className="px-2.5 py-1 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-200">
          SLA vencido <strong className="font-mono ml-1">{slaVencidos}</strong>
        </span>
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
        <h3 className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-3">
          Cola por riesgo
        </h3>
        <div className="space-y-2">
          {priority.length ? (
            priority.map((t) => (
              <PriorityTicketRow key={t.id} t={t} onSelect={selectTicket} />
            ))
          ) : (
            <p className="text-sm text-slate-500">Sin tickets abiertos.</p>
          )}
        </div>
      </div>
    </div>
  );
}
