import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { formatUserError, isAuthExpired } from "../errors";
import { getToken } from "../session";
import type { InboxConversation, InboxMessage } from "../types";

export function useConversation({
  token,
  conv,
  mensajes,
  onChange,
  onAuthExpired,
}: {
  token: string;
  conv: InboxConversation;
  mensajes: InboxMessage[];
  onChange: (conv: InboxConversation | null, mensajes?: InboxMessage[]) => void;
  onAuthExpired: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const handleAuthError = useCallback(
    (err: unknown) => {
      if (isAuthExpired(err)) {
        onAuthExpired();
        return true;
      }
      return false;
    },
    [onAuthExpired],
  );

  const refresh = useCallback(async () => {
    const t = token || (await getToken());
    if (!t || !conv.id) return;
    try {
      const data = await api.conversation(conv.id, t);
      onChange(data.conversacion, data.mensajes || []);
    } catch (err) {
      if (handleAuthError(err)) return;
    }
  }, [conv.id, token, onChange, handleAuthError]);

  const esperaAgente = conv.estado === "espera_agente";
  const conAgente = conv.estado === "con_agente";

  useEffect(() => {
    if (!esperaAgente && !conAgente) return;
    const id = setInterval(() => {
      void refresh();
    }, 4000);
    return () => clearInterval(id);
  }, [esperaAgente, conAgente, refresh]);

  const send = useCallback(
    async (value: string) => {
      const outgoing = value.trim();
      if (!outgoing || busy) return false;
      setError("");
      setBusy(true);
      onChange(conv, [
        ...mensajes,
        {
          id: `local-${Date.now()}`,
          conversacion_id: conv.id,
          autor: "cliente",
          texto: outgoing,
          direccion: "in",
          created_at: new Date().toISOString(),
        },
      ]);
      try {
        const res = await api.send(outgoing, token);
        onChange(res.conversacion, res.mensajes || []);
        return true;
      } catch (err) {
        if (handleAuthError(err)) return false;
        setError(formatUserError(err, "No pudimos enviar el mensaje. Intentá nuevamente."));
        onChange(
          conv,
          mensajes.filter((m) => !String(m.id).startsWith("local-")),
        );
        return false;
      } finally {
        setBusy(false);
      }
    },
    [busy, conv, mensajes, token, onChange, handleAuthError],
  );

  const sendVoice = useCallback(
    async (uri: string) => {
      if (!uri || busy) return false;
      setError("");
      setBusy(true);
      try {
        const res = await api.sendAudio(uri, token);
        onChange(res.conversacion, res.mensajes || []);
        return true;
      } catch (err) {
        if (handleAuthError(err)) return false;
        setError(
          formatUserError(err, "No pudimos procesar el audio. Revisá tu conexión e intentá nuevamente."),
        );
        return false;
      } finally {
        setBusy(false);
      }
    },
    [busy, token, onChange, handleAuthError],
  );

  return { busy, error, setError, send, sendVoice, refresh, esperaAgente, conAgente };
}
