import { useCallback, useEffect, useState } from "react";

import { api } from "../api";
import { formatUserError, isAuthExpired } from "../errors";
import { clearSession, loadSession } from "../session";
import { defaultBranding, type Branding } from "../theme";
import type { AuthPayload, InboxConversation, InboxMessage } from "../types";

export function useSession() {
  const [branding, setBranding] = useState<Branding>(defaultBranding);
  const [booting, setBooting] = useState(true);
  const [bootError, setBootError] = useState("");
  const [token, setToken] = useState("");
  const [needPin, setNeedPin] = useState(false);
  const [conv, setConv] = useState<InboxConversation | null>(null);
  const [mensajes, setMensajes] = useState<InboxMessage[]>([]);

  useEffect(() => {
    void api.branding().then(setBranding).catch(() => {});
  }, []);

  const restore = useCallback(async () => {
    setBootError("");
    const stored = await loadSession();
    if (!stored) return;
    try {
      const data = await api.conversation(stored.convId, stored.token);
      setToken(stored.token);
      setConv(data.conversacion);
      setMensajes(data.mensajes || []);
    } catch (err) {
      if (isAuthExpired(err)) {
        await clearSession();
        return;
      }
      setBootError(
        formatUserError(err, "No pudimos conectar. Revisá tu conexión e intentá nuevamente."),
      );
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        await restore();
      } finally {
        setBooting(false);
      }
    })();
  }, [restore]);

  const retryBoot = useCallback(async () => {
    setBooting(true);
    try {
      await restore();
    } finally {
      setBooting(false);
    }
  }, [restore]);

  const onAuthed = useCallback((payload: AuthPayload) => {
    setToken(payload.portal_token);
    setConv(payload.conversacion);
    setMensajes(payload.mensajes || []);
    setNeedPin(payload.has_pin === false);
    setBootError("");
  }, []);

  const onExit = useCallback(async () => {
    await clearSession();
    setToken("");
    setConv(null);
    setMensajes([]);
    setNeedPin(false);
    setBootError("");
  }, []);

  const applyConversation = useCallback(
    (nextConv: InboxConversation | null, nextMensajes?: InboxMessage[]) => {
      if (nextConv) setConv(nextConv);
      if (nextMensajes) setMensajes(nextMensajes);
    },
    [],
  );

  return {
    branding,
    booting,
    bootError,
    retryBoot,
    token,
    needPin,
    setNeedPin,
    conv,
    mensajes,
    onAuthed,
    onExit,
    applyConversation,
  };
}
