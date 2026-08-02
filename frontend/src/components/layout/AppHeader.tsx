"use client";

import { useApp } from "@/contexts/AppContext";
import { PendingTasksBell } from "@/components/layout/PendingTasksBell";
import { AvailabilityControl } from "@/components/layout/AvailabilityControl";

export function AppHeader() {
  const { user, isAdmin, orgs, tenantSlug, tenantContext, logout, setTenant } =
    useApp();

  const brandColor = tenantContext?.brand_color || "#2298A6";
  const logoLabel = tenantContext?.logo_label || "i";
  const orgName = tenantContext?.organizacion_nombre || "Operations Hub";
  const rolLabel =
    user?.rol === "admin"
      ? "Administración"
      : user?.rol === "supervisor"
        ? "Supervisor"
        : user?.rol === "ejecutivo"
          ? "Ejecutivo"
          : user?.nombre || "Agente";

  return (
    <header className="glass border-b border-slate-800/80 px-4 py-3 flex items-center justify-between gap-4 shrink-0">
      <div className="flex items-center gap-3 min-w-0">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-white shrink-0 shadow-lg shadow-ecolan-brand/15"
          style={{
            background: `linear-gradient(135deg, ${brandColor}, #1A7985)`,
          }}
        >
          {logoLabel}
        </div>
        <div className="min-w-0">
          <h1 className="font-semibold text-slate-100 truncate tracking-tight">{orgName}</h1>
          <p className="text-[10px] font-mono text-slate-500 truncate uppercase">
            {user?.rol || "agente"}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap justify-end">
        {isAdmin && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-slate-500 hidden sm:inline">
              Tenant
            </span>
            <select
              value={tenantSlug}
              onChange={(e) => setTenant(e.target.value)}
              className="bg-slate-950 border border-slate-600/80 rounded-lg px-2.5 py-1.5 text-xs font-mono transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent"
            >
              {orgs.map((o) => (
                <option key={o.slug} value={o.slug}>
                  {o.nombre}
                </option>
              ))}
            </select>
          </div>
        )}
        <AvailabilityControl />
        <PendingTasksBell />
        <div className="hidden md:flex flex-col items-end">
          <span className="text-xs text-slate-300 truncate max-w-[10rem]">{rolLabel}</span>
        </div>
        <button
          type="button"
          onClick={logout}
          className="text-xs font-mono px-3 py-1.5 rounded-lg border border-slate-600/80 text-slate-400 hover:text-slate-200 hover:border-slate-500 hover:bg-slate-800/50 transition-all duration-200 ease-in-out"
        >
          Salir
        </button>
      </div>
    </header>
  );
}
