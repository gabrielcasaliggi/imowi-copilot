"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type { AdminUser, AuditEvent, Organization } from "@/lib/types";
import {
  GlassCard,
  KpiCard,
  SectionHeader,
  SidebarSection,
  StatusPill,
} from "@/components/ui/GlassCard";
import { PlatformSettingsPanel } from "@/components/admin/PlatformSettingsPanel";

const inputCls =
  "w-full bg-slate-950 border border-slate-700/80 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500/40";

type HubTab = "cooperativas" | "seguridad" | "config" | "roles";

export function AdminPanel() {
  const [hubTab, setHubTab] = useState<HubTab>("cooperativas");
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [selectedSlug, setSelectedSlug] = useState("");
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [loginEvents, setLoginEvents] = useState<
    { actor: string; ok: boolean; reason: string; ip: string; created_at: string | null }[]
  >([]);
  const [invites, setInvites] = useState<
    { email: string; rol: string; pendiente: boolean; expires_at: string | null }[]
  >([]);
  const [inviteForm, setInviteForm] = useState({ email: "", nombre: "", rol: "agente" });
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [showDelete, setShowDelete] = useState(false);
  const [rbacRoles, setRbacRoles] = useState<
    { codigo: string; nombre: string; descripcion: string; permisos: string[] }[]
  >([]);
  const [rbacPerms, setRbacPerms] = useState<
    { codigo: string; dominio: string; descripcion: string }[]
  >([]);

  const [newOrg, setNewOrg] = useState({
    nombre: "",
    slug: "",
    logo_label: "C",
    brand_color: "#34d399",
  });

  const cooperativas = orgs.filter((o) => !o.es_plataforma && o.slug !== "imowi");
  const selectedOrg = orgs.find((o) => o.slug === selectedSlug);
  const totalUsuarios = cooperativas.reduce((a, o) => a + (o.usuarios || 0), 0);
  const totalAbiertos = cooperativas.reduce((a, o) => a + (o.tickets_abiertos || 0), 0);

  const loadOrgs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.adminOrganizations();
      setOrgs(data.organizaciones);
      setSelectedSlug((prev) => {
        if (prev && data.organizaciones.some((o) => o.slug === prev)) return prev;
        const first = data.organizaciones.find((o) => o.slug !== "imowi");
        return first?.slug || "";
      });
    } finally {
      setLoading(false);
    }
  }, []);

  const loadUsers = useCallback(async (slug: string) => {
    if (!slug) {
      setUsers([]);
      return;
    }
    const data = await api.adminUsers(slug);
    setUsers(data.usuarios);
  }, []);

  const loadInvites = useCallback(async (slug: string) => {
    if (!slug) {
      setInvites([]);
      return;
    }
    try {
      const d = await api.listInvites(slug);
      setInvites(d.invites);
    } catch {
      setInvites([]);
    }
  }, []);

  useEffect(() => {
    void loadOrgs();
  }, [loadOrgs]);

  useEffect(() => {
    if (!selectedSlug) return;
    void loadUsers(selectedSlug);
    void loadInvites(selectedSlug);
    setShowDelete(false);
    setDeleteConfirm("");
  }, [selectedSlug, loadUsers, loadInvites]);

  useEffect(() => {
    void api.adminAudit(20).then((d) => setAuditEvents(d.eventos)).catch(() => setAuditEvents([]));
  }, [message]);

  useEffect(() => {
    if (hubTab === "roles") {
      void Promise.all([api.rbacRoles(), api.rbacPermissions()]).then(([roles, perms]) => {
        setRbacRoles(roles.roles);
        setRbacPerms(perms.permisos);
      });
    }
    if (hubTab === "seguridad") {
      void api
        .loginEvents("console", 50)
        .then((d) => setLoginEvents(d.eventos))
        .catch(() => setLoginEvents([]));
    }
  }, [hubTab]);

  const tabBtn = (id: HubTab, label: string) => (
    <button
      key={id}
      type="button"
      onClick={() => setHubTab(id)}
      className={`px-3 py-1.5 rounded-lg text-sm border transition ${
        hubTab === id
          ? "border-cyan-500/50 bg-cyan-500/15 text-cyan-100"
          : "border-slate-700/80 text-slate-400 hover:border-slate-500"
      }`}
    >
      {label}
    </button>
  );

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
      setMessage(`Cooperativa creada: ${created.organizacion.nombre}`);
      await loadOrgs();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Error al crear cooperativa");
    } finally {
      setBusy(false);
    }
  };

  const onDeleteOrg = async () => {
    if (!selectedSlug || deleteConfirm !== selectedSlug) return;
    setBusy(true);
    setMessage("");
    try {
      const res = await api.deleteOrganization(selectedSlug);
      setMessage(
        `Eliminada ${res.eliminada.nombre}: ${res.eliminada.usuarios} usuarios, ${res.eliminada.tickets} tickets`,
      );
      setShowDelete(false);
      setDeleteConfirm("");
      setSelectedSlug("");
      await loadOrgs();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Error al eliminar");
    } finally {
      setBusy(false);
    }
  };

  const onToggleUserActive = async (user: AdminUser) => {
    if (!selectedSlug) return;
    setBusy(true);
    try {
      await api.updateAdminUser(selectedSlug, user.id, { activo: !(user.activo !== false) });
      await loadUsers(selectedSlug);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Error al actualizar usuario");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="admin-hub-page p-4 space-y-5 overflow-y-auto min-h-0">
      <SectionHeader
        title="Admin Hub"
        subtitle="Cooperativas · usuarios · seguridad"
      />

      <div className="flex flex-wrap gap-2">
        {tabBtn("cooperativas", "Cooperativas")}
        {tabBtn("seguridad", "Seguridad")}
        {tabBtn("config", "Config")}
        {tabBtn("roles", "Roles")}
      </div>

      {message && (
        <p className="text-sm text-cyan-200 border border-cyan-500/25 rounded-xl px-4 py-2.5 bg-cyan-500/8">
          {message}
        </p>
      )}

      {hubTab === "config" && <PlatformSettingsPanel onMessage={setMessage} />}

      {hubTab === "roles" && (
        <div className="space-y-4">
          <SidebarSection title="Roles de consola">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {rbacRoles.map((r) => (
                <GlassCard key={r.codigo} title={r.nombre} accent="cyan" variant="secondary">
                  <p className="text-xs text-slate-400 mb-2">{r.descripcion}</p>
                  <p className="text-[11px] font-mono text-slate-500">{r.permisos.length} permisos</p>
                </GlassCard>
              ))}
            </div>
          </SidebarSection>
          <SidebarSection title="Matriz (referencia)">
            <div className="overflow-x-auto border border-slate-800 rounded-xl max-h-80">
              <table className="w-full text-xs text-left">
                <thead className="bg-slate-950/80 text-slate-400 sticky top-0">
                  <tr>
                    <th className="px-3 py-2">Permiso</th>
                    {rbacRoles.map((r) => (
                      <th key={r.codigo} className="px-2 py-2 text-center">
                        {r.codigo}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rbacPerms.map((p) => (
                    <tr key={p.codigo} className="border-t border-slate-800/80">
                      <td className="px-3 py-2 font-mono text-slate-300">{p.codigo}</td>
                      {rbacRoles.map((r) => (
                        <td key={r.codigo} className="px-2 py-2 text-center">
                          {r.permisos.includes(p.codigo) ? (
                            <span className="text-emerald-400">Sí</span>
                          ) : (
                            <span className="text-slate-600">—</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SidebarSection>
        </div>
      )}

      {hubTab === "seguridad" && (
        <SidebarSection title="Auditoría de login (consola)">
          <ul className="space-y-1 text-xs font-mono text-slate-400 max-h-96 overflow-y-auto">
            {loginEvents.length === 0 ? (
              <li className="text-slate-500">Sin eventos aún.</li>
            ) : (
              loginEvents.map((ev, idx) => (
                <li key={idx}>
                  {ev.created_at?.slice(0, 19)} · {ev.ok ? "OK" : "FAIL"} · {ev.actor} · {ev.reason} ·{" "}
                  {ev.ip}
                </li>
              ))
            )}
          </ul>
          <div className="mt-4 border-t border-slate-800 pt-3">
            <p className="text-xs text-slate-500 mb-2">Eventos operativos recientes</p>
            <div className="space-y-1 max-h-48 overflow-y-auto text-xs">
              {auditEvents.slice(0, 15).map((ev) => (
                <div key={ev.id} className="font-mono text-slate-400">
                  {ev.created_at?.slice(0, 16)} · {ev.accion} · {ev.recurso}
                </div>
              ))}
            </div>
          </div>
        </SidebarSection>
      )}

      {hubTab === "cooperativas" &&
        (loading ? (
          <p className="text-slate-500">Cargando…</p>
        ) : (
          <div className="space-y-5">
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
              <KpiCard label="Cooperativas" value={cooperativas.length} tone="cyan" />
              <KpiCard label="Usuarios" value={totalUsuarios} tone="emerald" />
              <KpiCard label="Tickets abiertos" value={totalAbiertos} tone="amber" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Lista */}
              <GlassCard title="Cooperativas" accent="cyan" variant="secondary">
                <div className="space-y-1.5 max-h-[28rem] overflow-y-auto">
                  {cooperativas.length === 0 ? (
                    <p className="text-xs text-slate-500">Ninguna aún. Creá la primera →</p>
                  ) : (
                    cooperativas.map((o) => (
                      <button
                        key={o.slug}
                        type="button"
                        onClick={() => setSelectedSlug(o.slug)}
                        className={`w-full text-left p-2.5 rounded-xl border transition-colors ${
                          selectedSlug === o.slug
                            ? "border-cyan-500/40 bg-cyan-500/8"
                            : "border-slate-800 hover:border-slate-700"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span
                            className="w-7 h-7 rounded-lg flex items-center justify-center text-[10px] font-bold shrink-0"
                            style={{ backgroundColor: `${o.brand_color}22`, color: o.brand_color }}
                          >
                            {o.logo_label}
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="text-sm text-slate-100 truncate">{o.nombre}</p>
                            <p className="text-[10px] font-mono text-slate-500">
                              {o.slug} · {o.usuarios ?? 0} usr
                            </p>
                          </div>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </GlassCard>

              {/* Crear */}
              <GlassCard title="Nueva cooperativa" accent="emerald" variant="secondary">
                <form onSubmit={onCreateOrg} className="space-y-2.5">
                  <input
                    required
                    placeholder="Nombre"
                    value={newOrg.nombre}
                    onChange={(e) => setNewOrg({ ...newOrg, nombre: e.target.value })}
                    className={inputCls}
                  />
                  <input
                    placeholder="Slug opcional (coop-…)"
                    value={newOrg.slug}
                    onChange={(e) => setNewOrg({ ...newOrg, slug: e.target.value })}
                    className={`${inputCls} font-mono`}
                  />
                  <div className="flex gap-2">
                    <input
                      placeholder="Logo"
                      maxLength={8}
                      value={newOrg.logo_label}
                      onChange={(e) => setNewOrg({ ...newOrg, logo_label: e.target.value })}
                      className="w-20 bg-slate-950 border border-slate-700/80 rounded-lg px-2 py-2 text-sm text-center"
                    />
                    <input
                      type="color"
                      value={newOrg.brand_color}
                      onChange={(e) => setNewOrg({ ...newOrg, brand_color: e.target.value })}
                      className="h-10 w-14 rounded-lg border border-slate-700 bg-slate-950"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={busy}
                    className="w-full text-sm font-medium px-4 py-2 rounded-lg border border-emerald-500/35 text-emerald-200 hover:bg-emerald-500/10 disabled:opacity-50"
                  >
                    Crear
                  </button>
                </form>
              </GlassCard>

              {/* Detalle */}
              <GlassCard
                title={selectedOrg ? selectedOrg.nombre : "Detalle"}
                accent="cyan"
                variant="secondary"
              >
                {!selectedOrg ? (
                  <p className="text-xs text-slate-500">Seleccioná una cooperativa.</p>
                ) : (
                  <div className="space-y-4">
                    <div className="flex flex-wrap gap-2 items-center">
                      <StatusPill label={selectedOrg.slug} tone="neutral" />
                      <span className="text-[11px] text-slate-500">{users.length} usuarios</span>
                    </div>

                    {/* Invite */}
                    <div>
                      <p className="text-xs text-slate-400 mb-1.5">Invitar operador</p>
                      <form
                        className="space-y-2"
                        onSubmit={async (e) => {
                          e.preventDefault();
                          setBusy(true);
                          try {
                            const res = await api.createInvite(inviteForm, selectedSlug);
                            setMessage(
                              `Invitación a ${res.email}${res.token ? ` · token: ${res.token.slice(0, 10)}…` : ""}`,
                            );
                            setInviteForm({ email: "", nombre: "", rol: "agente" });
                            await loadInvites(selectedSlug);
                          } catch (err) {
                            setMessage(err instanceof Error ? err.message : "Error invite");
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        <input
                          className={inputCls}
                          placeholder="Email"
                          value={inviteForm.email}
                          onChange={(e) => setInviteForm((f) => ({ ...f, email: e.target.value }))}
                          required
                        />
                        <div className="flex gap-2">
                          <select
                            className={inputCls}
                            value={inviteForm.rol}
                            onChange={(e) => setInviteForm((f) => ({ ...f, rol: e.target.value }))}
                          >
                            <option value="agente">agente</option>
                            <option value="supervisor">supervisor</option>
                            <option value="ejecutivo">ejecutivo</option>
                          </select>
                          <button
                            type="submit"
                            disabled={busy}
                            className="shrink-0 px-3 rounded-lg border border-cyan-500/35 text-cyan-200 text-xs disabled:opacity-50"
                          >
                            Invitar
                          </button>
                        </div>
                      </form>
                      {invites.filter((i) => i.pendiente).length > 0 && (
                        <ul className="mt-2 text-[10px] font-mono text-slate-500 space-y-0.5">
                          {invites
                            .filter((i) => i.pendiente)
                            .slice(0, 5)
                            .map((i) => (
                              <li key={i.email}>pendiente · {i.email}</li>
                            ))}
                        </ul>
                      )}
                    </div>

                    {/* Users */}
                    <div className="border-t border-slate-800 pt-3 max-h-48 overflow-y-auto space-y-1">
                      {users.length === 0 ? (
                        <p className="text-xs text-slate-500">Sin usuarios.</p>
                      ) : (
                        users.map((u) => (
                          <div
                            key={u.id}
                            className="flex justify-between gap-2 text-xs py-1.5 border-b border-slate-800/50"
                          >
                            <div className="min-w-0">
                              <p className="text-slate-200 truncate">{u.nombre}</p>
                              <p className="font-mono text-slate-500 truncate text-[10px]">{u.email}</p>
                            </div>
                            <div className="shrink-0 flex flex-col items-end gap-0.5">
                              <span className="text-slate-500">{u.rol}</span>
                              <button
                                type="button"
                                disabled={busy}
                                className="text-[10px] text-cyan-300"
                                onClick={() => void onToggleUserActive(u)}
                              >
                                {u.activo === false ? "Activar" : "Desactivar"}
                              </button>
                              <button
                                type="button"
                                disabled={busy}
                                className="text-[10px] text-amber-300/90"
                                onClick={async () => {
                                  try {
                                    const r = await api.resetUserPassword(u.id, selectedSlug);
                                    setMessage(
                                      `Reset ${r.email}${r.temporary_password ? ` · ${r.temporary_password}` : ""}`,
                                    );
                                  } catch (err) {
                                    setMessage(err instanceof Error ? err.message : "Error reset");
                                  }
                                }}
                              >
                                Reset clave
                              </button>
                            </div>
                          </div>
                        ))
                      )}
                    </div>

                    {/* Delete */}
                    <div className="border-t border-rose-900/40 pt-3">
                      {!showDelete ? (
                        <button
                          type="button"
                          className="text-xs text-rose-300/90 hover:text-rose-200"
                          onClick={() => setShowDelete(true)}
                        >
                          Eliminar cooperativa…
                        </button>
                      ) : (
                        <div className="space-y-2">
                          <p className="text-[11px] text-rose-300/90 leading-relaxed">
                            Borra usuarios, tickets, KB y datos de canal de esta coop. Escribí{" "}
                            <span className="font-mono text-rose-200">{selectedOrg.slug}</span> para
                            confirmar.
                          </p>
                          <input
                            className={`${inputCls} font-mono border-rose-800/50`}
                            placeholder={selectedOrg.slug}
                            value={deleteConfirm}
                            onChange={(e) => setDeleteConfirm(e.target.value)}
                          />
                          <div className="flex gap-2">
                            <button
                              type="button"
                              disabled={busy || deleteConfirm !== selectedOrg.slug}
                              onClick={() => void onDeleteOrg()}
                              className="text-xs px-3 py-1.5 rounded-lg bg-rose-600/80 text-white disabled:opacity-40"
                            >
                              Confirmar borrado
                            </button>
                            <button
                              type="button"
                              className="text-xs text-slate-400"
                              onClick={() => {
                                setShowDelete(false);
                                setDeleteConfirm("");
                              }}
                            >
                              Cancelar
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </GlassCard>
            </div>
          </div>
        ))}
    </div>
  );
}
