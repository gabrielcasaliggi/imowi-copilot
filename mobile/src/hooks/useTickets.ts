import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import { formatUserError, isAuthExpired } from "../errors";
import type { PortalTicket, PortalTicketDetail } from "../types";

export function useTickets({
  token,
  onAuthExpired,
}: {
  token: string;
  onAuthExpired: () => void;
}) {
  const [items, setItems] = useState<PortalTicket[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<PortalTicketDetail | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const inFlight = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(
    async (mode: "initial" | "refresh") => {
      if (!token || inFlight.current) return;
      inFlight.current = true;
      if (mode === "initial") setLoading(true);
      else setRefreshing(true);
      setError("");
      try {
        const res = await api.listTickets(token);
        if (!mounted.current) return;
        setItems(res.items || []);
      } catch (err) {
        if (!mounted.current) return;
        if (isAuthExpired(err)) {
          onAuthExpired();
          return;
        }
        setError(
          formatUserError(err, "No pudimos cargar tus tickets. Intentá nuevamente."),
        );
      } finally {
        inFlight.current = false;
        if (mounted.current) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    },
    [token, onAuthExpired],
  );

  useEffect(() => {
    void load("initial");
  }, [load]);

  const refresh = useCallback(() => {
    void load("refresh");
  }, [load]);

  const openDetail = useCallback(
    async (ticketId: string) => {
      if (!token || detailBusy) return;
      setDetailBusy(true);
      setError("");
      try {
        const res = await api.getTicket(ticketId, token);
        if (mounted.current) setDetail(res);
      } catch (err) {
        if (!mounted.current) return;
        if (isAuthExpired(err)) {
          onAuthExpired();
          return;
        }
        setError(
          formatUserError(err, "No pudimos abrir el ticket. Intentá nuevamente."),
        );
      } finally {
        if (mounted.current) setDetailBusy(false);
      }
    },
    [token, detailBusy, onAuthExpired],
  );

  const closeDetail = useCallback(() => setDetail(null), []);

  return {
    items,
    loading,
    refreshing,
    error,
    setError,
    refresh,
    detail,
    detailBusy,
    openDetail,
    closeDetail,
  };
}
