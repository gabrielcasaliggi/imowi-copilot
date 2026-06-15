import type { ReactNode } from "react";

export function GlassCard({
  title,
  children,
  accent,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  accent?: "cyan" | "amber" | "emerald" | "default";
  className?: string;
}) {
  const border =
    accent === "cyan"
      ? "border-cyan-500/20 bg-cyan-500/5"
      : accent === "amber"
        ? "border-amber-500/20 bg-amber-500/5"
        : accent === "emerald"
          ? "border-emerald-500/20 bg-emerald-500/5"
          : "border-slate-800 bg-slate-900/40";

  return (
    <div className={`rounded-2xl border p-4 ${border} ${className}`}>
      {title && (
        <h3
          className={`text-xs font-mono uppercase tracking-wider mb-2 ${
            accent === "cyan"
              ? "text-cyan-400/90"
              : accent === "amber"
                ? "text-amber-300/90"
                : accent === "emerald"
                  ? "text-emerald-300/90"
                  : "text-slate-500"
          }`}
        >
          {title}
        </h3>
      )}
      {children}
    </div>
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
      <p className="text-[10px] uppercase tracking-wider font-mono text-slate-500">
        {label}
      </p>
      <p className={`text-2xl font-semibold mt-1 tabular-nums ${valueClass}`}>{value}</p>
      {helper && <p className="text-[10px] text-slate-500 mt-1">{helper}</p>}
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
