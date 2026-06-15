"use client";

import { useApp } from "@/contexts/AppContext";
import { KpiCard } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";

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

export function NocBoard() {
  const { isAdmin, stats, tickets, selectTicket } = useApp();
  if (!isAdmin) return null;

  const resumen = stats?.resumen;
  const abiertos = tickets.filter((t) => t.estado !== "Cerrado");
  const priority = [...abiertos]
    .sort((a, b) => {
      const pa = (a.nivel === "N2" ? 2 : 0) + (a.proveedor ? 1 : 0);
      const pb = (b.nivel === "N2" ? 2 : 0) + (b.proveedor ? 1 : 0);
      return pb - pa;
    })
    .slice(0, 8);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
      <div>
        <h2 className="font-semibold text-slate-100">Centro de Control NOC</h2>
        <p className="text-[10px] font-mono text-slate-500">
          Cola operativa · priorización · seguimiento
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Abiertos" value={resumen?.abiertos ?? abiertos.length} />
        <KpiCard
          label="N2"
          value={resumen?.n2 ?? tickets.filter((t) => t.nivel === "N2").length}
        />
        <KpiCard label="Cerrados" value={resumen?.cerrados ?? 0} />
        <KpiCard label="Prom. hs" value={resumen?.promedio_horas ?? 0} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3">
          <h3 className="text-xs font-mono uppercase tracking-wider text-slate-500 mb-3">
            Cola NOC priorizada
          </h3>
          <div className="space-y-2">
            {priority.length ? (
              priority.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => selectTicket(t.id)}
                  className="w-full text-left p-3 rounded-lg border border-slate-800 bg-slate-900/70 hover:border-cyan-500/40"
                >
                  <div className="flex justify-between items-center gap-2">
                    <span className="font-mono text-cyan-300 text-xs">{t.id}</span>
                    <span className="flex gap-1">
                      {t.nivel && <StatusBadge value={t.nivel} />}
                      <StatusBadge value={t.estado} />
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1 truncate">
                    {t.organizacion || ""} · {t.linea || ""}
                  </p>
                  <p className="text-[10px] text-slate-500 mt-1 truncate">
                    {t.categoria || "General"}
                    {t.proveedor ? ` · ${t.proveedor}` : ""}
                  </p>
                </button>
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
              Estados
            </p>
            <MiniList items={(stats?.distribuciones?.estado || []).slice(0, 5)} />
          </div>
          <div>
            <p className="text-[10px] font-mono uppercase text-slate-500 mb-2">
              Proveedores sugeridos
            </p>
            <MiniList items={(stats?.distribuciones?.proveedor || []).slice(0, 5)} />
          </div>
          <p className="text-[11px] text-slate-500">
            Los reclamos nuevos los generan las cooperativas desde su consola. El NOC
            administra, prioriza y actualiza seguimiento.
          </p>
        </div>
      </div>
    </div>
  );
}
