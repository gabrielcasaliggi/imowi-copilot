const COLORS: Record<string, string> = {
  Normal: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-50/10 dark:text-emerald-300 dark:border-emerald-500/35",
  Activa: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-50/10 dark:text-emerald-300 dark:border-emerald-500/35",
  Suspendida: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-50/10 dark:text-rose-300 dark:border-rose-500/35",
  "Al día": "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-50/10 dark:text-emerald-300 dark:border-emerald-500/35",
  Deuda: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-50/10 dark:text-amber-300 dark:border-amber-500/35",
  "Anomalía Predictiva": "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-50/10 dark:text-amber-300 dark:border-amber-500/35",
  Abierto: "bg-teal-50 text-teal-800 border-teal-200 dark:bg-ecolan-brand/15 dark:text-ecolan-brand dark:border-ecolan-brand/40",
  "En Revisión": "bg-gray-100 text-gray-700 border-gray-200 dark:bg-slate-500/15 dark:text-slate-300 dark:border-slate-500/35",
  Escalado: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-50/10 dark:text-amber-300 dark:border-amber-500/35",
  "Pendiente Cliente": "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-50/10 dark:text-sky-300 dark:border-sky-500/35",
  Cerrado: "bg-gray-100 text-gray-600 border-gray-200 dark:bg-slate-500/15 dark:text-slate-400 dark:border-slate-500/30",
  Cerrada: "bg-gray-100 text-gray-600 border-gray-200 dark:bg-slate-500/15 dark:text-slate-400 dark:border-slate-500/30",
  N1: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-50/10 dark:text-emerald-300 dark:border-emerald-500/35",
  N2: "bg-teal-50 text-teal-800 border-teal-200 dark:bg-ecolan-brand/15 dark:text-ecolan-brand dark:border-ecolan-brand/40",
  Proveedor: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-50/10 dark:text-amber-300 dark:border-amber-500/35",
  "Autónomo Predictivo": "bg-teal-50 text-teal-800 border-teal-200 dark:bg-ecolan-brand/15 dark:text-ecolan-brand dark:border-ecolan-brand/40",
  "Reporte Cliente": "bg-teal-50 text-teal-800 border-teal-200 dark:bg-ecolan-brand/15 dark:text-ecolan-brand dark:border-ecolan-brand/40",
  "Bot N1": "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-50/10 dark:text-emerald-300 dark:border-emerald-500/35",
  "Espera agente": "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-50/10 dark:text-amber-300 dark:border-amber-500/35",
  "Con agente": "bg-teal-50 text-teal-800 border-teal-200 dark:bg-ecolan-brand/15 dark:text-ecolan-brand dark:border-ecolan-brand/40",
};

export function StatusBadge({ value }: { value: string }) {
  const cls =
    COLORS[value] ||
    "bg-gray-100 text-gray-700 border-gray-200 dark:bg-slate-600/20 dark:text-slate-300 dark:border-slate-500/30";
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide rounded-full border transition-all duration-200 ease-in-out ${cls}`}
    >
      {value}
    </span>
  );
}
