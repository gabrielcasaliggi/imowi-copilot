"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { useKbPendingCount } from "@/hooks/useKbPendingCount";

type NavItem = {
  href: string;
  label: string;
  /** Etiqueta corta única en nav móvil (evita “tickets” duplicado). */
  shortLabel: string;
  id: string;
  permission: string | null;
};

const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: "Operación",
    items: [
      { href: "/inbox", label: "Bandeja", shortLabel: "Bandeja", id: "inbox", permission: null },
      {
        href: "/soporte",
        label: "Consola",
        shortLabel: "Consola",
        id: "soporte",
        permission: null,
      },
      {
        href: "/tickets",
        label: "Cola",
        shortLabel: "Cola",
        id: "tickets",
        permission: "tickets.queue.view",
      },
    ],
  },
  {
    title: "Gestión",
    items: [
      {
        href: "/conocimiento",
        label: "Conocimiento",
        shortLabel: "KB",
        id: "kb",
        permission: "kb.publish",
      },
      {
        href: "/estadisticas",
        label: "Estadísticas",
        shortLabel: "Stats",
        id: "stats",
        permission: "stats.any",
      },
      {
        href: "/admin",
        label: "Administración",
        shortLabel: "Admin",
        id: "admin",
        permission: "orgs.manage",
      },
    ],
  },
];

export function SidebarNav() {
  const pathname = usePathname();
  const { can, tenantSlug } = useApp();
  const canKb = can("kb.publish");
  const { count: kbPendingCount } = useKbPendingCount(canKb, tenantSlug);

  const canSee = (permission: string | null) => {
    if (!permission) return true;
    if (permission === "stats.any") {
      return (
        can("stats.global") ||
        can("stats.bot") ||
        can("stats.agents") ||
        can("stats.self")
      );
    }
    return can(permission);
  };

  const linkClass = (active: boolean) =>
    `block text-left px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ease-in-out whitespace-nowrap ${
      active
        ? "border shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent"
    }`;

  const activeStyle = {
    background: "color-mix(in srgb, var(--brand) 12%, transparent)",
    color: "var(--brand)",
    borderColor: "color-mix(in srgb, var(--brand) 30%, transparent)",
  } as const;

  const flatItems = NAV_GROUPS.flatMap((g) => g.items.filter((n) => canSee(n.permission)));

  return (
    <>
      <nav className="lg:hidden flex gap-2 p-2 border-b border-slate-800/80 overflow-x-auto shrink-0">
        {flatItems.map((item) => {
          const active = pathname.startsWith(item.href);
          const showKbBadge = item.id === "kb" && kbPendingCount > 0;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={linkClass(active)}
              style={active ? activeStyle : undefined}
            >
              <span className="inline-flex items-center gap-1.5">
                {item.shortLabel}
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
      <aside className="w-60 shrink-0 border-r border-slate-800/80 p-3 bg-ecolan-dark/30 hidden lg:block">
        <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500 px-2 mb-3">
          Navegación
        </p>
        <nav className="space-y-4">
          {NAV_GROUPS.map((group) => {
            const items = group.items.filter((n) => canSee(n.permission));
            if (!items.length) return null;
            return (
              <div key={group.title}>
                <p className="text-[10px] font-medium uppercase tracking-wider text-slate-500 px-2 mb-1.5">
                  {group.title}
                </p>
                <div className="space-y-1">
                  {items.map((item) => {
                    const active = pathname.startsWith(item.href);
                    const showKbBadge = item.id === "kb" && kbPendingCount > 0;
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={linkClass(active)}
                        style={active ? activeStyle : undefined}
                      >
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
