import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { formatUserError, isAuthExpired } from "../errors";
import { projectInvoiceList } from "../invoicesView";
import type { PortalInvoicesResponse } from "../types";

/** Lectura independiente del saldo. No envía identidad en el query. */
export function useInvoices({
  token,
  onAuthExpired,
}: {
  token: string;
  onAuthExpired: () => void;
}) {
  const [data, setData] = useState<PortalInvoicesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    if (!token || inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError("");
    try {
      const res = await api.getInvoices(token);
      if (!mounted.current) return;
      setData({
        status: res.status,
        reason_code: res.reason_code ?? null,
        invoices: projectInvoiceList(res.invoices),
      });
    } catch (err) {
      if (!mounted.current) return;
      if (isAuthExpired(err)) {
        onAuthExpired();
        return;
      }
      setError(
        formatUserError(
          err,
          "No pudimos consultar tus facturas. Intentá nuevamente.",
        ),
      );
      setData(null);
    } finally {
      inFlight.current = false;
      if (mounted.current) setLoading(false);
    }
  }, [token, onAuthExpired]);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = useCallback(() => {
    void load();
  }, [load]);

  return { data, loading, error, refresh };
}
