const COLORS: Record<string, string> = {
  Normal: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  Activa: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  Suspendida: "bg-red-500/20 text-red-300 border-red-500/40",
  "Al día": "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  Deuda: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  "Anomalía Predictiva": "bg-amber-500/20 text-amber-300 border-amber-500/40",
  Abierto: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
  "En Revisión": "bg-violet-500/20 text-violet-300 border-violet-500/40",
  Cerrado: "bg-slate-500/20 text-slate-400 border-slate-500/40",
  N1: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  N2: "bg-violet-500/20 text-violet-300 border-violet-500/40",
  Proveedor: "bg-amber-500/20 text-amber-300 border-amber-500/40",
  "Autónomo Predictivo": "bg-violet-500/20 text-violet-300 border-violet-500/40",
  "Reporte Cliente": "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
};

export function StatusBadge({ value }: { value: string }) {
  const cls =
    COLORS[value] || "bg-slate-600/30 text-slate-300 border-slate-500/30";
  return (
    <span
      className={`px-2 py-0.5 text-[10px] font-mono uppercase rounded border ${cls}`}
    >
      {value}
    </span>
  );
}
