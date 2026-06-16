"use client";

import { GlassCard } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useApp } from "@/contexts/AppContext";
import { ESTADO_CASO_LABELS } from "@/lib/types";

function pasosConfirmados(hechos: string[] | undefined): number {
  if (!hechos?.length) return 0;
  return hechos.filter((h) => h.includes("=ok") || h.includes("=falla")).length;
}

export function EstadoOperativoPanel() {
  const {
    isAdmin,
    flujoOperativo,
    ticketFormacion,
    ticketTimeline,
    estadoConversacion,
  } = useApp();

  if (isAdmin) return null;

  const pasosTimeline = ticketTimeline.filter((e) => e.tipo === "paso_operativo").length;
  const pasosHechos = pasosConfirmados(flujoOperativo?.hechos_resumen);
  const pasosTotal = Math.max(pasosTimeline, pasosHechos);

  if (!flujoOperativo?.paso_id && !ticketFormacion && !estadoConversacion) {
    return null;
  }

  return (
    <GlassCard title="Estado operativo" accent="cyan" variant="secondary">
      <div className="space-y-2.5 text-xs">
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">Estado caso</span>
          <span className="text-slate-200 font-medium">
            {ESTADO_CASO_LABELS[estadoConversacion || ""] || estadoConversacion || "—"}
          </span>
        </div>
        {flujoOperativo?.paso_label && (
          <div>
            <p className="text-slate-500 mb-0.5">Paso actual</p>
            <p className="text-slate-100 font-medium">{flujoOperativo.paso_label}</p>
          </div>
        )}
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">Pasos confirmados</span>
          <span className="font-mono text-emerald-300 text-sm">{pasosTotal}</span>
        </div>
        <div className="flex justify-between gap-2 items-center">
          <span className="text-slate-500">Ticket</span>
          {ticketFormacion?.id ? (
            <span className="flex gap-1.5 items-center">
              <span className="font-mono text-amber-300">{ticketFormacion.id}</span>
              <StatusBadge value={ticketFormacion.estado} />
            </span>
          ) : (
            <span className="text-slate-500">pendiente</span>
          )}
        </div>
        {flujoOperativo?.completado && (
          <p className="text-[11px] text-emerald-300 border border-emerald-500/30 rounded-lg px-2.5 py-1.5 bg-emerald-500/8">
            Flujo N1 completo — listo para NOC
          </p>
        )}
      </div>
    </GlassCard>
  );
}
