"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { api } from "@/lib/api-client";

const NAV_GROUPS = [
  {
    title: "Operación",
    items: [
      { href: "/inbox", label: "Bandeja", id: "inbox", permission: null as string | null },
      { href: "/soporte", label: "Consola de tickets", id: "soporte", permission: null },
    ],
  },
  {
    title: "Gestión",
    items: [
      { href: "/conocimiento", label: "Centro de conocimiento", id: "kb", permission: "kb.propose" },
      { href: "/tickets", label: "Cola de tickets", id: "tickets", permission: "tickets.queue.view" },
      {
        href: "/estadisticas",
        label: "Estadísticas",
        id: "stats",
        permission: "stats.any",
      },
      { href: "/admin", label: "Administración", id: "admin", permission: "orgs.manage" },
    ],
  },
];

export function SidebarNav() {
  const pathname = usePathname();
  const { isAdmin, can, tenantSlug } = useApp();
  const [kbPendingCount, setKbPendingCount] = useState(0);

  const canSee = (permission: string | null) => {
    if (!permission) return true;
    if (permission === "stats.any") {
      return can("stats.global") || can("stats.bot") || can("stats.agents");
    }
    return can(permission);
  };

  const loadKbPending = useCallback(async () => {
    if (!isAdmin) {
      setKbPendingCount(0);
      return;
    }
    try {
      const res = await api.kbContributions({ estado: "pendiente" }, tenantSlug);
      setKbPendingCount((res.contribuciones || []).length);
    } catch {
      setKbPendingCount(0);
    }
  }, [isAdmin, tenantSlug]);

  useEffect(() => {
    void loadKbPending();
    if (!isAdmin) return;
    const id = window.setInterval(() => void loadKbPending(), 45_000);
    return () => window.clearInterval(id);
  }, [isAdmin, loadKbPending]);

  const linkClass = (active: boolean) =>
    `block text-left px-3 py-2.5 rounded-xl text-sm font-medium transition-colors whitespace-nowrap ${
      active
        ? "bg-cyan-500/10 text-cyan-300 border border-cyan-500/25 shadow-[inset_0_1px_0_rgba(34,211,238,0.08)]"
        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent"
    }`;

  const flatItems = NAV_GROUPS.flatMap((g) => g.items.filter((n) => canSee(n.permission)));

  return (
    <>
      <nav className="lg:hidden flex gap-2 p-2 border-b border-slate-800/80 overflow-x-auto shrink-0">
        {flatItems.map((item) => {
          const active = pathname.startsWith(item.href);
          const showKbBadge = item.id === "kb" && isAdmin && kbPendingCount > 0;
          return (
            <Link key={item.href} href={item.href} className={linkClass(active)}>
              <span className="inline-flex items-center gap-1.5">
                {item.label.split(" ").slice(-1)[0]}
                {showKbBadge && (
                  <span className="min-w-[1rem] h-4 px-1 rounded-full bg-amber-400 text-slate-950 text-[9px] font-bold flex items-center justify-center">
                    {kbPendingCount > 9 ? "9+" : kbPendingCount}
                  </span>
                )}
              </span>
            </Link>
          );
        })}
      </nav>
      <aside className="w-60 shrink-0 border-r border-slate-800/80 p-3 hidden lg:block">
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-600 px-2 mb-3">
          Navegación
        </p>
        <nav className="space-y-4">
          {NAV_GROUPS.map((group) => {
            const items = group.items.filter((n) => canSee(n.permission));
            if (!items.length) return null;
            return (
              <div key={group.title}>
                <p className="text-[10px] font-mono uppercase tracking-wider text-slate-600 px-2 mb-1.5">
                  {group.title}
                </p>
                <div className="space-y-1">
                  {items.map((item) => {
                    const active = pathname.startsWith(item.href);
                    const showKbBadge = item.id === "kb" && isAdmin && kbPendingCount > 0;
                    return (
                      <Link key={item.href} href={item.href} className={linkClass(active)}>
                        <span className="flex items-center justify-between gap-2">
                          <span>{item.label}</span>
                          {showKbBadge && (
                            <span className="min-w-[1.15rem] h-[1.15rem] px-1 rounded-full bg-amber-400 text-slate-950 text-[9px] font-bold flex items-center justify-center">
                              {kbPendingCount > 9 ? "9+" : kbPendingCount}
                            </span>
                          )}
                        </span>
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
