"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type ToastTone = "info" | "success" | "warning" | "danger";

type ToastItem = {
  id: number;
  message: string;
  tone: ToastTone;
};

type ToastContextValue = {
  push: (message: string, tone?: ToastTone) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

const TONE_CLS: Record<ToastTone, string> = {
  info: "border-ecolan-brand/40 bg-slate-900 text-slate-100",
  success: "border-emerald-500/40 bg-slate-900 text-emerald-100",
  warning: "border-amber-500/40 bg-slate-900 text-amber-100",
  danger: "border-red-500/40 bg-slate-900 text-red-100",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const push = useCallback((message: string, tone: ToastTone = "info") => {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setItems((prev) => [...prev.slice(-4), { id, message, tone }]);
    window.setTimeout(() => {
      setItems((prev) => prev.filter((t) => t.id !== id));
    }, 4200);
  }, []);

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="fixed bottom-4 right-4 z-[80] flex flex-col gap-2 max-w-sm w-[calc(100%-2rem)] pointer-events-none"
        aria-live="polite"
        aria-relevant="additions"
      >
        {items.map((t) => (
          <div
            key={t.id}
            role="status"
            className={`pointer-events-auto rounded-xl border px-3.5 py-2.5 text-sm shadow-none ${TONE_CLS[t.tone]}`}
          >
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    return {
      push: (message: string) => {
        if (typeof window !== "undefined") console.warn("[toast]", message);
      },
    };
  }
  return ctx;
}
