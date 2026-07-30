"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useApp } from "@/contexts/AppContext";
import { api } from "@/lib/api-client";

export type PendingTaskKind = "kb_review" | "ticket_notif" | "inbox";

export interface PendingTask {
  id: string;
  kind: PendingTaskKind;
  title: string;
  detail: string;
  href: string;
  createdAt?: string;
}

const POLL_MS = 45_000;

function BellIcon({ active }: { active: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`w-4 h-4 ${active ? "text-amber-300" : "text-slate-400"}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      aria-hidden
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 1 0-12 0v3.2c0 .5-.2 1-.6 1.4L4 17h5m6 0a3 3 0 1 1-6 0m6 0H9"
      />
    </svg>
  );
}

function kindLabel(kind: PendingTaskKind): string {
  if (kind === "kb_review") return "Revisión KB";
  if (kind === "inbox") return "Bandeja";
  return "Ticket";
}

export function PendingTasksBell() {
  const { isAdmin, tenantSlug, notifications, user } = useApp();
  const [open, setOpen] = useState(false);
  const [tasks, setTasks] = useState<PendingTask[]>([]);
  const [loading, setLoading] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    if (!user) {
      setTasks([]);
      return;
    }
    setLoading(true);
    const next: PendingTask[] = [];
    try {
      if (isAdmin) {
        const kb = await api.kbContributions({ estado: "pendiente" }, tenantSlug);
        for (const c of kb.contribuciones || []) {
          next.push({
            id: `kb-${c.id}`,
            kind: "kb_review",
            title: c.titulo,
            detail: [
              c.nivel_ticket || "",
              c.ticket_id || "",
              c.propuesto_por || c.origen,
            ]
              .filter(Boolean)
              .join(" · "),
            href: "/conocimiento",
            createdAt: c.created_at,
          });
        }
      }

      const unread = (notifications || []).filter((n) => n.leida !== "Sí");
      for (const n of unread.slice(0, 8)) {
        next.push({
          id: `notif-${n.id}`,
          kind: "ticket_notif",
          title: n.titulo || "Novedad de ticket",
          detail: n.mensaje?.slice(0, 120) || n.ticket_id,
          href: n.ticket_id
            ? `/soporte?ticket=${encodeURIComponent(n.ticket_id)}`
            : "/soporte",
          createdAt: n.created_at,
        });
      }
    } catch {
      // silencioso: la campana no debe romper el header
    } finally {
      setTasks(next);
      setLoading(false);
    }
  }, [user, isAdmin, tenantSlug, notifications]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!user) return;
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(id);
  }, [user, load]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const count = tasks.length;
  const hasPending = count > 0;

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => {
          setOpen((v) => !v);
          if (!open) void load();
        }}
        className={`relative p-2 rounded-lg border transition-colors ${
          hasPending
            ? "border-amber-500/40 bg-amber-500/10 hover:bg-amber-500/15"
            : "border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-500 hover:bg-slate-800/50"
        }`}
        aria-label={
          hasPending
            ? `${count} pendientes por atender`
            : "Sin pendientes"
        }
        title={hasPending ? `${count} pendientes` : "Sin pendientes"}
      >
        <BellIcon active={hasPending} />
        {hasPending && (
          <span className="absolute -top-1 -right-1 min-w-[1.1rem] h-[1.1rem] px-1 rounded-full bg-amber-400 text-slate-950 text-[9px] font-bold flex items-center justify-center leading-none">
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-xl border border-slate-700 bg-slate-950 shadow-xl shadow-black/40 z-50 overflow-hidden">
          <div className="px-3 py-2.5 border-b border-slate-800 flex items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold text-slate-100">Pendientes</p>
              <p className="text-[10px] text-slate-500">
                {isAdmin
                  ? "Revisiones KB y novedades de tickets"
                  : "Novedades operativas de tus tickets"}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void load()}
              className="text-[10px] font-mono text-cyan-400 hover:text-cyan-300"
            >
              {loading ? "…" : "Actualizar"}
            </button>
          </div>

          <div className="max-h-80 overflow-y-auto">
            {!tasks.length ? (
              <p className="px-3 py-6 text-center text-xs text-slate-500">
                No tenés pendientes por ahora.
              </p>
            ) : (
              <ul className="divide-y divide-slate-800/80">
                {tasks.map((t) => (
                  <li key={t.id}>
                    <Link
                      href={t.href}
                      onClick={() => setOpen(false)}
                      className="block px-3 py-2.5 hover:bg-slate-900/80 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs text-slate-100 font-medium line-clamp-2">
                          {t.title}
                        </p>
                        <span className="shrink-0 text-[9px] font-mono uppercase px-1.5 py-0.5 rounded border border-slate-700 text-slate-400">
                          {kindLabel(t.kind)}
                        </span>
                      </div>
                      {t.detail && (
                        <p className="text-[11px] text-slate-500 mt-1 line-clamp-2">
                          {t.detail}
                        </p>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {isAdmin && (
            <div className="px-3 py-2 border-t border-slate-800 bg-slate-900/40">
              <Link
                href="/conocimiento"
                onClick={() => setOpen(false)}
                className="text-[11px] text-amber-300 hover:text-amber-200 font-medium"
              >
                Ir a bandeja de revisión KB →
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
