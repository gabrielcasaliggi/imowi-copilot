"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api-client";
import type { NasCatalogItem, NasHealth, NetworkOutage } from "@/lib/types";
import { useApp } from "@/contexts/AppContext";
import { Button, TextAreaField, TextField, inputCls } from "@/components/ui/forms";
import { useToast } from "@/components/ui/Toast";

const TIPOS = [
  { id: "DOWN", label: "Caída / DOWN" },
  { id: "FALLA_ELECTRICA", label: "Falla eléctrica" },
  { id: "FIBRA", label: "Fibra" },
  { id: "OTRO", label: "Otro" },
];

export function IncidentesMasivosPanel() {
  const { tenantSlug, can } = useApp();
  const { push: toast } = useToast();
  const allowed = can("outages.manage");

  const [nasList, setNasList] = useState<NasCatalogItem[]>([]);
  const [outages, setOutages] = useState<NetworkOutage[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState("");
  const [health, setHealth] = useState<NasHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [alcance, setAlcance] = useState<"total" | "parcial">("total");
  const [tipo, setTipo] = useState("DOWN");
  const [eta, setEta] = useState(45);
  const [etaValidada, setEtaValidada] = useState(false);
  const [comentario, setComentario] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!allowed) return;
    setLoading(true);
    setError("");
    try {
      const [nasRes, outRes] = await Promise.all([
        api.listNas(tenantSlug),
        api.listOutages(tenantSlug, "activo"),
      ]);
      setNasList(nasRes.data || []);
      setOutages(outRes.data || []);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "No se pudo cargar";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [allowed, tenantSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredNas = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return nasList;
    return nasList.filter(
      (n) =>
        n.shortname.toLowerCase().includes(q) ||
        (n.nasname || "").toLowerCase().includes(q),
    );
  }, [filter, nasList]);

  const selectedNas = nasList.find((n) => n.shortname === selected) || null;

  useEffect(() => {
    if (!selected) {
      setHealth(null);
      return;
    }
    let cancelled = false;
    setHealthLoading(true);
    api
      .nasHealth(selected, tenantSlug)
      .then((h) => {
        if (cancelled) return;
        setHealth(h);
        const sug = h.alcance_sugerido === "parcial" ? "parcial" : "total";
        setAlcance(sug);
      })
      .catch(() => {
        if (!cancelled) {
          setHealth({
            shortname: selected,
            reachable: false,
            error: "No se pudo chequear",
            alcance_sugerido: "total",
            resources: {},
          });
          setAlcance("total");
        }
      })
      .finally(() => {
        if (!cancelled) setHealthLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selected, tenantSlug]);

  async function declarar() {
    if (!selectedNas) {
      toast("Elegí un NAS", "danger");
      return;
    }
    if (!comentario.trim()) {
      toast("El comentario es obligatorio", "danger");
      return;
    }
    setSaving(true);
    try {
      await api.createOutage(
        {
          nas_shortname: selectedNas.shortname,
          nas_ip: selectedNas.nasname || selectedNas.ip || "",
          alcance,
          tipo,
          comentario: comentario.trim(),
          eta_minutos: eta,
          eta_validada: etaValidada,
        },
        tenantSlug,
      );
      toast("Incidente declarado", "success");
      setComentario("");
      setSelected("");
      setHealth(null);
      await load();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Error al declarar", "danger");
    } finally {
      setSaving(false);
    }
  }

  async function resolver(id: string) {
    setSaving(true);
    try {
      await api.resolveOutage(id, tenantSlug);
      toast("Incidente resuelto", "success");
      await load();
    } catch (e) {
      toast(e instanceof ApiError ? e.message : "Error al resolver", "danger");
    } finally {
      setSaving(false);
    }
  }

  if (!allowed) {
    return (
      <div className="p-6 text-sm text-slate-400">
        No tenés permiso para gestionar incidentes masivos.
      </div>
    );
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-4 md:p-6 space-y-6">
      <header className="space-y-1">
        <h1 className="text-xl font-semibold text-slate-100">Incidentes masivos</h1>
        <p className="text-sm text-slate-400 max-w-2xl">
          Declará un NAS con problema. El bot avisará a los abonados de ese nodo cuando escriban,
          sin crear reclamos duplicados. Usá el comentario para explicar si es total o una rama/área.
        </p>
      </header>

      {error && (
        <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      <section className="rounded-2xl border border-slate-700/80 bg-slate-900/40 p-4 md:p-5 space-y-4">
        <h2 className="text-sm font-medium text-slate-200">Anunciar incidente</h2>

        <div className="grid gap-3 md:grid-cols-2">
          <label className="block space-y-1.5">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-500">
              Buscar NAS (Radius)
            </span>
            <TextField
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="shortname o IP…"
              disabled={loading}
            />
          </label>
          <label className="block space-y-1.5">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-500">
              NAS seleccionado
            </span>
            <select
              className={inputCls}
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              disabled={loading || !filteredNas.length}
            >
              <option value="">Elegí un NAS…</option>
              {filteredNas.map((n) => (
                <option key={n.shortname} value={n.shortname}>
                  {n.shortname} — {n.nasname || n.ip || "sin IP"}
                </option>
              ))}
            </select>
          </label>
        </div>

        {selected && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {healthLoading ? (
              <span className="text-slate-500">Chequeando MikroTik…</span>
            ) : health?.reachable ? (
              <span className="px-2 py-1 rounded-lg border border-emerald-500/40 text-emerald-300 bg-emerald-500/10">
                NAS alcanzable → sugerido: fallo de área/parcial
              </span>
            ) : (
              <span className="px-2 py-1 rounded-lg border border-amber-500/40 text-amber-200 bg-amber-500/10">
                Sin respuesta del NAS → sugerido: caída total
                {health?.error ? ` (${health.error})` : ""}
              </span>
            )}
          </div>
        )}

        <div className="grid gap-3 md:grid-cols-3">
          <label className="block space-y-1.5">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-500">
              Alcance
            </span>
            <select
              className={inputCls}
              value={alcance}
              onChange={(e) => setAlcance(e.target.value as "total" | "parcial")}
            >
              <option value="total">Total del NAS</option>
              <option value="parcial">Parcial / área / rama</option>
            </select>
          </label>
          <label className="block space-y-1.5">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-500">
              Tipo
            </span>
            <select className={inputCls} value={tipo} onChange={(e) => setTipo(e.target.value)}>
              {TIPOS.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1.5">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-500">
              ETA (min)
            </span>
            <TextField
              type="number"
              min={1}
              max={1440}
              value={eta}
              onChange={(e) => setEta(Number(e.target.value) || 45)}
            />
          </label>
        </div>

        <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer w-fit">
          <input
            type="checkbox"
            className="rounded border-slate-600 bg-slate-800 text-teal-500 focus:ring-teal-500/40"
            checked={etaValidada}
            onChange={(e) => setEtaValidada(e.target.checked)}
          />
          ETA confirmada por operaciones (si no, el bot no la comunica al cliente)
        </label>

        <label className="block space-y-1.5">
          <span className="text-xs font-mono uppercase tracking-wider text-slate-500">
            Comentario para el bot (obligatorio)
          </span>
          <TextAreaField
            rows={4}
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
            placeholder="Ej: Rama de fibra caída en calle San Martín; afecta NAP zona escuela. Guardia en camino."
          />
        </label>

        <div className="flex flex-wrap gap-2">
          <Button variant="primary" disabled={saving || loading} onClick={() => void declarar()}>
            {saving ? "Guardando…" : "Declarar incidente"}
          </Button>
          <Button variant="secondary" disabled={loading || saving} onClick={() => void load()}>
            Actualizar
          </Button>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-slate-200">
          Activos ({outages.length})
        </h2>
        {!outages.length && !loading && (
          <p className="text-sm text-slate-500">No hay incidentes masivos activos.</p>
        )}
        <ul className="space-y-3">
          {outages.map((o) => (
            <li
              key={o.id}
              className="rounded-2xl border border-slate-700/80 bg-slate-900/40 p-4 space-y-2"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium text-slate-100">
                    {o.nas_shortname}{" "}
                    <span className="text-slate-500 font-normal text-sm">
                      {o.nas_ip ? `· ${o.nas_ip}` : ""}
                    </span>
                  </p>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {o.alcance} · {o.tipo} · ETA{" "}
                    {o.eta_validada === "No" ? "sin confirmar" : `${o.eta_minutos} min`}
                    {o.validado_a ? ` · validado ${o.validado_a}` : ""} ·{" "}
                    {o.created_by || "—"}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="success"
                  disabled={saving}
                  onClick={() => void resolver(o.id)}
                >
                  Resolver
                </Button>
              </div>
              {o.comentario && (
                <p className="text-sm text-slate-300">
                  <span className="text-slate-500">Comentario: </span>
                  {o.comentario}
                </p>
              )}
              {o.mensaje_cliente && (
                <p className="text-xs text-slate-400 border-t border-slate-800 pt-2">
                  <span className="text-slate-500">Mensaje al cliente: </span>
                  {o.mensaje_cliente}
                </p>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
