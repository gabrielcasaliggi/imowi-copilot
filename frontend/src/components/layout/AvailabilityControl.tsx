"use client";

import { useEffect, useState } from "react";
import { useApp } from "@/contexts/AppContext";
import { api } from "@/lib/api-client";

const OPTIONS = [
  { value: "disponible", label: "Disponible", tone: "border-emerald-500/40 text-emerald-200" },
  { value: "ocupado", label: "Ocupado", tone: "border-amber-500/40 text-amber-200" },
  { value: "ausente", label: "Ausente", tone: "border-slate-500/40 text-slate-300" },
] as const;

export function AvailabilityControl() {
  const { can } = useApp();
  const [value, setValue] = useState("disponible");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const raw = window.sessionStorage.getItem("ops_hub_disponibilidad");
    if (raw && OPTIONS.some((o) => o.value === raw)) setValue(raw);
  }, []);

  if (!can("agent.availability")) return null;

  const onChange = async (next: string) => {
    setBusy(true);
    try {
      const res = await api.setAvailability(next);
      setValue(res.disponibilidad || next);
      window.sessionStorage.setItem("ops_hub_disponibilidad", res.disponibilidad || next);
    } catch {
      /* ignore — el select vuelve al valor previo en siguiente render si falla */
    } finally {
      setBusy(false);
    }
  };

  const tone = OPTIONS.find((o) => o.value === value)?.tone || OPTIONS[0].tone;

  return (
    <select
      value={value}
      disabled={busy}
      onChange={(e) => void onChange(e.target.value)}
      className={`bg-slate-950 border rounded-lg px-2 py-1.5 text-[11px] font-mono outline-none disabled:opacity-50 ${tone}`}
      title="Estado de disponibilidad"
      aria-label="Disponibilidad"
    >
      {OPTIONS.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
