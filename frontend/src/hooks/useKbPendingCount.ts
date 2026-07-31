"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";

type Listener = (count: number) => void;

let sharedCount = 0;
let inflight: Promise<number> | null = null;
const listeners = new Set<Listener>();

function notify(n: number) {
  sharedCount = n;
  listeners.forEach((l) => l(n));
}

/** Actualiza el contador compartido sin refetch (p. ej. tras cargar la campana). */
export function setKbPendingCount(n: number) {
  notify(n);
}

export async function refreshKbPendingCount(
  enabled: boolean,
  tenantSlug?: string,
): Promise<number> {
  if (!enabled) {
    notify(0);
    return 0;
  }
  if (inflight) return inflight;
  inflight = (async () => {
    try {
      const res = await api.kbContributions({ estado: "pendiente" }, tenantSlug);
      const n = (res.contribuciones || []).length;
      notify(n);
      return n;
    } catch {
      notify(0);
      return 0;
    } finally {
      inflight = null;
    }
  })();
  return inflight;
}

/**
 * Contador compartido de contribuciones KB pendientes (una sola fuente / poll).
 */
export function useKbPendingCount(enabled: boolean, tenantSlug?: string) {
  const [count, setCount] = useState(sharedCount);

  useEffect(() => {
    const listener: Listener = (n) => setCount(n);
    listeners.add(listener);
    setCount(sharedCount);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  const refresh = useCallback(() => {
    return refreshKbPendingCount(enabled, tenantSlug);
  }, [enabled, tenantSlug]);

  useEffect(() => {
    void refresh();
    if (!enabled) return;
    const id = window.setInterval(() => void refresh(), 45_000);
    return () => window.clearInterval(id);
  }, [enabled, refresh]);

  return { count, refresh };
}
