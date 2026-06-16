import type { ReactNode } from "react";

type Accent = "cyan" | "amber" | "emerald" | "default";
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
  const border =
    variant === "primary"
      ? "border-emerald-500/25 bg-emerald-500/8 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
      : variant === "secondary"
        ? "border-slate-700/60 bg-slate-900/35"
        : variant === "technical"
          ? "border-slate-700/50 bg-slate-950/50"
          : accent === "cyan"
            ? "border-cyan-500/20 bg-cyan-500/5"
            : accent === "amber"
              ? "border-amber-500/20 bg-amber-500/5"
              : accent === "emerald"
                ? "border-emerald-500/20 bg-emerald-500/5"
                : "border-slate-800 bg-slate-900/40";

  const titleColor =
    variant === "primary"
      ? "text-emerald-300/95"
      : accent === "cyan"
        ? "text-cyan-400/90"
        : accent === "amber"
          ? "text-amber-300/90"
          : accent === "emerald"
            ? "text-emerald-300/90"
            : "text-slate-400";

  return (
    <div className={`rounded-2xl border p-4 ${border} ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-2 mb-2.5">
          <h3 className={`text-xs font-mono uppercase tracking-wider ${titleColor}`}>
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
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`sidebar-section ${className}`}>
      <div className="sidebar-section-header">
        <h2 className="sidebar-section-title">{title}</h2>
        <div className="sidebar-section-line" aria-hidden />
      </div>
      <div className="sidebar-section-body">{children}</div>
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
  tone?: "default" | "cyan" | "emerald" | "amber" | "red" | "violet";
  helper?: string;
}) {
  const toneClass =
    tone === "cyan"
      ? "border-cyan-500/25 bg-cyan-500/10 shadow-cyan-500/5"
      : tone === "emerald"
        ? "border-emerald-500/25 bg-emerald-500/10 shadow-emerald-500/5"
        : tone === "amber"
          ? "border-amber-500/25 bg-amber-500/10 shadow-amber-500/5"
          : tone === "red"
            ? "border-red-500/25 bg-red-500/10 shadow-red-500/5"
            : tone === "violet"
              ? "border-violet-500/25 bg-violet-500/10 shadow-violet-500/5"
              : "border-slate-800 bg-slate-900/60 shadow-slate-950/20";
  const valueClass =
    tone === "cyan"
      ? "text-cyan-100"
      : tone === "emerald"
        ? "text-emerald-100"
        : tone === "amber"
          ? "text-amber-100"
          : tone === "red"
            ? "text-red-100"
            : tone === "violet"
              ? "text-violet-100"
              : "text-slate-100";
  return (
    <div className={`rounded-xl border p-3 shadow-lg shadow-[inset_0_1px_0_rgba(255,255,255,0.03)] ${toneClass}`}>
      <p className="text-[11px] uppercase tracking-wider font-mono text-slate-500">
        {label}
      </p>
      <p className={`text-2xl font-semibold mt-1 tabular-nums ${valueClass}`}>{value}</p>
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
      {subtitle && <p className="text-[11px] text-slate-500 mt-1">{subtitle}</p>}
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
          <p className="text-[11px] font-mono text-slate-500 mt-1 leading-relaxed">{subtitle}</p>
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
    <div className="capability-card rounded-2xl border border-slate-800/80 bg-slate-900/40 p-4 flex flex-col h-full">
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
        {status && <StatusPill label={status} tone={statusTone} />}
      </div>
      <p className="text-xs text-slate-400 leading-relaxed mb-3">{description}</p>
      {items && items.length > 0 && (
        <ul className="space-y-1.5 flex-1">
          {items.map((item) => (
            <li key={item} className="text-[11px] text-slate-300 flex gap-2">
              <span className="text-cyan-500/70 shrink-0">·</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
      {footer && <div className="mt-3 pt-3 border-t border-slate-800/80">{footer}</div>}
    </div>
  );
}
