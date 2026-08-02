const COLORS: Record<string, string> = {
  Normal: "bg-emerald-50/10 text-emerald-300 border-emerald-500/35",
  Activa: "bg-emerald-50/10 text-emerald-300 border-emerald-500/35",
  Suspendida: "bg-rose-50/10 text-rose-300 border-rose-500/35",
  "Al día": "bg-emerald-50/10 text-emerald-300 border-emerald-500/35",
  Deuda: "bg-amber-50/10 text-amber-300 border-amber-500/35",
  "Anomalía Predictiva": "bg-amber-50/10 text-amber-300 border-amber-500/35",
  Abierto: "bg-ecolan-brand/15 text-ecolan-brand border-ecolan-brand/40",
  "En Revisión": "bg-slate-500/15 text-slate-300 border-slate-500/35",
  Escalado: "bg-amber-50/10 text-amber-300 border-amber-500/35",
  "Pendiente Cliente": "bg-sky-50/10 text-sky-300 border-sky-500/35",
  Cerrado: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  Cerrada: "bg-slate-500/15 text-slate-400 border-slate-500/30",
  N1: "bg-emerald-50/10 text-emerald-300 border-emerald-500/35",
  N2: "bg-ecolan-brand/15 text-ecolan-brand border-ecolan-brand/40",
  Proveedor: "bg-amber-50/10 text-amber-300 border-amber-500/35",
  "Autónomo Predictivo": "bg-ecolan-brand/15 text-ecolan-brand border-ecolan-brand/40",
  "Reporte Cliente": "bg-ecolan-brand/15 text-ecolan-brand border-ecolan-brand/40",
  // Inbox / canal
  "Bot N1": "bg-emerald-50/10 text-emerald-300 border-emerald-500/35",
  "Espera agente": "bg-amber-50/10 text-amber-300 border-amber-500/35",
  "Con agente": "bg-ecolan-brand/15 text-ecolan-brand border-ecolan-brand/40",
};

export function StatusBadge({ value }: { value: string }) {
  const cls =
    COLORS[value] || "bg-slate-600/20 text-slate-300 border-slate-500/30";
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 text-[10px] font-mono font-medium uppercase tracking-wide rounded-full border transition-all duration-200 ease-in-out ${cls}`}
    >
      {value}
    </span>
  );
}
