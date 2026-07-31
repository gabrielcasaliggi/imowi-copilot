"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, type InboxConversation, type InboxMessage } from "@/lib/api-client";

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
      setStep("otp");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar");
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
    // Mostrar el mensaje del cliente al instante mientras el bot arma la respuesta
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
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <header className="border-b border-slate-800 px-4 py-3 flex items-center justify-between">
        <div>
          <p className="text-sm font-semibold">Portal abonado · Cooperativa Batán</p>
          <p className="text-[10px] font-mono text-slate-500">Ecolan + IMOVI · soporte</p>
        </div>
        <div className="flex gap-3 items-center">
          {token && (
            <button type="button" onClick={onExit} className="text-xs text-slate-400 hover:text-slate-200">
              Salir
            </button>
          )}
          <Link href="/login" className="text-xs text-cyan-400/80 hover:text-cyan-300">
            Consola operadores
          </Link>
        </div>
      </header>

      <main className="flex-1 flex flex-col max-w-lg mx-auto w-full p-4 gap-4">
        {step === "auth" && (
          <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 space-y-4">
            <h1 className="text-lg font-semibold">Ingresá al portal</h1>
            <p className="text-xs text-slate-400">
              Validamos tu DNI contra el padrón y te enviamos un código al email registrado.
            </p>
            <div className="flex gap-2 text-xs">
              <button
                type="button"
                className={`px-3 py-1 rounded-lg ${mode === "dni" ? "bg-emerald-500/20 text-emerald-300" : "text-slate-500"}`}
                onClick={() => setMode("dni")}
              >
                DNI + OTP
              </button>
              <button
                type="button"
                className={`px-3 py-1 rounded-lg ${mode === "pin" ? "bg-emerald-500/20 text-emerald-300" : "text-slate-500"}`}
                onClick={() => setMode("pin")}
              >
                DNI + PIN
              </button>
            </div>

            {mode === "dni" ? (
              <form onSubmit={onStartDni} className="space-y-3">
                <input
                  value={dni}
                  onChange={(e) => setDni(e.target.value)}
                  placeholder="DNI (solo números)"
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono"
                  required
                />
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full py-2.5 rounded-xl font-semibold text-slate-950 bg-emerald-400 disabled:opacity-50"
                >
                  {busy ? "Verificando…" : "Continuar"}
                </button>
              </form>
            ) : (
              <form onSubmit={onPinLogin} className="space-y-3">
                <input
                  value={dni}
                  onChange={(e) => setDni(e.target.value)}
                  placeholder="DNI"
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono"
                  required
                />
                <input
                  type="password"
                  inputMode="numeric"
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  placeholder="PIN (6–8 dígitos)"
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono"
                  required
                />
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full py-2.5 rounded-xl font-semibold text-slate-950 bg-emerald-400 disabled:opacity-50"
                >
                  {busy ? "Ingresando…" : "Ingresar"}
                </button>
              </form>
            )}

            <button
              type="button"
              onClick={() => void onGuest()}
              disabled={busy}
              className="w-full text-xs text-slate-500 hover:text-slate-300 py-2"
            >
              Continuar como invitado (sin datos de cuenta)
            </button>

            {showDemo && (
              <p className="text-[10px] font-mono text-slate-600">Dev: DNI demo 30111222 (OTP en respuesta debug)</p>
            )}
          </div>
        )}

        {step === "otp" && (
          <form onSubmit={onVerifyOtp} className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 space-y-4">
            <h1 className="text-lg font-semibold">Código de verificación</h1>
            <p className="text-xs text-slate-400">
              Enviamos un código a <span className="font-mono text-slate-300">{contactMasked}</span>
            </p>
            <input
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              placeholder="Código OTP"
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono tracking-widest"
              required
            />
            <button
              type="submit"
              disabled={busy}
              className="w-full py-2.5 rounded-xl font-semibold text-slate-950 bg-emerald-400 disabled:opacity-50"
            >
              {busy ? "Validando…" : "Verificar"}
            </button>
            <button type="button" className="text-xs text-slate-500" onClick={() => setStep("auth")}>
              Volver
            </button>
          </form>
        )}

        {step === "pin-setup" && (
          <form onSubmit={onSetPin} className="rounded-2xl border border-slate-800 bg-slate-900/50 p-6 space-y-4">
            <h1 className="text-lg font-semibold">Creá un PIN (opcional)</h1>
            <p className="text-xs text-slate-400">Para próximos ingresos sin OTP. 6 a 8 dígitos.</p>
            <input
              type="password"
              inputMode="numeric"
              value={newPin}
              onChange={(e) => setNewPin(e.target.value)}
              placeholder="PIN"
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono"
              minLength={6}
              maxLength={8}
              required
            />
            <button
              type="submit"
              disabled={busy}
              className="w-full py-2.5 rounded-xl font-semibold text-slate-950 bg-emerald-400 disabled:opacity-50"
            >
              Guardar PIN
            </button>
            <button type="button" className="text-xs text-slate-500" onClick={() => setStep("chat")}>
              Omitir por ahora
            </button>
          </form>
        )}

        {(step === "chat" || step === "pin-setup") && conv && (
          <>
            {modoInvitado && (
              <p className="text-xs text-amber-400/90 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
                Modo invitado: no vemos tu cuenta. Identificate con DNI para consultas personalizadas.
              </p>
            )}
            <div className="flex-1 rounded-2xl border border-slate-800 bg-slate-900/40 p-3 overflow-y-auto min-h-[320px] max-h-[55vh] space-y-2">
              {mensajes.map((m) => (
                <div
                  key={m.id}
                  className={`text-sm rounded-xl px-3 py-2 max-w-[90%] ${
                    m.autor === "cliente"
                      ? "ml-auto bg-emerald-500/20 text-emerald-100"
                      : "mr-auto bg-slate-800 text-slate-200"
                  }`}
                >
                  <p className="text-[10px] font-mono text-slate-500 mb-0.5">{m.autor}</p>
                  {m.texto}
                </div>
              ))}
              {botTyping && (
                <div
                  className="mr-auto bg-slate-800 text-slate-200 text-sm rounded-xl px-3 py-2 max-w-[90%]"
                  aria-live="polite"
                  aria-label="El asistente está escribiendo"
                >
                  <p className="text-[10px] font-mono text-slate-500 mb-1">bot</p>
                  <div className="flex items-center gap-1.5 py-0.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/80 animate-bounce [animation-delay:0ms]" />
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/80 animate-bounce [animation-delay:150ms]" />
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400/80 animate-bounce [animation-delay:300ms]" />
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>
            <p
              className={`text-[11px] font-mono min-h-[1rem] ${
                botTyping ? "text-emerald-400/90" : "text-transparent"
              }`}
              aria-live="polite"
            >
              {botTyping ? "Recibido · el asistente está armando la respuesta…" : "·"}
            </p>
            <form onSubmit={onSend} className="flex gap-2">
              <input
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                placeholder={botTyping ? "Esperá la respuesta…" : "Escribí tu consulta…"}
                disabled={botTyping}
                className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm disabled:opacity-60"
              />
              <button
                type="submit"
                disabled={botTyping || !texto.trim()}
                className="px-4 rounded-xl font-semibold text-slate-950 bg-emerald-400 disabled:opacity-50"
              >
                {botTyping ? "…" : "Enviar"}
              </button>
            </form>
          </>
        )}

        {error && <p className="text-sm text-red-400 font-mono">{error}</p>}
      </main>
    </div>
  );
}
