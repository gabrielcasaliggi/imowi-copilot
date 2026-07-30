"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { SlaBadge } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api } from "@/lib/api-client";
import type { Ticket } from "@/lib/types";

const ESTADOS = ["", "Abierto", "En Revisión", "Escalado", "Pendiente Cliente", "Cerrado"];
const NIVELES = ["", "N1", "N2"];
const SLA_OPTS = ["", "Vencido", "Crítico", "En riesgo", "En tiempo"];

function TicketRow({
  t,
  onSelect,
  canReassign,
  agents,
  onReassign,
}: {
  t: Ticket;
  onSelect: (id: string) => void;
  canReassign: boolean;
  agents: { email: string; nombre: string }[];
  onReassign: (ticketId: string, asignado_a: string) => void;
}) {
  const intel = t.intelligence;
  return (
    <div className="w-full text-left p-3 rounded-xl border border-slate-800 bg-slate-950/60 hover:border-cyan-500/40 transition-colors">
      <button type="button" onClick={() => onSelect(t.id)} className="w-full text-left">
        <div className="flex justify-between items-start gap-2">
          <span className="font-mono text-cyan-300 text-xs">{t.id}</span>
          <span className="text-[10px] font-mono text-amber-400">
            {intel?.priority_score ?? 0}
          </span>
        </div>
        <div className="flex flex-wrap gap-1 mt-1.5">
          {t.nivel && <StatusBadge value={t.nivel} />}
          <StatusBadge value={t.estado} />
          <SlaBadge label={t.sla_label} estado={t.estado_sla || intel?.sla?.estado_sla} />
        </div>
        <p className="text-[11px] text-slate-400 mt-1 truncate">
          {t.organizacion ? `${t.organizacion} · ` : ""}
          {t.linea || "—"} · {t.categoria || "General"}
        </p>
        {t.asignado_a && (
          <p className="text-[10px] text-violet-300/90 mt-1 truncate">
            Asignado: {t.asignado_a}
          </p>
        )}
        {intel?.next_best_action && (
          <p className="text-[10px] text-cyan-500/80 mt-1 line-clamp-1">
            → {intel.next_best_action}
          </p>
        )}
      </button>
      {canReassign && agents.length > 0 && (
        <select
          value={t.asignado_a || ""}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => {
            e.stopPropagation();
            if (e.target.value) onReassign(t.id, e.target.value);
          }}
          className="mt-2 w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-[11px] text-slate-300"
        >
          <option value="">Derivar a agente…</option>
          {agents.map((a) => (
            <option key={a.email} value={a.email}>
              {a.nombre} ({a.email})
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

export function TicketQueuePanel() {
  const router = useRouter();
  const { isAdmin, can, tenantSlug } = useApp();

  const [items, setItems] = useState<Ticket[]>([]);
  const [agents, setAgents] = useState<{ email: string; nombre: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [estado, setEstado] = useState("");
  const [nivel, setNivel] = useState("");
  const [sla, setSla] = useState("");
  const [categoria, setCategoria] = useState("");
  const [q, setQ] = useState("");
  const [soloAbiertos, setSoloAbiertos] = useState(true);

  const canReassign = can("tickets.reassign");
  const slug = isAdmin ? tenantSlug : undefined;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.tickets(
        {
          estado,
          nivel,
          sla,
          categoria,
          q,
          solo_abiertos: soloAbiertos,
        },
        slug,
      );
      setItems(res.tickets || []);
    } finally {
      setLoading(false);
    }
  }, [estado, nivel, sla, categoria, q, soloAbiertos, slug]);

  const canQueue = can("tickets.queue.view");

  useEffect(() => {
    if (canQueue) load();
  }, [canQueue, load]);

  useEffect(() => {
    if (!canReassign) return;
    void api
      .orgUsers()
      .then((d) =>
        setAgents(
          (d.usuarios || [])
            .filter((u) => u.activo !== false)
            .map((u) => ({ email: u.email, nombre: u.nombre })),
        ),
      )
      .catch(() => setAgents([]));
  }, [canReassign]);

  const onReassign = async (ticketId: string, asignado_a: string) => {
    await api.reassignTicket(ticketId, { asignado_a }, slug);
    await load();
  };

  const vencidos = useMemo(
    () =>
      items.filter(
        (t) =>
          t.estado !== "Cerrado" &&
          (t.estado_sla === "Vencido" || t.intelligence?.sla?.vencido),
      ).length,
    [items],
  );

  const onSelect = (id: string) => {
    router.push(`/soporte?ticket=${encodeURIComponent(id)}`);
  };

  const onFilter = (e: FormEvent) => {
    e.preventDefault();
    load();
  };

  if (!canQueue) {
    return (
      <div className="p-6 text-sm text-slate-500">
        No tenés permiso para ver la cola de tickets.
      </div>
    );
  }

  return (
    <div className="space-y-4 min-h-0">
      <div className="flex flex-wrap justify-between gap-3 items-end">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-widest text-cyan-400/80">
            Gestión de tickets
          </p>
          <h2 className="text-xl font-semibold text-slate-50">Cola operativa</h2>
          <p className="text-sm text-slate-400 mt-1">
            Filtros, SLA y priorización — contexto telco preservado.
          </p>
        </div>
        <Link
          href="/soporte"
          className="text-xs px-3 py-1.5 rounded-lg border border-cyan-500/30 text-cyan-200 hover:bg-cyan-500/10"
        >
          Ir a consola
        </Link>
      </div>

      <div className="flex flex-wrap gap-3 text-xs">
        <span className="px-2.5 py-1 rounded-lg border border-slate-700 bg-slate-950/60 text-slate-300">
          En vista <strong className="font-mono text-slate-100 ml-1">{items.length}</strong>
        </span>
        <span className="px-2.5 py-1 rounded-lg border border-amber-500/30 bg-amber-500/10 text-amber-200">
          SLA vencido <strong className="font-mono ml-1">{vencidos}</strong>
        </span>
      </div>

      <form
        onSubmit={onFilter}
        className="rounded-xl border border-slate-800 bg-slate-950/50 p-3 grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2"
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar línea, ID…"
          className="col-span-2 md:col-span-3 xl:col-span-2 bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
        />
        <select
          value={estado}
          onChange={(e) => setEstado(e.target.value)}
          className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
        >
          {ESTADOS.map((e) => (
            <option key={e || "all"} value={e}>
              {e || "Todos los estados"}
            </option>
          ))}
        </select>
        <select
          value={nivel}
          onChange={(e) => setNivel(e.target.value)}
          className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
        >
          {NIVELES.map((n) => (
            <option key={n || "all"} value={n}>
              {n || "Todos los niveles"}
            </option>
          ))}
        </select>
        <select
          value={sla}
          onChange={(e) => setSla(e.target.value)}
          className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
        >
          {SLA_OPTS.map((s) => (
            <option key={s || "all"} value={s}>
              {s || "Todo SLA"}
            </option>
          ))}
        </select>
        <input
          value={categoria}
          onChange={(e) => setCategoria(e.target.value)}
          placeholder="Categoría"
          className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs"
        />
        <label className="flex items-center gap-2 text-xs text-slate-400 px-1">
          <input
            type="checkbox"
            checked={soloAbiertos}
            onChange={(e) => setSoloAbiertos(e.target.checked)}
          />
          Solo abiertos
        </label>
        <button
          type="submit"
          className="col-span-2 md:col-span-1 text-xs py-1.5 rounded-lg border border-cyan-500/30 bg-cyan-500/10 text-cyan-200"
        >
          Aplicar
        </button>
      </form>

      {loading ? (
        <p className="text-sm text-slate-500">Cargando cola…</p>
      ) : !items.length ? (
        <p className="text-sm text-slate-500">Sin tickets con esos filtros.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
          {items.map((t) => (
            <TicketRow
              key={t.id}
              t={t}
              onSelect={onSelect}
              canReassign={canReassign}
              agents={agents}
              onReassign={(id, email) => void onReassign(id, email)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
