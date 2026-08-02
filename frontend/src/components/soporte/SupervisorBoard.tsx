"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { SlaBadge } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api } from "@/lib/api-client";
import type { Ticket, TicketEvent } from "@/lib/types";

type AsignacionTab = "" | "libre" | "asignado";

function isFree(t: Ticket) {
  return !(t.asignado_a || "").trim();
}

function agentKey(email: string) {
  return (email || "").trim().toLowerCase();
}

function matchesAgent(t: Ticket, email: string) {
  const a = agentKey(t.asignado_a || "");
  const e = agentKey(email);
  if (!a || !e) return false;
  return a === e || a.includes(e) || e.includes(a.split("@")[0]);
}

/** Tablero operativo del supervisor: vivo, colas globales, asignación y trazabilidad. */
export function SupervisorBoard() {
  const router = useRouter();
  const { can, isAdmin, tenantSlug, selectTicket } = useApp();
  const slug = isAdmin ? tenantSlug : undefined;

  const [items, setItems] = useState<Ticket[]>([]);
  const [agents, setAgents] = useState<{ email: string; nombre: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<AsignacionTab>("libre");
  const [agentFilter, setAgentFilter] = useState("");
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TicketEvent[]>([]);
  const [detailBusy, setDetailBusy] = useState(false);
  const [assignBusy, setAssignBusy] = useState<string | null>(null);
  const [hint, setHint] = useState("");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  const canBoard = can("tickets.reassign") || can("stats.agents");

  const load = useCallback(async () => {
    try {
      const res = await api.tickets(
        {
          nivel: "N2",
          solo_abiertos: true,
          q: q || undefined,
        },
        slug,
      );
      setItems(res.tickets || []);
      setUpdatedAt(new Date());
    } catch (err) {
      setHint(err instanceof Error ? err.message : "No se pudo cargar la cola");
    } finally {
      setLoading(false);
    }
  }, [q, slug]);

  useEffect(() => {
    if (!canBoard) return;
    setLoading(true);
    void load();
  }, [canBoard, load]);

  useEffect(() => {
    if (!canBoard) return;
    const id = window.setInterval(() => {
      void load();
    }, 5000);
    return () => window.clearInterval(id);
  }, [canBoard, load]);

  useEffect(() => {
    if (!can("tickets.reassign")) return;
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
  }, [can]);

  const loadDetail = useCallback(
    async (ticketId: string) => {
      setDetailBusy(true);
      try {
        const res = await api.ticketDetail(ticketId, slug);
        setTimeline(res.timeline || []);
        setSelectedId(ticketId);
      } catch (err) {
        setHint(err instanceof Error ? err.message : "No se pudo cargar el historial");
      } finally {
        setDetailBusy(false);
      }
    },
    [slug],
  );

  useEffect(() => {
    if (!selectedId) {
      setTimeline([]);
      return;
    }
    void loadDetail(selectedId);
  }, [selectedId, loadDetail]);

  const pendientes = useMemo(
    () => items.filter((t) => isFree(t) && t.estado !== "Cerrado"),
    [items],
  );
  const asignados = useMemo(
    () => items.filter((t) => !isFree(t) && t.estado !== "Cerrado"),
    [items],
  );

  const porAgente = useMemo(() => {
    const map = new Map<string, { email: string; nombre: string; count: number }>();
    for (const a of agents) {
      map.set(agentKey(a.email), { email: a.email, nombre: a.nombre, count: 0 });
    }
    for (const t of asignados) {
      const raw = (t.asignado_a || "").trim();
      if (!raw) continue;
      const key = agentKey(raw);
      const existing = map.get(key);
      if (existing) {
        existing.count += 1;
      } else {
        map.set(key, { email: raw, nombre: raw.split("@")[0] || raw, count: 1 });
      }
    }
    return Array.from(map.values()).sort((a, b) => b.count - a.count || a.nombre.localeCompare(b.nombre));
  }, [agents, asignados]);

  const visible = useMemo(() => {
    let list = items;
    if (tab === "libre") list = list.filter(isFree);
    if (tab === "asignado") list = list.filter((t) => !isFree(t));
    if (agentFilter) list = list.filter((t) => matchesAgent(t, agentFilter));
    return list;
  }, [items, tab, agentFilter]);

  const selected = items.find((t) => t.id === selectedId) || null;

  const onAssign = async (ticketId: string, asignado_a: string) => {
    if (!asignado_a) return;
    setAssignBusy(ticketId);
    setHint("");
    try {
      await api.reassignTicket(ticketId, { asignado_a }, slug);
      setHint(`Ticket ${ticketId} asignado a ${asignado_a}`);
      await load();
      if (selectedId === ticketId) await loadDetail(ticketId);
    } catch (err) {
      setHint(err instanceof Error ? err.message : "No se pudo asignar");
    } finally {
      setAssignBusy(null);
    }
  };

  const onOpenConsole = async (id: string) => {
    await selectTicket(id);
    router.push(`/soporte?ticket=${encodeURIComponent(id)}`);
  };

  if (!canBoard) return null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap justify-between gap-3 items-end">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-widest text-ecolan-brand/80">
            Supervisión N2
          </p>
          <h2 className="text-xl font-semibold text-slate-50">Operación en vivo</h2>
          <p className="text-sm text-slate-400 mt-1 max-w-2xl">
            Pendientes libres, carga por agente y trazabilidad de cada ticket. Asigná casos en
            espera a un agente disponible.
          </p>
        </div>
        <div className="text-right space-y-1">
          <p className="text-[11px] font-mono text-slate-500">
            {updatedAt
              ? `Actualizado ${updatedAt.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`
              : "—"}
            {" · auto 5s"}
          </p>
          <Link
            href="/inbox"
            className="text-xs px-3 py-1.5 rounded-lg border border-slate-600 text-slate-300 hover:bg-slate-800/50 inline-block"
          >
            Ver canal (Bandeja)
          </Link>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        <button
          type="button"
          onClick={() => {
            setTab("libre");
            setAgentFilter("");
          }}
          className={`px-3 py-1.5 rounded-lg border ${
            tab === "libre"
              ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-100"
              : "border-slate-700 text-slate-400 hover:border-slate-500"
          }`}
        >
          Pendientes <strong className="font-mono ml-1">{pendientes.length}</strong>
        </button>
        <button
          type="button"
          onClick={() => setTab("asignado")}
          className={`px-3 py-1.5 rounded-lg border ${
            tab === "asignado"
              ? "border-ecolan-brand/40 bg-ecolan-brand/15 text-slate-100"
              : "border-slate-700 text-slate-400 hover:border-slate-500"
          }`}
        >
          Asignados <strong className="font-mono ml-1">{asignados.length}</strong>
        </button>
        <button
          type="button"
          onClick={() => {
            setTab("");
            setAgentFilter("");
          }}
          className={`px-3 py-1.5 rounded-lg border ${
            tab === ""
              ? "border-ecolan-brand/40 bg-ecolan-brand/15 text-slate-100"
              : "border-slate-700 text-slate-400 hover:border-slate-500"
          }`}
        >
          Todos <strong className="font-mono ml-1">{items.length}</strong>
        </button>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar ID, línea…"
          className="ml-auto bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs min-w-[160px]"
        />
      </div>

      <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
        <p className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2">
          Colas por agente
        </p>
        {!porAgente.length ? (
          <p className="text-xs text-slate-500">Sin agentes / sin tickets asignados.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {porAgente.map((a) => {
              const active = agentKey(agentFilter) === agentKey(a.email);
              return (
                <button
                  key={a.email}
                  type="button"
                  onClick={() => {
                    setAgentFilter(active ? "" : a.email);
                    setTab(active ? "" : "asignado");
                  }}
                  className={`text-left px-2.5 py-1.5 rounded-lg border text-xs transition-colors ${
                    active
                      ? "border-ecolan-brand/50 bg-ecolan-brand/15 text-slate-100"
                      : "border-slate-700/80 text-slate-300 hover:border-slate-500"
                  }`}
                >
                  <span className="font-medium">{a.nombre}</span>
                  <span className="font-mono text-slate-400 ml-2">{a.count}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {hint && (
        <p className="text-xs text-amber-200 border border-amber-500/25 rounded-lg px-3 py-2 bg-amber-500/8">
          {hint}
        </p>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.2fr)_minmax(300px,0.9fr)] gap-4">
        <div className="space-y-2 min-h-0">
          {loading && !items.length ? (
            <p className="text-sm text-slate-500">Cargando operación…</p>
          ) : !visible.length ? (
            <p className="text-sm text-slate-500">
              No hay tickets N2 abiertos con este filtro.
            </p>
          ) : (
            visible.map((t) => {
              const free = isFree(t);
              const active = selectedId === t.id;
              return (
                <div
                  key={t.id}
                  className={`rounded-xl border p-3 transition-colors ${
                    active
                      ? "border-ecolan-brand/40 bg-ecolan-brand/10"
                      : "border-slate-800 bg-slate-950/60 hover:border-slate-600"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => void loadDetail(t.id)}
                    className="w-full text-left"
                  >
                    <div className="flex justify-between gap-2 items-start">
                      <span className="font-mono text-ecolan-brand text-xs">{t.id}</span>
                      <SlaBadge
                        label={t.sla_label}
                        estado={t.estado_sla || t.intelligence?.sla?.estado_sla}
                      />
                    </div>
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {t.nivel && <StatusBadge value={t.nivel} />}
                      <StatusBadge value={t.estado} />
                      {free ? (
                        <span className="px-2 py-0.5 text-[10px] font-mono uppercase rounded border border-emerald-500/40 text-emerald-200 bg-emerald-500/10">
                          Pendiente
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 text-[10px] font-mono uppercase rounded border border-ecolan-brand/40 text-slate-200 bg-ecolan-brand/10">
                          Asignado
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-400 mt-1.5 truncate">
                      {t.linea || "—"} · {t.categoria || "General"}
                      {t.asignado_a ? ` · ${t.asignado_a}` : ""}
                    </p>
                    {t.descripcion_falla && (
                      <p className="text-[11px] text-slate-500 mt-1 line-clamp-2">
                        {t.descripcion_falla}
                      </p>
                    )}
                  </button>
                  <div className="mt-2 flex flex-wrap gap-2 items-center">
                    {can("tickets.reassign") && agents.length > 0 && (
                      <select
                        value={t.asignado_a || ""}
                        disabled={assignBusy === t.id}
                        onChange={(e) => {
                          if (e.target.value) void onAssign(t.id, e.target.value);
                        }}
                        className="flex-1 min-w-[140px] bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-[11px] text-slate-300 disabled:opacity-50"
                      >
                        <option value="">
                          {free ? "Asignar a agente…" : "Reasignar…"}
                        </option>
                        {agents.map((a) => (
                          <option key={a.email} value={a.email}>
                            {a.nombre} ({a.email})
                          </option>
                        ))}
                      </select>
                    )}
                    <button
                      type="button"
                      onClick={() => void onOpenConsole(t.id)}
                      className="text-[11px] px-2.5 py-1 rounded-lg border border-ecolan-brand/40 text-ecolan-brand hover:bg-ecolan-brand/10"
                    >
                      Abrir
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-4 min-h-[320px] sticky top-2 self-start">
          {!selectedId || !selected ? (
            <div className="h-full flex flex-col justify-center text-center gap-2 py-10">
              <p className="text-sm text-slate-300">Historial del ticket</p>
              <p className="text-xs text-slate-500 max-w-xs mx-auto leading-relaxed">
                Seleccioná un ticket N2 para ver la trazabilidad completa: creación, bot,
                asignaciones, notas y cierre.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex justify-between gap-2 items-start">
                <div>
                  <p className="font-mono text-ecolan-brand text-sm">{selected.id}</p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    {selected.linea || "—"} · {selected.categoria || "General"}
                  </p>
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {selected.nivel && <StatusBadge value={selected.nivel} />}
                    <StatusBadge value={selected.estado} />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => void onOpenConsole(selected.id)}
                  className="text-[11px] px-2.5 py-1 rounded-lg border border-ecolan-brand/40 text-ecolan-brand shrink-0"
                >
                  Consola
                </button>
              </div>
              {selected.asignado_a ? (
                <p className="text-xs text-slate-200">
                  Asignado a <span className="font-mono">{selected.asignado_a}</span>
                </p>
              ) : (
                <p className="text-xs text-emerald-200">Sin asignar — esperando agente</p>
              )}
              {selected.descripcion_falla && (
                <p className="text-xs text-slate-400 leading-relaxed border-t border-slate-800 pt-2">
                  {selected.descripcion_falla}
                </p>
              )}
              <div className="border-t border-slate-800 pt-3">
                <p className="text-[10px] font-mono uppercase tracking-wider text-slate-500 mb-2">
                  Trazabilidad
                </p>
                {detailBusy && !timeline.length ? (
                  <p className="text-xs text-slate-500">Cargando historial…</p>
                ) : !timeline.length ? (
                  <p className="text-xs text-slate-500">Sin eventos registrados.</p>
                ) : (
                  <div className="space-y-3 max-h-[480px] overflow-y-auto pr-1">
                    {timeline.map((ev) => (
                      <div
                        key={ev.id}
                        className={`pl-3 border-l ${
                          ev.visible_cliente === "No"
                            ? "border-ecolan-brand/40"
                            : "border-ecolan-brand/30"
                        }`}
                      >
                        <div className="flex justify-between gap-2">
                          <p className="text-xs text-slate-200 font-medium">{ev.titulo}</p>
                          {ev.visible_cliente === "No" && (
                            <span className="text-[9px] font-mono text-ecolan-brand uppercase shrink-0">
                              interno
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] text-slate-500 font-mono mt-0.5">
                          {ev.tipo}
                          {ev.estado ? ` · ${ev.estado}` : ""}
                          {ev.actor ? ` · ${ev.actor}` : ""}
                          {ev.created_at
                            ? ` · ${ev.created_at.slice(0, 16).replace("T", " ")}`
                            : ""}
                        </p>
                        {ev.detalle && (
                          <p className="text-[11px] text-slate-400 mt-1 leading-relaxed whitespace-pre-wrap">
                            {ev.detalle}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
