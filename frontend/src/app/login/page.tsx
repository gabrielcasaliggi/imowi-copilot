"use client";

import { FormEvent, useEffect, useState } from "react";
import { useApp } from "@/contexts/AppContext";
import { getToken } from "@/lib/storage";
import { inputCls } from "@/components/ui/forms";
import { ThemeToggle } from "@/components/ui/ThemeToggle";
import { getBranding } from "@/lib/brand";

export default function LoginPage() {
  const { login, ready } = useApp();
  const { productDisplayName, orgHint } = getBranding();
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const showDemoCredentials =
    process.env.NODE_ENV !== "production" &&
    process.env.NEXT_PUBLIC_APP_ENV !== "production";

  useEffect(() => {
    if (ready && getToken()) {
      // Hard nav: más fiable si el App Router quedó con chunks stale tras un deploy
      window.location.replace("/inbox");
    }
  }, [ready]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(usuario, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Credenciales incorrectas");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center p-6 bg-gradient-to-b from-ecolan-dark/40 to-transparent relative">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-md rounded-2xl border border-slate-700/80 bg-slate-900/60 p-8 glass shadow-sm">
        <div className="flex items-center gap-3 mb-8">
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center font-bold text-white shadow-lg shadow-ecolan-brand/20"
            style={{ background: "linear-gradient(135deg, #2298A6, #1A7985)" }}
          >
            B
          </div>
          <div>
            <h1 className="text-xl font-semibold text-slate-50 tracking-tight">{productDisplayName}</h1>
            <p className="text-xs font-mono text-slate-500">
              {orgHint} · Ecolan + móvil · WhatsApp
            </p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label htmlFor="login-usuario" className="text-xs font-medium text-slate-400 block mb-1.5">
              Usuario
            </label>
            <input
              id="login-usuario"
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              className={`${inputCls} rounded-xl px-4 py-2.5 font-mono`}
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label htmlFor="login-password" className="text-xs font-medium text-slate-400 block mb-1.5">
              Contraseña
            </label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`${inputCls} rounded-xl px-4 py-2.5 font-mono`}
              autoComplete="current-password"
              required
            />
          </div>
          {error && (
            <p className="text-sm text-rose-400" role="alert">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl font-semibold text-white bg-ecolan-brand hover:bg-ecolan-brand-dark disabled:opacity-50 shadow-sm transition-all duration-200 ease-in-out"
          >
            {loading ? "Ingresando…" : "Ingresar"}
          </button>
        </form>

        {showDemoCredentials && (
          <div className="mt-6 pt-4 border-t border-slate-800 text-[10px] font-mono text-slate-600 space-y-1">
            <p>batan / batan — Agente</p>
            <p>admin / admin — Administración</p>
          </div>
        )}

        <p className="mt-6 text-center text-xs text-slate-500">
          ¿Sos abonado?{" "}
          <a href="/portal" className="text-ecolan-brand hover:text-ecolan-brand-dark transition-colors duration-200">
            Ir al portal de soporte
          </a>
        </p>
      </div>
    </div>
  );
}
