"use client";

import { useApp } from "@/contexts/AppContext";

export function AppHeader() {
  const { user, isAdmin, orgs, tenantSlug, tenantContext, logout, setTenant } =
    useApp();

  const brandColor = tenantContext?.brand_color || "#22d3ee";
  const logoLabel = tenantContext?.logo_label || "i";
  const orgName = tenantContext?.organizacion_nombre || "imowi";

  return (
    <header className="glass border-b border-slate-800/80 px-4 py-3 flex items-center justify-between gap-4 shrink-0">
      <div className="flex items-center gap-3 min-w-0">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-slate-950 shrink-0"
          style={{
            background: `linear-gradient(135deg, ${brandColor}, #3b82f6)`,
          }}
        >
          {logoLabel}
        </div>
        <div className="min-w-0">
          <h1 className="font-semibold text-slate-100 truncate">{orgName}</h1>
          <p className="text-[10px] font-mono text-slate-500 truncate">
            Operations Hub · Agentic AI
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap justify-end">
        {isAdmin && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono text-slate-500 hidden sm:inline">
              Vista global / cooperativa
            </span>
            <select
              value={tenantSlug}
              onChange={(e) => setTenant(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1.5 text-xs font-mono"
            >
              {orgs.map((o) => (
                <option key={o.slug} value={o.slug}>
                  {o.nombre}
                </option>
              ))}
            </select>
          </div>
        )}
        <span className="text-xs font-mono text-slate-400 hidden md:inline">
          {isAdmin ? "NOC imowi" : user?.nombre} · {user?.rol}
        </span>
        <button
          type="button"
          onClick={logout}
          className="text-xs font-mono px-3 py-1.5 rounded-lg border border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-500"
        >
          Salir
        </button>
      </div>
    </header>
  );
}
