import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "../api";
import { formatUserError, isAuthExpired } from "../errors";
import type { ConnectivityStatusResponse } from "../types";

export function useConnectivity({
  token,
  onAuthExpired,
}: {
  token: string;
  onAuthExpired: () => void;
}) {
  const [data, setData] = useState<ConnectivityStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null);
  const inFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(
    async (serviceId?: string | null) => {
      if (!token || inFlight.current) return;
      inFlight.current = true;
      setLoading(true);
      setError("");
      const sid = (serviceId || "").trim() || undefined;
      try {
        const res = await api.getConnectivity(token, sid);
        if (!mounted.current) return;
        setData(res);
        if (res.service?.id) {
          setSelectedServiceId(res.service.id);
        } else if (res.needs_service_selection) {
          setSelectedServiceId(null);
        }
      } catch (err) {
        if (!mounted.current) return;
        if (isAuthExpired(err)) {
          onAuthExpired();
          return;
        }
        if (err instanceof ApiError && err.status === 404 && sid) {
          // 404 solo con service_id = servicio ajeno/inexistente.
          // Sin service_id, un 404 suele ser endpoint ausente (p.ej. API vieja/prod).
          setSelectedServiceId(null);
          setError("No encontramos ese servicio. Elegí otro o reintentá.");
          setData(null);
          return;
        }
        setError(
          formatUserError(
            err,
            "No pudimos consultar el estado de tu Internet. Intentá nuevamente.",
          ),
        );
        setData(null);
      } finally {
        inFlight.current = false;
        if (mounted.current) setLoading(false);
      }
    },
    [token, onAuthExpired],
  );

  useEffect(() => {
    void load(undefined);
  }, [load]);

  const selectService = useCallback(
    (serviceId: string) => {
      const id = serviceId.trim();
      if (!id) return;
      setSelectedServiceId(id);
      void load(id);
    },
    [load],
  );

  const refresh = useCallback(() => {
    void load(selectedServiceId);
  }, [load, selectedServiceId]);

  return {
    data,
    loading,
    error,
    selectedServiceId,
    selectService,
    refresh,
  };
}
