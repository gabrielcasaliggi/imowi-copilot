"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, type InboxConversation, type InboxMessage } from "@/lib/api-client";
import { StatusBadge } from "@/components/ui/StatusBadge";
import {
  ChatMessageBubble,
  ChatTypingIndicator,
  SendIcon,
} from "@/components/ui/ChatMessageBubble";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { botEstadoLabel, getBranding } from "@/lib/brand";

const PORTAL_KEY = "ops_hub_portal_session";
const showDemo =
  process.env.NODE_ENV !== "production" &&
  process.env.NEXT_PUBLIC_APP_ENV !== "production";

type PortalStored = {
  token: string;
  convId: string;
};

type Step = "auth" | "otp" | "chat" | "pin-setup";

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

function canalEstadoLabel(estado: string): string {
  switch (estado) {
    case "bot":
      return botEstadoLabel();
    case "espera_agente":
      return "Espera agente";
    case "con_agente":
      return "Con agente";
    case "cerrado":
      return "Cerrada";
    default:
      return estado;
  }
}

export default function PortalPage() {
  const [step, setStep] = useState<Step>("auth");
  const [mode, setMode] = useState<"dni" | "pin" | "guest">("dni");
  const [dni, setDni] = useState("");
  const [pin, setPin] = useState("");
  const [otp, setOtp] = useState("");
  const [challengeId, setChallengeId] = useState("");
  const [contactMasked, setContactMasked] = useState("");
  const [token, setToken] = useState("");
  const [conv, setConv] = useState<InboxConversation | null>(null);
  const [mensajes, setMensajes] = useState<InboxMessage[]>([]);
  const [texto, setTexto] = useState("");
  const [busy, setBusy] = useState(false);
  const [botTyping, setBotTyping] = useState(false);
  const [error, setError] = useState("");
  const [modoInvitado, setModoInvitado] = useState(false);
  const [newPin, setNewPin] = useState("");
  const [otpInfo, setOtpInfo] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const applyPayload = useCallback(
    (c: InboxConversation, msgs: InboxMessage[], portalToken: string, guest = false) => {
      setConv(c);
      setMensajes(msgs);
      setToken(portalToken);
      setModoInvitado(guest);
      setStep("chat");
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
      setStep("chat");
    } catch {
      saveStored(null);
      setToken("");
      setConv(null);
      setMensajes([]);
      setStep("auth");
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
  }, [mensajes, botTyping]);

  const onStartDni = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.portalAuthStart({
        dni: dni.trim(),
        org_slug: "coop-batan",
      });
      setChallengeId(res.challenge_id);
      setContactMasked(res.contact_masked);
      if (res.debug_otp) setOtp(res.debug_otp);
      setOtpInfo("");
      setStep("otp");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar");
    } finally {
      setBusy(false);
    }
  };

  const onResendOtp = async () => {
    if (!dni.trim()) return;
    setBusy(true);
    setError("");
    setOtpInfo("");
    try {
      const res = await api.portalAuthStart({
        dni: dni.trim(),
        org_slug: "coop-batan",
      });
      setChallengeId(res.challenge_id);
      setContactMasked(res.contact_masked);
      if (res.debug_otp) setOtp(res.debug_otp);
      else setOtp("");
      setOtpInfo("Te enviamos un código nuevo.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo reenviar el código");
    } finally {
      setBusy(false);
    }
  };

  const onVerifyOtp = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.portalAuthVerify({
        challenge_id: challengeId,
        otp: otp.trim(),
        org_slug: "coop-batan",
      });
      applyPayload(res.conversacion, res.mensajes || [], res.portal_token, false);
      if (!res.has_pin) setStep("pin-setup");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Código incorrecto");
    } finally {
      setBusy(false);
    }
  };

  const onPinLogin = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.portalLoginPin({
        dni: dni.trim(),
        pin: pin.trim(),
        org_slug: "coop-batan",
      });
      applyPayload(res.conversacion, res.mensajes || [], res.portal_token, false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo ingresar");
    } finally {
      setBusy(false);
    }
  };

  const onGuest = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await api.portalSession({ org_slug: "coop-batan" });
      applyPayload(res.conversacion, res.mensajes || [], res.portal_token, true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar");
    } finally {
      setBusy(false);
    }
  };

  const onSetPin = async (e: FormEvent) => {
    e.preventDefault();
    if (!token) return;
    setBusy(true);
    setError("");
    try {
      await api.portalSetPin(newPin.trim(), token);
      setStep("chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo guardar el PIN");
    } finally {
      setBusy(false);
    }
  };

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !texto.trim() || botTyping) return;
    setError("");
    const outgoing = texto.trim();
    setTexto("");
    setMensajes((prev) => [
      ...prev,
      {
        id: `local-${Date.now()}`,
        conversacion_id: conv?.id || "",
        autor: "cliente",
        texto: outgoing,
        direccion: "in",
        meta_message_id: "",
        created_at: new Date().toISOString(),
      },
    ]);
    setBotTyping(true);
    try {
      const res = await api.portalSend(outgoing, token);
      if (res.conversacion) setConv(res.conversacion);
      setMensajes(res.mensajes || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al enviar");
      setTexto(outgoing);
      setMensajes((prev) => prev.filter((m) => !String(m.id).startsWith("local-")));
    } finally {
      setBotTyping(false);
    }
  };

  const onExit = () => {
    saveStored(null);
    setToken("");
    setConv(null);
    setMensajes([]);
    setStep("auth");
    setOtp("");
    setChallengeId("");
    setOtpInfo("");
  };

  const esperaAgente = conv?.estado === "espera_agente";
  const conAgente = conv?.estado === "con_agente";

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col transition-colors duration-200">
      <header className="border-b border-slate-800/80 px-4 py-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold tracking-tight">Portal abonado · Cooperativa Batán</p>
          <p className="text-[10px] font-medium text-slate-500">Ecolan + IMOVI · soporte</p>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle compact />
          {token && (
            <button
              type="button"
              onClick={onExit}
              className="text-xs text-slate-500 hover:text-slate-200 transition-colors duration-200"
            >
              Salir
            </button>
          )}
        </div>
      </header>

      <main className="flex-1 flex flex-col max-w-lg mx-auto w-full p-4 gap-4">
        {step === "auth" && (
          <div className="rounded-2xl border border-slate-700/80 bg-slate-900/50 p-6 space-y-4 shadow-sm">
            <h1 className="text-lg font-semibold">Ingresá al portal</h1>
            <p className="text-xs text-slate-400">
              Validamos tu DNI contra el padrón y te enviamos un código al email registrado.
            </p>
            <div className="flex gap-2 text-xs" role="tablist" aria-label="Modo de ingreso">
              <button
                type="button"
                role="tab"
                aria-selected={mode === "dni"}
                className={`px-3 py-1.5 rounded-lg transition-all duration-200 ease-in-out ${mode === "dni" ? "bg-ecolan-brand/15 text-ecolan-brand font-medium" : "text-slate-400 hover:text-slate-200"}`}
                onClick={() => setMode("dni")}
              >
                DNI + OTP
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === "pin"}
                className={`px-3 py-1.5 rounded-lg transition-all duration-200 ease-in-out ${mode === "pin" ? "bg-ecolan-brand/15 text-ecolan-brand font-medium" : "text-slate-400 hover:text-slate-200"}`}
                onClick={() => setMode("pin")}
              >
                DNI + PIN
              </button>
            </div>

            {mode === "dni" ? (
              <form onSubmit={onStartDni} className="space-y-3">
                <div>
                  <label htmlFor="portal-dni" className="text-xs font-medium text-slate-500 block mb-1.5">
                    DNI
                  </label>
                  <input
                    id="portal-dni"
                    value={dni}
                    onChange={(e) => setDni(e.target.value)}
                    placeholder="Solo números"
                    inputMode="numeric"
                    className="w-full bg-slate-950/80 border border-slate-600/80 rounded-xl px-4 py-2.5 text-sm tabular-nums transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent"
                    required
                  />
                </div>
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full py-2.5 rounded-xl font-semibold text-white bg-ecolan-brand hover:bg-ecolan-brand-dark disabled:opacity-50 shadow-sm transition-all duration-200 ease-in-out"
                >
                  {busy ? "Verificando…" : "Continuar"}
                </button>
              </form>
            ) : (
              <form onSubmit={onPinLogin} className="space-y-3">
                <div>
                  <label htmlFor="portal-dni-pin" className="text-xs font-medium text-slate-500 block mb-1.5">
                    DNI
                  </label>
                  <input
                    id="portal-dni-pin"
                    value={dni}
                    onChange={(e) => setDni(e.target.value)}
                    placeholder="Solo números"
                    inputMode="numeric"
                    className="w-full bg-slate-950/80 border border-slate-600/80 rounded-xl px-4 py-2.5 text-sm tabular-nums transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent"
                    required
                  />
                </div>
                <div>
                  <label htmlFor="portal-pin" className="text-xs font-medium text-slate-500 block mb-1.5">
                    PIN
                  </label>
                  <input
                    id="portal-pin"
                    type="password"
                    inputMode="numeric"
                    value={pin}
                    onChange={(e) => setPin(e.target.value)}
                    placeholder="6–8 dígitos"
                    className="w-full bg-slate-950/80 border border-slate-600/80 rounded-xl px-4 py-2.5 text-sm tabular-nums transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent"
                    required
                  />
                </div>
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full py-2.5 rounded-xl font-semibold text-white bg-ecolan-brand hover:bg-ecolan-brand-dark disabled:opacity-50 shadow-sm transition-all duration-200 ease-in-out"
                >
                  {busy ? "Ingresando…" : "Ingresar"}
                </button>
              </form>
            )}

            <button
              type="button"
              onClick={() => void onGuest()}
              disabled={busy}
              className="w-full text-xs text-slate-400 hover:text-slate-300 py-2"
            >
              Continuar como invitado (sin datos de cuenta)
            </button>

            {showDemo && (
              <p className="text-[10px] font-mono text-slate-500">
                Dev: DNI demo 30111222 (OTP en respuesta debug)
              </p>
            )}
          </div>
        )}

        {step === "otp" && (
          <form onSubmit={onVerifyOtp} className="rounded-2xl border border-slate-700/80 bg-slate-900/50 p-6 space-y-4 shadow-sm">
            <h1 className="text-lg font-semibold">Código de verificación</h1>
            <p className="text-xs text-slate-400">
              Enviamos un código a <span className="font-mono text-slate-300">{contactMasked}</span>
            </p>
            <div>
              <label htmlFor="portal-otp" className="text-xs font-medium text-slate-500 block mb-1.5">
                Código OTP
              </label>
              <input
                id="portal-otp"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                placeholder="Ingresá el código"
                inputMode="numeric"
                autoComplete="one-time-code"
                className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono tracking-widest"
                required
              />
            </div>
            {otpInfo && (
              <p className="text-xs text-ecolan-brand" role="status">
                {otpInfo}
              </p>
            )}
            <button
              type="submit"
              disabled={busy}
              className="w-full py-2.5 rounded-xl font-semibold text-white bg-ecolan-brand hover:bg-ecolan-brand-dark disabled:opacity-50 shadow-sm transition-all duration-200 ease-in-out"
            >
              {busy ? "Validando…" : "Verificar"}
            </button>
            <div className="flex justify-between gap-3">
              <button
                type="button"
                className="text-xs text-slate-400 hover:text-slate-200"
                onClick={() => setStep("auth")}
              >
                Volver
              </button>
              <button
                type="button"
                disabled={busy}
                className="text-xs text-emerald-400/90 hover:text-ecolan-brand disabled:opacity-50"
                onClick={() => void onResendOtp()}
              >
                Reenviar código
              </button>
            </div>
          </form>
        )}

        {step === "pin-setup" && (
          <form onSubmit={onSetPin} className="rounded-2xl border border-slate-700/80 bg-slate-900/50 p-6 space-y-4 shadow-sm">
            <h1 className="text-lg font-semibold">Creá un PIN (opcional)</h1>
            <p className="text-xs text-slate-400">Para próximos ingresos sin OTP. 6 a 8 dígitos.</p>
            <div>
              <label htmlFor="portal-new-pin" className="text-xs font-medium text-slate-500 block mb-1.5">
                Nuevo PIN
              </label>
              <input
                id="portal-new-pin"
                type="password"
                inputMode="numeric"
                value={newPin}
                onChange={(e) => setNewPin(e.target.value)}
                placeholder="6–8 dígitos"
                className="w-full bg-slate-950/80 border border-slate-600/80 rounded-xl px-4 py-2.5 text-sm tabular-nums transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent"
                minLength={6}
                maxLength={8}
                required
              />
            </div>
            <button
              type="submit"
              disabled={busy}
              className="w-full py-2.5 rounded-xl font-semibold text-white bg-ecolan-brand hover:bg-ecolan-brand-dark disabled:opacity-50 shadow-sm transition-all duration-200 ease-in-out"
            >
              Guardar PIN
            </button>
            <button type="button" className="text-xs text-slate-400" onClick={() => setStep("chat")}>
              Omitir por ahora
            </button>
          </form>
        )}

        {(step === "chat" || step === "pin-setup") && conv && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge value={canalEstadoLabel(conv.estado)} />
              {conv.ticket_id && (
                <span className="text-[10px] font-mono text-slate-400">Caso {conv.ticket_id}</span>
              )}
            </div>

            {modoInvitado && (
              <p className="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
                Modo invitado: no vemos tu cuenta. Identificate con DNI para consultas personalizadas.
              </p>
            )}

            {esperaAgente && (
              <p
                className="text-xs text-amber-200 bg-amber-500/10 border border-amber-500/25 rounded-lg px-3 py-2"
                role="status"
              >
                Te estamos conectando con un agente. Podés seguir escribiendo; te responderán en este
                mismo chat.
              </p>
            )}

            {conAgente && (
              <p
                className="text-xs text-ecolan-brand bg-ecolan-brand/10 border border-ecolan-brand/25 rounded-lg px-3 py-2"
                role="status"
              >
                Un agente se unió a la conversación. Las respuestas aparecerán acá.
              </p>
            )}

            <div className="chat-thread flex-1 rounded-2xl border border-slate-700/80 bg-slate-900/40 p-4 overflow-y-auto min-h-[320px] max-h-[55vh] space-y-3 shadow-sm">
              {mensajes.map((m) => (
                <ChatMessageBubble key={m.id} message={m} portal />
              ))}
              {botTyping && <ChatTypingIndicator />}
              <div ref={bottomRef} />
            </div>
            <p
              className={`text-[11px] font-mono min-h-[1rem] ${
                botTyping ? "text-ecolan-brand" : "text-transparent"
              }`}
              aria-live="polite"
            >
              {botTyping
                ? `Recibido · ${getBranding().botDisplayName} está armando la respuesta…`
                : "·"}
            </p>
            <form onSubmit={onSend} className="flex gap-2.5">
              <label className="sr-only" htmlFor="portal-mensaje">
                Tu mensaje
              </label>
              <input
                id="portal-mensaje"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                placeholder={botTyping ? "Esperá la respuesta…" : "Escribí tu consulta…"}
                disabled={botTyping}
                className="flex-1 bg-slate-950/80 border border-slate-600/80 rounded-xl px-4 py-2.5 text-sm disabled:opacity-60 transition-all duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-ecolan-brand focus:border-transparent"
              />
              <button
                type="submit"
                disabled={botTyping || !texto.trim()}
                className="inline-flex items-center gap-2 px-4 rounded-xl font-semibold text-white bg-ecolan-brand hover:bg-ecolan-brand-dark disabled:opacity-50 shadow-sm transition-all duration-200 ease-in-out"
              >
                <SendIcon className="h-4 w-4" />
                {botTyping ? "Enviando…" : "Enviar"}
              </button>
            </form>
          </>
        )}

        {error && (
          <p className="text-sm text-red-400" role="alert">
            {error}
          </p>
        )}
      </main>
    </div>
  );
}
