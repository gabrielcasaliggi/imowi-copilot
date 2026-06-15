"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "@/contexts/AppContext";

const NAV = [
  { href: "/soporte", label: "Consola de Soporte", id: "soporte", admin: false },
  { href: "/red", label: "Monitor de Red", id: "red", admin: true },
  { href: "/estadisticas", label: "Estadísticas", id: "stats", admin: true },
  { href: "/conocimiento", label: "Centro de Conocimiento", id: "kb", admin: true },
];

export function SidebarNav() {
  const pathname = usePathname();
  const { isAdmin } = useApp();

  const items = NAV.filter((n) => !n.admin || isAdmin);

  const linkClass = (active: boolean) =>
    `block text-left px-3 py-2.5 rounded-xl text-sm font-medium transition-colors whitespace-nowrap ${
      active
        ? "bg-cyan-500/10 text-cyan-300 border border-cyan-500/25"
        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
    }`;

  return (
    <>
      <nav className="lg:hidden flex gap-2 p-2 border-b border-slate-800/80 overflow-x-auto shrink-0">
        {items.map((item) => {
          const active = pathname.startsWith(item.href);
          return (
            <Link key={item.href} href={item.href} className={linkClass(active)}>
              {item.label.split(" ").slice(-1)[0]}
            </Link>
          );
        })}
      </nav>
      <aside className="w-56 shrink-0 border-r border-slate-800/80 p-3 hidden lg:block">
        <nav className="space-y-1">
          {items.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link key={item.href} href={item.href} className={linkClass(active)}>
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
