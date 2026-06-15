"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "@/contexts/AppContext";

const NAV_GROUPS = [
  {
    title: "Operación",
    items: [
      { href: "/soporte", label: "Consola de Soporte", id: "soporte", admin: false },
      { href: "/red", label: "Monitor de Red", id: "red", admin: true },
    ],
  },
  {
    title: "Gestión",
    items: [
      { href: "/estadisticas", label: "Estadísticas", id: "stats", admin: true },
      { href: "/admin", label: "Administración", id: "admin", admin: true },
    ],
  },
  {
    title: "Conocimiento",
    items: [{ href: "/conocimiento", label: "Centro de Conocimiento", id: "kb", admin: true }],
  },
];

export function SidebarNav() {
  const pathname = usePathname();
  const { isAdmin } = useApp();

  const linkClass = (active: boolean) =>
    `block text-left px-3 py-2.5 rounded-xl text-sm font-medium transition-colors whitespace-nowrap ${
      active
        ? "bg-cyan-500/10 text-cyan-300 border border-cyan-500/25 shadow-[inset_0_1px_0_rgba(34,211,238,0.08)]"
        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent"
    }`;

  const flatItems = NAV_GROUPS.flatMap((g) =>
    g.items.filter((n) => !n.admin || isAdmin),
  );

  return (
    <>
      <nav className="lg:hidden flex gap-2 p-2 border-b border-slate-800/80 overflow-x-auto shrink-0">
        {flatItems.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} className={linkClass(active)}>
              {item.label.split(" ").slice(-1)[0]}
            </Link>
          );
        })}
      </nav>
      <aside className="w-60 shrink-0 border-r border-slate-800/80 p-3 hidden lg:block">
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-600 px-2 mb-3">
          imowi Operations
        </p>
        <nav className="space-y-4">
          {NAV_GROUPS.map((group) => {
            const items = group.items.filter((n) => !n.admin || isAdmin);
            if (!items.length) return null;
            return (
              <div key={group.title}>
                <p className="text-[10px] font-mono uppercase tracking-wider text-slate-600 px-2 mb-1.5">
                  {group.title}
                </p>
                <div className="space-y-1">
                  {items.map((item) => {
                    const active = pathname.startsWith(item.href);
                    return (
                      <Link key={item.href} href={item.href} className={linkClass(active)}>
                        {item.label}
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
