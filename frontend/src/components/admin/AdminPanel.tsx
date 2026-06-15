"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type { AdminUser, ImportCsvResult, Organization } from "@/lib/types";
import { KpiCard } from "@/components/ui/GlassCard";

const CSV_EJEMPLO = `nombre,email,telefono,rol,linea_principal
Operador Batán 1,operador1@coopbatan.com,2235551001,cliente,2235551234
Operador Batán 2,operador2@coopbatan.com,2235551002,cliente,2235555678`;

export function AdminPanel() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedSlug, setSelectedSlug] = useState("");
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [importResult, setImportResult] = useState<ImportCsvResult | null>(null);

  const [newOrg, setNewOrg] = useState({
    nombre: "",
    slug: "",
    logo_label: "C",
    brand_color: "#34d399",
  });

  const [newUser, setNewUser] = useState({
    nombre: "",
    email: "",
    password: "cliente",
    rol: "cliente",
    telefono: "",
    linea_principal: "",
  });

  const cooperativas = orgs.filter((o) => !o.es_plataforma && o.slug !== "imowi");

  const loadOrgs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.adminOrganizations();
      setOrgs(data.organizaciones);
      if (!selectedSlug) {
        const first = data.organizaciones.find((o) => o.slug !== "imowi");
        if (first) setSelectedSlug(first.slug);
      }
    } finally {
      setLoading(false);
    }
  }, [selectedSlug]);

  const loadUsers = useCallback(async (slug: string) => {
    if (!slug) return;
    const data = await api.adminUsers(slug);
    setUsers(data.usuarios);
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadOrgs);
  }, [loadOrgs]);

  useEffect(() => {
    if (selectedSlug) void Promise.resolve().then(() => loadUsers(selectedSlug));
  }, [selectedSlug, loadUsers]);

  const onCreateOrg = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const created = await api.createOrganization({
        nombre: newOrg.nombre,
        slug: newOrg.slug || undefined,
        logo_label: newOrg.logo_label,
        brand_color: newOrg.brand_color,
      });
      setNewOrg({ nombre: "", slug: "", logo_label: "C", brand_color: "#34d399" });
      setSelectedSlug(created.organizacion.slug);
      setMessage("Cooperativa creada. Ahora podés cargar su primera credencial abajo.");
      await loadOrgs();
      await loadUsers(created.organizacion.slug);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Error al crear cooperativa");
    } finally {
      setBusy(false);
    }
  };

  const onCreateUser = async (e: FormEvent) => {
    e.preventDefault();
    if (!selectedSlug) return;
    setBusy(true);
    setMessage("");
    try {
      await api.createAdminUser(selectedSlug, newUser);
      setNewUser({
        nombre: "",
        email: "",
        password: "cliente",
        rol: "cliente",
        telefono: "",
        linea_principal: "",
      });
      setMessage("Usuario creado.");
      await loadUsers(selectedSlug);
      await loadOrgs();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Error al crear usuario");
    } finally {
      setBusy(false);
    }
  };

  const onImportCsv = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedSlug) return;
    const input = e.currentTarget.elements.namedItem("csvfile") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      setMessage("Seleccioná un archivo CSV.");
      return;
    }
    setBusy(true);
    setMessage("");
    setImportResult(null);
    try {
      const result = await api.importUsersCsv(selectedSlug, file);
      setImportResult(result);
      setMessage(
        `Importación: ${result.creados} creados, ${result.actualizados} actualizados, ${result.lineas_creadas} líneas.`,
      );
      input.value = "";
      await loadUsers(selectedSlug);
      await loadOrgs();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Error al importar CSV");
    } finally {
      setBusy(false);
    }
  };

  const selectedOrg = orgs.find((o) => o.slug === selectedSlug);

  return (
    <div className="p-4 space-y-6 overflow-y-auto">
      <div>
        <h2 className="font-semibold text-slate-100">Administración</h2>
        <p className="text-[10px] font-mono text-slate-500">
          Cooperativas · usuarios · importación CSV piloto
        </p>
      </div>

      {message && (
        <p className="text-sm text-cyan-300/90 border border-cyan-500/20 rounded-lg px-3 py-2 bg-cyan-500/5">
          {message}
        </p>
      )}

      {loading ? (
        <p className="text-slate-500">Cargando…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KpiCard label="Cooperativas" value={cooperativas.length} />
            <KpiCard
              label="Usuarios totales"
              value={cooperativas.reduce((a, o) => a + (o.usuarios || 0), 0)}
            />
            <KpiCard
              label="Tickets abiertos"
              value={cooperativas.reduce((a, o) => a + (o.tickets_abiertos || 0), 0)}
            />
            <KpiCard
              label="Líneas JSC demo"
              value={cooperativas.reduce((a, o) => a + (o.lineas || 0), 0)}
            />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
              <h3 className="text-xs font-mono uppercase text-slate-500">Alta cooperativa</h3>
              <form onSubmit={onCreateOrg} className="space-y-2">
                <input
                  required
                  placeholder="Nombre (ej. Cooperativa Lincoln)"
                  value={newOrg.nombre}
                  onChange={(e) => setNewOrg({ ...newOrg, nombre: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm"
                />
                <input
                  placeholder="Slug opcional (ej. coop-lincoln)"
                  value={newOrg.slug}
                  onChange={(e) => setNewOrg({ ...newOrg, slug: e.target.value })}
                  className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm font-mono"
                />
                <div className="flex gap-2">
                  <input
                    placeholder="Logo"
                    maxLength={8}
                    value={newOrg.logo_label}
                    onChange={(e) => setNewOrg({ ...newOrg, logo_label: e.target.value })}
                    className="w-20 bg-slate-950 border border-slate-700 rounded px-2 py-2 text-sm text-center"
                  />
                  <input
                    type="color"
                    value={newOrg.brand_color}
                    onChange={(e) => setNewOrg({ ...newOrg, brand_color: e.target.value })}
                    className="h-10 w-14 rounded border border-slate-700 bg-slate-950"
                  />
                </div>
                <button
                  type="submit"
                  disabled={busy}
                  className="text-xs px-4 py-2 rounded border border-emerald-500/30 text-emerald-300 disabled:opacity-50"
                >
                  Crear cooperativa
                </button>
              </form>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
              <h3 className="text-xs font-mono uppercase text-slate-500">Cooperativas activas</h3>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {cooperativas.map((o) => (
                  <button
                    key={o.slug}
                    type="button"
                    onClick={() => setSelectedSlug(o.slug)}
                    className={`w-full text-left p-3 rounded-xl border transition-colors ${
                      selectedSlug === o.slug
                        ? "border-cyan-500/40 bg-cyan-500/5"
                        : "border-slate-800 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-bold"
                        style={{ backgroundColor: `${o.brand_color}22`, color: o.brand_color }}
                      >
                        {o.logo_label}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-slate-200 truncate">{o.nombre}</p>
                        <p className="text-[10px] font-mono text-slate-500">{o.slug}</p>
                      </div>
                      <div className="text-[10px] font-mono text-slate-500 text-right">
                        <div>{o.usuarios ?? 0} usr</div>
                        <div>{o.tickets_abiertos ?? 0} abiertos</div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {selectedOrg && (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
                <h3 className="text-xs font-mono uppercase text-slate-500">
                  Credenciales — {selectedOrg.nombre}
                </h3>
                <p className="text-xs text-slate-500">
                  El email y la clave inicial que cargues acá son las credenciales de acceso
                  para esa cooperativa.
                </p>
                <form onSubmit={onCreateUser} className="space-y-2">
                  <input
                    required
                    placeholder="Nombre"
                    value={newUser.nombre}
                    onChange={(e) => setNewUser({ ...newUser, nombre: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm"
                  />
                  <input
                    required
                    type="email"
                    placeholder="Email"
                    value={newUser.email}
                    onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm"
                  />
                  <div className="flex gap-2">
                    <input
                      placeholder="Teléfono"
                      value={newUser.telefono}
                      onChange={(e) => setNewUser({ ...newUser, telefono: e.target.value })}
                      className="flex-1 bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm"
                    />
                    <input
                      placeholder="Línea principal"
                      value={newUser.linea_principal}
                      onChange={(e) =>
                        setNewUser({ ...newUser, linea_principal: e.target.value })
                      }
                      className="flex-1 bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm font-mono"
                    />
                  </div>
                  <div className="flex gap-2">
                    <select
                      value={newUser.rol}
                      onChange={(e) => setNewUser({ ...newUser, rol: e.target.value })}
                      className="bg-slate-950 border border-slate-700 rounded px-2 py-2 text-sm"
                    >
                      <option value="cliente">Operador (cliente)</option>
                      <option value="ingeniero_noc">Ingeniero NOC</option>
                    </select>
                    <input
                      placeholder="Clave inicial"
                      value={newUser.password}
                      onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                      className="flex-1 bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm font-mono"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={busy}
                    className="text-xs px-4 py-2 rounded border border-cyan-500/30 text-cyan-300 disabled:opacity-50"
                  >
                    Agregar usuario
                  </button>
                </form>

                <div className="max-h-48 overflow-y-auto border-t border-slate-800 pt-3 space-y-1">
                  {users.length === 0 ? (
                    <p className="text-xs text-slate-600">Sin usuarios en esta cooperativa.</p>
                  ) : (
                    users.map((u) => (
                      <div
                        key={u.id}
                        className="flex justify-between gap-2 text-xs py-1.5 border-b border-slate-800/60"
                      >
                        <div className="min-w-0">
                          <p className="text-slate-300 truncate">{u.nombre}</p>
                          <p className="font-mono text-slate-500 truncate">{u.email}</p>
                        </div>
                        <span className="text-slate-500 shrink-0">{u.rol}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 space-y-3">
                <h3 className="text-xs font-mono uppercase text-slate-500">Importar CSV</h3>
                <p className="text-xs text-slate-500">
                  Columnas: nombre, email, telefono, rol, linea_principal (opcional abonado, plan).
                  Clave por defecto: <span className="font-mono text-slate-400">cliente</span>
                </p>
                <pre className="text-[10px] font-mono text-slate-600 bg-slate-950/80 p-2 rounded overflow-x-auto">
                  {CSV_EJEMPLO}
                </pre>
                <form onSubmit={onImportCsv} className="flex flex-wrap gap-2 items-center">
                  <input
                    name="csvfile"
                    type="file"
                    accept=".csv,text/csv"
                    className="text-xs text-slate-400 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:bg-slate-800 file:text-slate-300"
                  />
                  <button
                    type="submit"
                    disabled={busy}
                    className="text-xs px-4 py-2 rounded border border-violet-500/30 text-violet-300 disabled:opacity-50"
                  >
                    Importar
                  </button>
                </form>
                {importResult && importResult.errores.length > 0 && (
                  <div className="text-xs text-amber-400/90 space-y-1 max-h-32 overflow-y-auto">
                    {importResult.errores.map((err) => (
                      <p key={err}>{err}</p>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
