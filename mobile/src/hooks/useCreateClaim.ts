import { useCallback, useRef, useState } from "react";

import { api } from "../api";
import { formatUserError, isAuthExpired } from "../errors";
import type { PortalTicketDetail } from "../types";

/**
 * Crear reclamo controlado. Guarda inFlight para evitar doble POST por doble tap.
 */
export function useCreateClaim({
  token,
  onAuthExpired,
}: {
  token: string;
  onAuthExpired: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);

  const create = useCallback(
    async (input: {
      motivo: string;
      descripcion: string;
    }): Promise<PortalTicketDetail | null> => {
      if (!token || inFlight.current) return null;
      const motivo = input.motivo.trim();
      const descripcion = input.descripcion.trim();
      if (!motivo || !descripcion) {
        setError("Completá el motivo y la descripción.");
        return null;
      }
      inFlight.current = true;
      setBusy(true);
      setError("");
      try {
        const res = await api.createTicket(token, { motivo, descripcion });
        return res;
      } catch (err) {
        if (isAuthExpired(err)) {
          onAuthExpired();
          return null;
        }
        setError(
          formatUserError(
            err,
            "No pudimos crear el reclamo. Intentá nuevamente.",
          ),
        );
        return null;
      } finally {
        inFlight.current = false;
        setBusy(false);
      }
    },
    [token, onAuthExpired],
  );

  const clearError = useCallback(() => setError(""), []);

  return { create, busy, error, setError, clearError };
}
