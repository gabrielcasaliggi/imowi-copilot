"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { GlassCard, SidebarSection } from "@/components/ui/GlassCard";
import { useApp } from "@/contexts/AppContext";
import { api } from "@/lib/api-client";
import type { AgentPerformanceRow, AdminUser } from "@/lib/types";

const inputCls =
  "w-full bg-slate-950 border border-slate-700/80 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500/40";

/** Equipo: carga/disponibilidad. CRUD de agentes solo para supervisor (admin usa /admin). */
export function AgentsTeamPanel() {
  const { can, isAdmin, tenantSlug } = useApp();
  const [agentes, setAgentes] = useState<AgentPerformanceRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [newAgent, setNewAgent] = useState({
    nombre: "",
    email: "",
    password: "cliente",
  });

  const canManage = can("users.manage_agents") && !isAdmin;
  const canStats = can("stats.agents") || can("stats.global");
  const slug = isAdmin ? tenantSlug : undefined;

  const load = useCallback(async () => {
    if (!canStats && !canManage) return;
    setLoading(true);
    try {
      if (canStats) {
        const data = await api.agentsPerformance(slug);
        setAgentes(data.agentes || []);
      } else {
        const data = await api.orgUsers();
        setAgentes(
          (data.usuarios || []).map((u: AdminUser) => ({
            ...u,
            tickets_abiertos: 0,
            tickets_asignados: 0,
            tickets_cerrados: 0,
          })),
        );
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "No se pudo cargar el equipo");
    } finally {
      setLoading(false);
    }
  }, [canStats, canManage, slug]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!canStats && !can("users.manage_agents")) return null;

  const onCreate = async (e: FormEvent) => {
    e.preventDefault();
    if (!canManage) return;
    setBusy(true);
    setMessage("");
    try {
      await api.createOrgUser({ ...newAgent, rol: "agente" });
      setNewAgent({ nombre: "", email: "", password: "cliente" });
      setMessage("Agente creado.");
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Error al crear agente");
    } finally {
      setBusy(false);
    }
  };

  const onToggle = async (a: AgentPerformanceRow) => {
    if (!canManage) return;
    setBusy(true);
    try {
      await api.updateOrgUser(a.id, { activo: !(a.activo !== false) });
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Error al actualizar");
    } finally {
      setBusy(false);
    }
  };

  const dispTone = (d?: string) => {
    if (d === "disponible") return "text-emerald-300";
    if (d === "ocupado") return "text-amber-300";
    return "text-slate-400";
  };

  const disponibles = agentes.filter(
    (a) => a.disponibilidad === "disponible" && a.activo !== false,
  ).length;

  return (
    <SidebarSection title="Equipo">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <p className="text-xs text-slate-400">
          {agentes.length} agentes · {disponibles} disponibles
          {isAdmin && (
            <>
              {" · "}
              <Link href="/admin" className="text-cyan-300 hover:text-cyan-200">
                Gestionar usuarios en Admin
              </Link>
            </>
          )}
        </p>
      </div>

      {message && (
        <p className="text-xs text-cyan-200 mb-2 border border-cyan-500/20 rounded-lg px-3 py-2 bg-cyan-500/8">
          {message}
        </p>
      )}

      <div className={`grid grid-cols-1 ${canManage ? "xl:grid-cols-2" : ""} gap-4`}>
        <GlassCard title="Carga por agente" accent="cyan" variant="secondary">
          {loading ? (
            <p className="text-xs text-slate-500">Cargando…</p>
          ) : agentes.length === 0 ? (
            <p className="text-xs text-slate-500">Sin agentes en esta cooperativa.</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {agentes.map((a) => (
                <div
                  key={a.id}
                  className="flex justify-between gap-2 text-xs py-2 border-b border-slate-800/60 last:border-b-0"
                >
                  <div className="min-w-0">
                    <p className="text-slate-200 font-medium truncate">{a.nombre}</p>
                    <p className={`text-[11px] mt-0.5 ${dispTone(a.disponibilidad)}`}>
                      {a.disponibilidad || "disponible"}
                      {a.activo === false ? " · desactivado" : ""}
                    </p>
                  </div>
                  <div className="text-right shrink-0 space-y-1">
                    <p className="font-mono text-slate-300">{a.tickets_abiertos} abiertos</p>
                    <p className="text-[11px] text-slate-500">{a.tickets_cerrados} cerrados</p>
                    {canManage && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void onToggle(a)}
                        className="text-[11px] text-cyan-300 hover:text-cyan-200 disabled:opacity-50"
                      >
                        {a.activo === false ? "Reactivar" : "Desactivar"}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </GlassCard>

        {canManage && (
          <GlassCard title="Alta de agente" accent="emerald" variant="secondary">
            <form onSubmit={onCreate} className="space-y-2.5">
              <input
                required
                placeholder="Nombre"
                value={newAgent.nombre}
                onChange={(e) => setNewAgent({ ...newAgent, nombre: e.target.value })}
                className={inputCls}
              />
              <input
                required
                type="email"
                placeholder="Email"
                value={newAgent.email}
                onChange={(e) => setNewAgent({ ...newAgent, email: e.target.value })}
                className={inputCls}
              />
              <input
                type="password"
                placeholder="Clave inicial"
                value={newAgent.password}
                onChange={(e) => setNewAgent({ ...newAgent, password: e.target.value })}
                className={`${inputCls} font-mono`}
              />
              <button
                type="submit"
                disabled={busy}
                className="text-xs font-medium px-4 py-2 rounded-lg border border-emerald-500/35 text-emerald-200 hover:bg-emerald-500/10 disabled:opacity-50"
              >
                Crear agente
              </button>
            </form>
          </GlassCard>
        )}
      </div>
    </SidebarSection>
  );
}
