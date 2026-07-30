"use client";

import { useMemo } from "react";
import { GlassCard, SidebarSection } from "@/components/ui/GlassCard";
import { useApp } from "@/contexts/AppContext";

function matchUser(haystack: string | undefined, userKeys: Set<string>) {
  const v = (haystack || "").trim().toLowerCase();
  return !!v && userKeys.has(v);
}

/** Performance personal del agente — solo su actividad, sin KPIs de cola global. */
export function AgentSelfPanel() {
  const { can, user, tickets } = useApp();

  const keys = useMemo(() => {
    const s = new Set<string>();
    if (user?.usuario) {
      const u = user.usuario.toLowerCase();
      s.add(u);
      s.add(u.includes("@") ? u : `${u}@ops-hub.demo`);
      if (u.includes("@")) s.add(u.split("@", 1)[0]);
    }
    if (user?.nombre) s.add(user.nombre.toLowerCase());
    return s;
  }, [user]);

  const mine = useMemo(() => {
    const assigned = tickets.filter((t) => matchUser(t.asignado_a, keys));
    const createdOpen = tickets.filter(
      (t) =>
        t.estado !== "Cerrado" &&
        matchUser(t.creado_por, keys) &&
        !t.asignado_a,
    );
    const closed = tickets.filter(
      (t) =>
        t.estado === "Cerrado" &&
        (matchUser(t.asignado_a, keys) || matchUser(t.creado_por, keys)),
    );
    const open = [
      ...assigned.filter((t) => t.estado !== "Cerrado"),
      ...createdOpen,
    ];
    const slaRisk = open.filter(
      (t) => t.estado_sla === "Vencido" || t.intelligence?.sla?.vencido,
    ).length;
    return {
      abiertos: open.length,
      cerrados: closed.length,
      slaRisk,
      asignados: assigned.filter((t) => t.estado !== "Cerrado").length,
    };
  }, [tickets, keys]);

  if (!can("stats.self") || can("stats.agents") || can("stats.global") || can("stats.bot")) {
    return null;
  }

  return (
    <SidebarSection title="Mi actividad">
      <GlassCard title="Resumen personal" accent="cyan" variant="secondary">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
          <div>
            <p className="text-[10px] font-mono uppercase text-slate-500">Abiertos</p>
            <p className="text-lg font-mono text-slate-100 mt-0.5">{mine.abiertos}</p>
          </div>
          <div>
            <p className="text-[10px] font-mono uppercase text-slate-500">Asignados</p>
            <p className="text-lg font-mono text-violet-300 mt-0.5">{mine.asignados}</p>
          </div>
          <div>
            <p className="text-[10px] font-mono uppercase text-slate-500">SLA riesgo</p>
            <p className="text-lg font-mono text-amber-300 mt-0.5">{mine.slaRisk}</p>
          </div>
          <div>
            <p className="text-[10px] font-mono uppercase text-slate-500">Cerrados</p>
            <p className="text-lg font-mono text-emerald-300 mt-0.5">{mine.cerrados}</p>
          </div>
        </div>
        <p className="text-[11px] text-slate-500 mt-3">
          Solo tu carga. Abajo están los tickets libres para tomar.
        </p>
      </GlassCard>
    </SidebarSection>
  );
}
