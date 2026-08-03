"use client";

import { useCallback, useEffect, useState } from "react";
import { useApp } from "@/contexts/AppContext";
import { api } from "@/lib/api-client";
import type { KBContribution } from "@/lib/types";
import { GlassCard, KpiCard } from "@/components/ui/GlassCard";
import { inputCls } from "@/components/ui/forms";

function formatDate(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es-AR", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso.slice(0, 16);
  }
}

function EstadoPill({ estado }: { estado: string }) {
  const map: Record<string, string> = {
    pendiente: "border-amber-500/40 text-amber-300 bg-amber-500/10",
    aprobada: "border-emerald-500/40 text-emerald-300 bg-emerald-500/10",
    rechazada: "border-red-500/40 text-red-300 bg-red-500/10",
  };
  return (
    <span
      className={`px-2 py-0.5 text-[10px] font-mono uppercase rounded border ${
        map[estado] || "border-slate-600 text-slate-400"
      }`}
    >
      {estado}
    </span>
  );
}

export function KbReviewTray() {
  const { isAdmin, tenantSlug, setTenant, refreshData, appendTrace } = useApp();
  const [items, setItems] = useState<KBContribution[]>([]);
  const [filtro, setFiltro] = useState<"pendiente" | "todas" | "aprobada" | "rechazada">(
    "pendiente",
  );
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<KBContribution | null>(null);
  const [titulo, setTitulo] = useState("");
  const [categoria, setCategoria] = useState("");
  const [contenido, setContenido] = useState("");
  const [motivo, setMotivo] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(async () => {
    if (!isAdmin) return;
    setLoading(true);
    try {
      const res = await api.kbContributions({ estado: filtro }, tenantSlug);
      setItems(res.contribuciones || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [isAdmin, filtro, tenantSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  const openReview = (c: KBContribution) => {
    setSelected(c);
    setTitulo(c.titulo);
    setCategoria(c.categoria);
    setContenido(c.contenido);
    setMotivo("");
    setMessage("");
  };

  const onApprove = async () => {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      const targetSlug =
        selected.organizacion_slug ||
        undefined;
      const res = await api.approveKbContribution(
        selected.id,
        {
          titulo: titulo.trim() || undefined,
          categoria: categoria.trim() || undefined,
          contenido: contenido.trim() || undefined,
          motivo_revision: motivo.trim() || "Aprobada por administrador",
        },
        tenantSlug,
      );
      const pubSlug =
        res.articulo.organizacion_slug || targetSlug || tenantSlug;
      const pubName =
        res.articulo.organizacion_nombre ||
        selected.organizacion_nombre ||
        pubSlug ||
        "la cooperativa";
      appendTrace([`✅ KB aprobada: ${res.articulo.titulo} → ${pubName}`]);
      // La biblioteca se filtra por tenant: cambiar a la org donde quedó el artículo
      if (pubSlug && pubSlug !== tenantSlug) {
        await setTenant(pubSlug);
      } else {
        await refreshData();
      }
      setMessage(
        `Aprobada e incorporada a la KB de ${pubName}. Ya debería verse en la biblioteca abajo.`,
      );
      setSelected(null);
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "No se pudo aprobar");
    } finally {
      setBusy(false);
    }
  };

  const onReject = async () => {
    if (!selected) return;
    setBusy(true);
    setMessage("");
    try {
      await api.rejectKbContribution(
        selected.id,
        { motivo_revision: motivo.trim() || "Rechazada por administrador" },
        tenantSlug,
      );
      appendTrace([`⛔ Propuesta KB rechazada: ${selected.titulo}`]);
      setMessage("Propuesta rechazada.");
      setSelected(null);
      await load();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "No se pudo rechazar");
    } finally {
      setBusy(false);
    }
  };

  if (!isAdmin) return null;

  const pendientes = filtro === "pendiente" ? items.length : items.filter((i) => i.estado === "pendiente").length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-100">Bandeja de revisión KB</h3>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Aportes de cierres N1/N2 y agentes · solo el admin publica a la KB
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(["pendiente", "aprobada", "rechazada", "todas"] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFiltro(f)}
              className={`px-2.5 py-1 text-[10px] font-mono uppercase rounded border ${
                filtro === f
                  ? "border-ecolan-brand/40 text-ecolan-brand bg-ecolan-brand/10"
                  : "border-slate-700 text-slate-500 hover:text-slate-300"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <KpiCard label="En bandeja" value={items.length} tone="cyan" />
        <KpiCard
          label="Pendientes"
          value={pendientes}
          tone={pendientes ? "amber" : "emerald"}
        />
        <KpiCard
          label="Filtro"
          value={filtro}
          tone="violet"
          helper="Estado de revisión"
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_1.1fr] gap-3">
        <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3 max-h-[420px] overflow-y-auto space-y-2">
          {loading ? (
            <p className="text-xs text-slate-500 font-mono">Cargando propuestas…</p>
          ) : !items.length ? (
            <p className="text-xs text-slate-500">
              No hay contribuciones en este filtro.
            </p>
          ) : (
            items.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => openReview(c)}
                className={`w-full text-left p-3 rounded-lg border transition-colors ${
                  selected?.id === c.id
                    ? "border-ecolan-brand/40 bg-ecolan-brand/5"
                    : "border-slate-800 bg-slate-900/60 hover:border-slate-600"
                }`}
              >
                <div className="flex justify-between gap-2 items-start">
                  <p className="text-sm text-slate-100 font-medium line-clamp-2">{c.titulo}</p>
                  <EstadoPill estado={c.estado} />
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  {c.organizacion_nombre || c.organizacion_slug
                    ? `${c.organizacion_nombre || c.organizacion_slug} · `
                    : ""}
                  {c.categoria}
                  {c.nivel_ticket ? ` · ${c.nivel_ticket}` : ""}
                  {c.ticket_id ? ` · ${c.ticket_id}` : ""}
                </p>
                <p className="text-[10px] text-slate-600 mt-1">
                  {c.origen} · {c.propuesto_por || "sistema"} · {formatDate(c.created_at)}
                </p>
              </button>
            ))
          )}
        </div>

        <GlassCard
          title={selected ? "Revisar propuesta" : "Detalle"}
          variant="secondary"
          className="min-h-[280px]"
        >
          {!selected ? (
            <p className="text-xs text-slate-500">
              Seleccioná una propuesta para aprobarla (entra a KB) o rechazarla.
            </p>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-2 text-[10px] font-mono text-slate-500">
                <EstadoPill estado={selected.estado} />
                <span>{selected.origen}</span>
                {selected.ticket_id && <span>{selected.ticket_id}</span>}
              </div>
              {selected.estado === "pendiente" ? (
                <>
                  <input
                    className={inputCls}
                    value={titulo}
                    onChange={(e) => setTitulo(e.target.value)}
                    placeholder="Título"
                  />
                  <input
                    className={inputCls}
                    value={categoria}
                    onChange={(e) => setCategoria(e.target.value)}
                    placeholder="Categoría"
                  />
                  <textarea
                    className={`${inputCls} min-h-[140px] resize-y`}
                    value={contenido}
                    onChange={(e) => setContenido(e.target.value)}
                    placeholder="Contenido del artículo"
                  />
                  <textarea
                    className={`${inputCls} min-h-[60px] resize-y`}
                    value={motivo}
                    onChange={(e) => setMotivo(e.target.value)}
                    placeholder="Nota de revisión (opcional en aprobación; recomendada al rechazar)"
                  />
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={onApprove}
                      className="flex-1 min-w-[120px] py-2 rounded-lg text-sm font-semibold text-white bg-ecolan-brand hover:bg-ecolan-brand-dark disabled:opacity-50 shadow-sm transition-all duration-200 ease-in-out"
                    >
                      {busy ? "…" : "Aprobar → KB"}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={onReject}
                      className="flex-1 min-w-[120px] py-2 rounded-lg text-sm border border-red-500/40 text-red-300 hover:bg-red-500/10 disabled:opacity-50"
                    >
                      Rechazar
                    </button>
                  </div>
                </>
              ) : (
                <div className="space-y-2">
                  <p className="text-sm text-slate-200 font-medium">{selected.titulo}</p>
                  <pre className="text-[11px] text-slate-400 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
                    {selected.contenido}
                  </pre>
                  {selected.motivo_revision && (
                    <p className="text-[11px] text-slate-500 border-t border-slate-800 pt-2">
                      Revisión: {selected.motivo_revision}
                    </p>
                  )}
                  {selected.articulo_id && (
                    <p className="text-[10px] font-mono text-emerald-400/80">
                      Artículo: {selected.articulo_id}
                    </p>
                  )}
                </div>
              )}
              {message && (
                <p className="text-[11px] text-ecolan-brand/90">{message}</p>
              )}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}
