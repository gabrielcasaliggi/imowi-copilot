"use client";

import { useState } from "react";

/** Estrellas ☆ apagadas; hover/tap ilumina de 1 hasta la elegida. */
export function StarRatingInput({
  onSelect,
  disabled,
  label = "¿Cómo calificarías la atención recibida hoy?",
}: {
  onSelect: (n: number) => void | Promise<void>;
  disabled?: boolean;
  label?: string;
}) {
  const [hover, setHover] = useState(0);
  const [selected, setSelected] = useState(0);
  const [busy, setBusy] = useState(false);
  const lit = hover || selected;

  const pick = async (n: number) => {
    if (disabled || busy) return;
    setSelected(n);
    setBusy(true);
    try {
      await onSelect(n);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-700/80 bg-slate-900/50 px-4 py-3 space-y-2">
      <p className="text-sm text-slate-200">{label}</p>
      <div
        className="flex items-center justify-center gap-1.5 py-1"
        onMouseLeave={() => !selected && setHover(0)}
        role="group"
        aria-label="Calificación de 1 a 5 estrellas"
      >
        {[1, 2, 3, 4, 5].map((n) => {
          const on = n <= lit;
          return (
            <button
              key={n}
              type="button"
              disabled={disabled || busy || selected > 0}
              onMouseEnter={() => !selected && setHover(n)}
              onFocus={() => !selected && setHover(n)}
              onClick={() => void pick(n)}
              className={
                "text-3xl leading-none transition-colors duration-150 ease-out " +
                "disabled:cursor-default focus:outline-none focus-visible:ring-2 " +
                "focus-visible:ring-ecolan-brand/50 rounded-md px-0.5 " +
                (on ? "text-amber-400 drop-shadow-[0_0_6px_rgba(251,191,36,0.35)]" : "text-slate-600")
              }
              aria-label={`${n} ${n === 1 ? "estrella" : "estrellas"}`}
            >
              ★
            </button>
          );
        })}
      </div>
      <p className="text-[11px] text-center text-slate-500 font-mono">
        {selected
          ? `${"★".repeat(selected)}${"☆".repeat(5 - selected)}`
          : hover
            ? `${"★".repeat(hover)}${"☆".repeat(5 - hover)}`
            : "☆☆☆☆☆ · pasá el mouse o tocá"}
      </p>
    </div>
  );
}
