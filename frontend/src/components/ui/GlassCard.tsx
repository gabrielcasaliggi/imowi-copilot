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

export function KpiCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3">
      <p className="text-[10px] uppercase tracking-wider font-mono text-slate-500">
        {label}
      </p>
      <p className="text-2xl font-semibold text-slate-100 mt-1">{value}</p>
    </div>
  );
}
