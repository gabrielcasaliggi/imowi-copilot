import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api";
import { formatUserError, isAuthExpired } from "../errors";
import type { PortalTicketDetail } from "../types";

/** Detalle de un reclamo del abonado (GET /portal/tickets/{id}). 404 = ajeno o inexistente. */
export function useTicketDetail({
  ticketId,
  token,
  onAuthExpired,
}: {
  ticketId: string;
  token: string;
  onAuthExpired: () => void;
}) {
  const [detail, setDetail] = useState<PortalTicketDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const inFlight = useRef(false);
  const mounted = useRef(true);
  // En una ref: el padre recrea onAuthExpired en cada render y no debe recargar el detalle.
  const authExpiredRef = useRef(onAuthExpired);
  authExpiredRef.current = onAuthExpired;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      const tid = (ticketId || "").trim();
      if (!token || !tid || inFlight.current) return;
      inFlight.current = true;
      if (mode === "initial") setLoading(true);
      else setRefreshing(true);
      setError("");
      try {
        const res = await api.getTicket(tid, token);
        if (mounted.current) setDetail(res);
      } catch (err) {
        if (!mounted.current) return;
        if (isAuthExpired(err)) {
          authExpiredRef.current();
          return;
        }
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
          return;
        }
        setError(formatUserError(err, "No pudimos cargar el reclamo. Intentá nuevamente."));
      } finally {
        inFlight.current = false;
        if (mounted.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [ticketId, token],
  );

  useEffect(() => {
    setDetail(null);
    setNotFound(false);
    void load("initial");
  }, [load]);

  const refresh = useCallback(() => {
    void load("refresh");
  }, [load]);

  const retry = useCallback(() => {
    void load(detail ? "refresh" : "initial");
  }, [load, detail]);

  return { detail, loading, refreshing, error, notFound, refresh, retry };
}
