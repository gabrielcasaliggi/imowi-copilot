"use client";

import { useEffect, useState } from "react";
import { useApp } from "@/contexts/AppContext";
import { api } from "@/lib/api-client";
import { useToast } from "@/components/ui/Toast";

const OPTIONS = [
  { value: "disponible", label: "Disponible", tone: "border-emerald-500/40 text-emerald-200" },
  { value: "ocupado", label: "Ocupado", tone: "border-amber-500/40 text-amber-200" },
  { value: "ausente", label: "Ausente", tone: "border-slate-500/40 text-slate-300" },
] as const;

export function AvailabilityControl() {
  const { can } = useApp();
  const { push: toast } = useToast();
  const [value, setValue] = useState("disponible");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const raw = window.sessionStorage.getItem("ops_hub_disponibilidad");
    if (raw && OPTIONS.some((o) => o.value === raw)) setValue(raw);
  }, []);

  if (!can("agent.availability")) return null;

  const onChange = async (next: string) => {
    const prev = value;
    setValue(next);
    setBusy(true);
    try {
      const res = await api.setAvailability(next);
      const resolved = res.disponibilidad || next;
      setValue(resolved);
      window.sessionStorage.setItem("ops_hub_disponibilidad", resolved);
    } catch (err) {
      setValue(prev);
      toast(
        err instanceof Error ? err.message : "No se pudo actualizar la disponibilidad",
        "danger",
      );
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
      className={`bg-slate-950 border rounded-lg px-2 py-1.5 text-[11px] font-mono disabled:opacity-50 ${tone}`}
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
