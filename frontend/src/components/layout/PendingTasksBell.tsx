"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useApp } from "@/contexts/AppContext";
import { api } from "@/lib/api-client";
import { setKbPendingCount } from "@/hooks/useKbPendingCount";

export type PendingTaskKind = "kb_review" | "ticket_notif" | "inbox";

export interface PendingTask {
  id: string;
  kind: PendingTaskKind;
  title: string;
  detail: string;
  href: string;
  createdAt?: string;
  /** ID real de TicketNotification (solo kind=ticket_notif) */
  notificationId?: string;
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
  const { isAdmin, can, tenantSlug, notifications, user, markNotificationRead } = useApp();
  const canReviewKb = can("kb.publish");
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
      if (canReviewKb) {
        const kb = await api.kbContributions(
          { estado: "pendiente" },
          isAdmin ? tenantSlug : undefined,
        );
        const contribs = kb.contribuciones || [];
        setKbPendingCount(contribs.length);
        for (const c of contribs) {
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
      for (const n of unread.slice(0, 6)) {
        const canal = (n.canal || "").toLowerCase();
        const isCsat = canal === "csat_bajo";
        const isHandoff = canal === "inbox_handoff";
        const isSla = canal === "sla_breach";
        const title = n.titulo
          || (isCsat ? "CSAT bajo" : isHandoff ? "Cliente espera agente" : isSla ? "SLA vencido" : "Novedad de ticket");
        const href = isHandoff
          ? "/inbox"
          : n.ticket_id
            ? `/soporte?ticket=${encodeURIComponent(n.ticket_id)}`
            : isCsat
              ? "/estadisticas"
              : "/soporte";
        next.push({
          id: `notif-${n.id}`,
          kind: "ticket_notif",
          title,
          detail: n.mensaje?.slice(0, 120) || n.ticket_id,
          href,
          createdAt: n.created_at,
          notificationId: n.id,
        });
      }

      const slug = isAdmin ? tenantSlug : undefined;
      const inbox = await api.inboxConversations({ limit: 40, offset: 0 }, slug);
      let inboxAdded = 0;
      for (const c of inbox.conversaciones || []) {
        if (inboxAdded >= 8) break;
        const quien = c.abonado?.nombre || c.telefono || "Cliente";
        if (c.estado === "espera_agente") {
          next.push({
            id: `inbox-wait-${c.id}`,
            kind: "inbox",
            title: "Cliente espera agente",
            detail: `${quien}${c.ultimo_mensaje_texto ? ` · ${c.ultimo_mensaje_texto.slice(0, 80)}` : ""}`,
            href: `/inbox?conv=${encodeURIComponent(c.id)}`,
            createdAt: c.updated_at || c.ultimo_mensaje_at,
          });
          inboxAdded += 1;
        } else if (c.tiene_no_leidos && c.estado === "con_agente") {
          next.push({
            id: `inbox-unread-${c.id}`,
            kind: "inbox",
            title: `Nuevo mensaje · ${quien}`,
            detail: c.ultimo_mensaje_texto?.slice(0, 100) || c.telefono,
            href: `/inbox?conv=${encodeURIComponent(c.id)}`,
            createdAt: c.ultimo_mensaje_at || c.updated_at,
          });
          inboxAdded += 1;
        }
      }
    } catch {
      // silencioso: la campana no debe romper el header
    } finally {
      setTasks(next);
      setLoading(false);
    }
  }, [user, isAdmin, canReviewKb, tenantSlug, notifications]);

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
              <p className="text-[10px] text-slate-400">
                {canReviewKb
                  ? "KB, bandeja y tickets"
                  : "Bandeja y novedades de tickets"}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void load()}
              className="text-[10px] font-mono text-ecolan-brand hover:text-ecolan-brand"
            >
              {loading ? "…" : "Actualizar"}
            </button>
          </div>

          <div className="max-h-80 overflow-y-auto">
            {!tasks.length ? (
              <p className="px-3 py-6 text-center text-xs text-slate-400">
                No tenés pendientes por ahora.
              </p>
            ) : (
              <ul className="divide-y divide-slate-800/80">
                {tasks.map((t) => (
                  <li key={t.id}>
                    <Link
                      href={t.href}
                      onClick={() => {
                        setOpen(false);
                        if (t.kind === "ticket_notif" && t.notificationId) {
                          void markNotificationRead(t.notificationId);
                        }
                      }}
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
                        <p className="text-[11px] text-slate-400 mt-1 line-clamp-2">
                          {t.detail}
                        </p>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {canReviewKb && (
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
