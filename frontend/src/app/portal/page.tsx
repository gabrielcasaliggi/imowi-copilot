"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type InboxConversation, type InboxMessage } from "@/lib/api-client";

const PORTAL_KEY = "ops_hub_portal_session";

type PortalStored = {
  token: string;
  convId: string;
};

function loadStored(): PortalStored | null {
  try {
    const raw = sessionStorage.getItem(PORTAL_KEY);
    return raw ? (JSON.parse(raw) as PortalStored) : null;
  } catch {
    return null;
  }
}

function saveStored(s: PortalStored | null) {
  if (!s) sessionStorage.removeItem(PORTAL_KEY);
  else sessionStorage.setItem(PORTAL_KEY, JSON.stringify(s));
}

export default function PortalPage() {
  const [telefono, setTelefono] = useState("5492235551234");
  const [dni, setDni] = useState("");
  const [token, setToken] = useState("");
  const [conv, setConv] = useState<InboxConversation | null>(null);
  const [mensajes, setMensajes] = useState<InboxMessage[]>([]);
  const [texto, setTexto] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const applyPayload = useCallback(
    (c: InboxConversation, msgs: InboxMessage[], portalToken: string) => {
      setConv(c);
      setMensajes(msgs);
      setToken(portalToken);
      saveStored({ token: portalToken, convId: c.id });
    },
    [],
  );

  const refresh = useCallback(async () => {
    const stored = loadStored();
    if (!stored?.token || !stored.convId) return;
    try {
      const data = await api.portalConversation(stored.convId, stored.token);
      setConv(data.conversacion);
      setMensajes(data.mensajes || []);
      setToken(stored.token);
    } catch {
      saveStored(null);
      setToken("");
      setConv(null);
      setMensajes([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!token || !conv?.id) return;
    if (conv.estado !== "con_agente" && conv.estado !== "espera_agente") return;
    const id = window.setInterval(() => {
      void refresh();
    }, 4000);
    return () => window.clearInterval(id);
  }, [token, conv?.id, conv?.estado, refresh]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes]);

  const onStart = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.portalSession({
        telefono: telefono.trim() || undefined,
        dni: dni.trim() || undefined,
        org_slug: "coop-batan",
      });
      applyPayload(res.conversacion, res.mensajes || [], res.portal_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar");
    } finally {
      setBusy(false);
    }
  };

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !texto.trim()) return;
    setBusy(true);
    setError("");
    const outgoing = texto.trim();
    setTexto("");
    try {
      const res = await api.portalSend(outgoing, token);
      if (res.conversacion) setConv(res.conversacion);
      setMensajes(res.mensajes || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al enviar");
      setTexto(outgoing);
    } finally {
      setBusy(false);
    }
  };

  const onReset = () => {
    saveStored(null);
    setToken("");
    setConv(null);
    setMensajes([]);
    setError("");
  };

  const estadoHint =
    conv?.estado === "espera_agente"
      ? "Tu caso está en cola. Un agente te va a atender por este chat."
      : conv?.estado === "con_agente"
        ? "Estás hablando con un agente de Cooperativa Batán."
        : conv?.estado === "cerrado"
          ? "Conversación cerrada. Podés iniciar una nueva."
          : "Asistente automático N1 · internet Ecolan, móvil y facturación.";

  return (
    <div className="min-h-screen flex flex-col bg-[var(--background)] text-slate-200">
      <header className="border-b border-slate-800/80 px-4 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center font-bold text-slate-950 shrink-0"
            style={{ background: "linear-gradient(135deg, #34d399, #22d3ee)" }}
          >
            B
          </div>
          <div className="min-w-0">
            <h1 className="font-semibold text-slate-100 truncate">Portal abonado</h1>
            <p className="text-[10px] font-mono text-slate-500 truncate">
              Cooperativa Batán · soporte web
            </p>
          </div>
        </div>
        <Link
          href="/login"
          className="text-[11px] font-mono text-slate-500 hover:text-slate-300"
        >
          Acceso agentes →
        </Link>
      </header>

      <main className="flex-1 flex flex-col max-w-lg mx-auto w-full p-4 gap-3">
        {!conv ? (
          <form
            onSubmit={onStart}
            className="rounded-2xl border border-slate-800 bg-slate-900/50 p-5 space-y-4 mt-6"
          >
            <div>
              <h2 className="text-lg font-semibold text-slate-50">Identificate</h2>
              <p className="text-sm text-slate-400 mt-1">
                Ingresá tu teléfono o DNI para hablar con el asistente. Si hace falta, un agente
                continúa el chat.
              </p>
            </div>
            <div>
              <label className="text-xs font-mono text-slate-500 block mb-1">Teléfono</label>
              <input
                value={telefono}
                onChange={(e) => setTelefono(e.target.value)}
                placeholder="5492235551234"
                className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-sm font-mono"
              />
            </div>
            <div>
              <label className="text-xs font-mono text-slate-500 block mb-1">DNI (opcional)</label>
              <input
                value={dni}
                onChange={(e) => setDni(e.target.value)}
                placeholder="30111222"
                className="w-full bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-sm font-mono"
              />
            </div>
            {error && <p className="text-sm text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={busy}
              className="w-full py-3 rounded-xl font-semibold text-slate-950 disabled:opacity-50"
              style={{ background: "var(--brand, #34d399)" }}
            >
              {busy ? "Conectando…" : "Iniciar chat"}
            </button>
            <p className="text-[10px] text-slate-600 font-mono">
              Demo: 5492235551234 / DNI 30111222 (María)
            </p>
          </form>
        ) : (
          <>
            <div className="flex justify-between items-start gap-2">
              <div>
                <p className="text-sm text-slate-100">
                  {conv.abonado?.nombre || "Abonado"} · {conv.telefono}
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">{estadoHint}</p>
              </div>
              <button
                type="button"
                onClick={onReset}
                className="text-[11px] text-slate-500 hover:text-slate-300"
              >
                Nueva sesión
              </button>
            </div>

            <div className="flex-1 min-h-[420px] rounded-2xl border border-slate-800 bg-slate-950/40 p-3 overflow-y-auto space-y-2">
              {mensajes.map((m) => (
                <div
                  key={m.id}
                  className={`max-w-[85%] px-3 py-2 rounded-xl text-sm ${
                    m.autor === "cliente"
                      ? "ml-auto bg-emerald-500/15 text-slate-100"
                      : m.autor === "agente"
                        ? "bg-violet-500/15 text-slate-100"
                        : "bg-slate-800/80 text-slate-300"
                  }`}
                >
                  <p className="text-[9px] font-mono uppercase text-slate-500 mb-0.5">
                    {m.autor === "cliente" ? "vos" : m.autor === "agente" ? "agente" : "asistente"}
                  </p>
                  <p className="whitespace-pre-wrap">{m.texto}</p>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>

            {error && <p className="text-sm text-red-400">{error}</p>}

            {conv.estado !== "cerrado" && (
              <form onSubmit={onSend} className="flex gap-2">
                <input
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  placeholder="Escribí tu mensaje…"
                  className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-sm"
                  disabled={busy}
                />
                <button
                  type="submit"
                  disabled={busy || !texto.trim()}
                  className="px-4 py-2 rounded-xl text-sm font-semibold text-slate-950 disabled:opacity-40"
                  style={{ background: "var(--brand, #34d399)" }}
                >
                  Enviar
                </button>
              </form>
            )}
          </>
        )}
      </main>
    </div>
  );
}
