"use client";

import { useState, type ReactNode } from "react";

type Accent = "brand" | "cyan" | "amber" | "emerald" | "default";
type Variant = "default" | "primary" | "secondary" | "technical";

export function GlassCard({
  title,
  children,
  accent,
  variant = "default",
  className = "",
  titleExtra,
}: {
  title?: string;
  children: ReactNode;
  accent?: Accent;
  variant?: Variant;
  className?: string;
  titleExtra?: ReactNode;
}) {
  const isBrand = accent === "brand" || accent === "cyan";
  const border =
    variant === "primary"
      ? "border-ecolan-brand/25 bg-ecolan-brand/8 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
      : variant === "secondary"
        ? "border-slate-700/60 bg-slate-900/35"
        : variant === "technical"
          ? "border-slate-700/50 bg-slate-950/50"
          : isBrand
            ? "border-ecolan-brand/20 bg-ecolan-brand/5"
            : accent === "amber"
              ? "border-amber-500/20 bg-amber-500/5"
              : accent === "emerald"
                ? "border-emerald-500/20 bg-emerald-500/5"
                : "border-slate-800/80 bg-slate-900/40 shadow-sm";

  const titleColor =
    variant === "primary"
      ? "text-ecolan-brand"
      : isBrand
        ? "text-ecolan-brand/90"
        : accent === "amber"
          ? "text-amber-300/90"
          : accent === "emerald"
            ? "text-emerald-300/90"
            : "text-slate-400";

  return (
    <div className={`rounded-2xl border p-4 transition-all duration-200 ease-in-out ${border} ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-2 mb-2.5">
          <h3 className={`text-xs font-mono uppercase tracking-wider font-medium ${titleColor}`}>
            {title}
          </h3>
          {titleExtra}
        </div>
      )}
      {children}
    </div>
  );
}

export function SidebarSection({
  title,
  children,
  className = "",
  defaultOpen = true,
  sticky = false,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  /** Si false, arranca colapsada (útil en sidebars densos). */
  defaultOpen?: boolean;
  /** Fija el encabezado al hacer scroll del sidebar. */
  sticky?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className={`sidebar-section ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={`sidebar-section-header w-full text-left cursor-pointer hover:opacity-90 transition-opacity duration-200 ${
          sticky ? "sticky top-0 z-[5] bg-ecolan-dark/95 backdrop-blur-sm py-1 -mx-0.5 px-0.5" : ""
        }`}
      >
        <h2 className="sidebar-section-title">{title}</h2>
        <div className="sidebar-section-line" aria-hidden />
        <span className="text-[10px] font-mono text-slate-400 tabular-nums w-4 text-center" aria-hidden>
          {open ? "−" : "+"}
        </span>
      </button>
      {open && <div className="sidebar-section-body">{children}</div>}
    </section>
  );
}

export function KpiCard({
  label,
  value,
  tone = "default",
  helper,
}: {
  label: string;
  value: string | number;
  tone?: "default" | "brand" | "cyan" | "emerald" | "amber" | "red" | "violet";
  helper?: string;
}) {
  const isBrand = tone === "brand" || tone === "cyan" || tone === "violet";
  const toneClass =
    isBrand
      ? "border-ecolan-brand/25 bg-ecolan-brand/10 shadow-ecolan-brand/5"
      : tone === "emerald"
        ? "border-emerald-500/25 bg-emerald-500/10 shadow-emerald-500/5"
        : tone === "amber"
          ? "border-amber-500/25 bg-amber-500/10 shadow-amber-500/5"
          : tone === "red"
            ? "border-rose-500/25 bg-rose-500/10 shadow-rose-500/5"
            : "border-slate-800/80 bg-slate-900/60 shadow-sm";
  const valueClass =
    isBrand
      ? "text-slate-50"
      : tone === "emerald"
        ? "text-emerald-100"
        : tone === "amber"
          ? "text-amber-100"
          : tone === "red"
            ? "text-rose-100"
            : "text-slate-100";
  return (
    <div className={`rounded-xl border p-3.5 shadow-sm transition-all duration-200 ease-in-out ${toneClass}`}>
      <p className="text-[11px] uppercase tracking-wider font-mono text-slate-400">
        {label}
      </p>
      <p className={`text-2xl font-semibold mt-1 tabular-nums tracking-tight ${valueClass}`}>{value}</p>
      {helper && <p className="text-[11px] text-slate-500 mt-1">{helper}</p>}
    </div>
  );
}

export function SlaBadge({
  label,
  estado,
}: {
  label?: string;
  estado?: string;
}) {
  if (!label && !estado) return null;
  const est = (estado || "").toLowerCase();
  const cls =
    est === "vencido" || est === "crítico" || est === "critico"
      ? "chip chip-sla-danger"
      : est === "en riesgo"
        ? "chip chip-sla-warn"
        : "chip chip-sla-ok";
  return <span className={cls}>{label || estado}</span>;
}

export function PanelHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-3">
      <h3 className="enterprise-panel-header !mb-0">{title}</h3>
      {subtitle && <p className="text-[11px] text-slate-400 mt-1">{subtitle}</p>}
    </div>
  );
}

export function DataRow({
  label,
  children,
  mono,
}: {
  label: string;
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex justify-between gap-3 items-start text-xs">
      <span className="text-slate-500 shrink-0">{label}</span>
      <span className={`text-slate-200 text-right ${mono ? "font-mono" : ""}`}>{children}</span>
    </div>
  );
}

export type StatusPillTone = "available" | "demo" | "credentials" | "soon" | "neutral";

export function StatusPill({
  label,
  tone = "neutral",
}: {
  label: string;
  tone?: StatusPillTone;
}) {
  const cls =
    tone === "available"
      ? "status-pill status-pill-available"
      : tone === "demo"
        ? "status-pill status-pill-demo"
        : tone === "credentials"
          ? "status-pill status-pill-credentials"
          : tone === "soon"
            ? "status-pill status-pill-soon"
            : "status-pill status-pill-neutral";
  return <span className={cls}>{label}</span>;
}

export function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3 mb-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-50 tracking-tight">{title}</h2>
        {subtitle && (
          <p className="text-[11px] font-mono text-slate-400 mt-1 leading-relaxed">{subtitle}</p>
        )}
      </div>
      {action}
    </div>
  );
}

export function CapabilityCard({
  title,
  description,
  status,
  statusTone = "neutral",
  items,
  footer,
}: {
  title: string;
  description: string;
  status?: string;
  statusTone?: StatusPillTone;
  items?: string[];
  footer?: ReactNode;
}) {
  return (
    <div className="capability-card rounded-2xl border border-slate-700/80 bg-slate-900/40 p-4 flex flex-col h-full shadow-sm transition-all duration-200 ease-in-out hover:border-slate-600/80">
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="text-sm font-semibold text-slate-100 tracking-tight">{title}</h3>
        {status && <StatusPill label={status} tone={statusTone} />}
      </div>
      <p className="text-xs text-slate-400 leading-relaxed mb-3">{description}</p>
      {items && items.length > 0 && (
        <ul className="space-y-1.5 flex-1">
          {items.map((item) => (
            <li key={item} className="text-[11px] text-slate-300 flex gap-2">
              <span className="text-ecolan-brand/70 shrink-0">·</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
      {footer && <div className="mt-3 pt-3 border-t border-slate-800/80">{footer}</div>}
    </div>
  );
}
