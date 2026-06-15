"use client";

import { useApp } from "@/contexts/AppContext";
import { KpiCard, SlaBadge } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
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

function MiniList({ items }: { items: { label: string; count: number }[] }) {
  if (!items.length) return <p className="text-xs text-slate-600">Sin datos.</p>;
  return (
    <div className="space-y-1">
      {items.map((x) => (
        <div
          key={x.label}
          className="flex justify-between gap-2 text-xs py-1 border-b border-slate-800/60 last:border-b-0"
        >
          <span className="text-slate-300 truncate">{x.label}</span>
          <span className="font-mono text-slate-500">{x.count}</span>
        </div>
      ))}
    </div>
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
      {intel?.risk_reasons?.length ? (
        <p className="text-[9px] text-slate-600 mt-1 truncate">
          {intel.risk_reasons.join(" · ")}
        </p>
      ) : null}
    </button>
  );
}

export function NocBoard() {
  const { isAdmin, stats, tickets, selectTicket } = useApp();
  if (!isAdmin) return null;

  const resumen = stats?.resumen;
  const abiertos = tickets.filter((t) => t.estado !== "Cerrado");
  const priority = [...abiertos]
    .sort(
      (a, b) =>
        (b.intelligence?.priority_score || 0) - (a.intelligence?.priority_score || 0),
    )
    .slice(0, 10);
  const criticos = abiertos.filter((t) => (t.intelligence?.priority_score || 0) >= 75).length;

  return (
    <div className="flex-1 min-h-0 overflow-y-auto space-y-4 p-4">
      <div>
        <h2 className="font-semibold text-slate-100">Centro de Control NOC</h2>
        <p className="text-[10px] font-mono text-slate-500">
          Priorización inteligente · causa probable · próxima acción
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
        <KpiCard label="Abiertos" value={resumen?.abiertos ?? abiertos.length} />
        <KpiCard label="Críticos" value={criticos} />
        <KpiCard
          label="SLA vencido"
          value={abiertos.filter((t) => t.estado_sla === "Vencido" || t.intelligence?.sla?.vencido).length}
        />
        <KpiCard
          label="N2"
          value={resumen?.n2 ?? tickets.filter((t) => t.nivel === "N2").length}
        />
        <KpiCard label="Cerrados" value={resumen?.cerrados ?? 0} />
        <KpiCard label="Prom. hs" value={resumen?.promedio_horas ?? 0} />
      </div>

      <div className="grid gap-4 grid-cols-1 xl:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <h3 className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-3">
            Cola NOC por riesgo
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

        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3 space-y-4">
          <h3 className="text-xs font-mono uppercase tracking-wider text-slate-500">
            Resumen operativo
          </h3>
          <div>
            <p className="text-[10px] font-mono uppercase text-slate-500 mb-2">
              Categorías principales
            </p>
            <MiniList items={(stats?.distribuciones?.categoria || []).slice(0, 5)} />
          </div>
          <div>
            <p className="text-[10px] font-mono uppercase text-slate-500 mb-2">
              Por cooperativa
            </p>
            <MiniList items={(stats?.distribuciones?.cooperativa || []).slice(0, 5)} />
          </div>
          <p className="text-[11px] text-slate-500">
            El motor IA prioriza por nivel, SLA, antigüedad, recurrencia y categoría crítica.
          </p>
        </div>
      </div>
    </div>
  );
}
