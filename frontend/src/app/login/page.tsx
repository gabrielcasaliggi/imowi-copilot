"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useApp } from "@/contexts/AppContext";
import { getToken } from "@/lib/storage";

export default function LoginPage() {
  const router = useRouter();
  const { login, ready } = useApp();
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (ready && getToken()) router.replace("/soporte");
  }, [ready, router]);

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
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8 glass">
        <div className="flex items-center gap-3 mb-8">
          <div
            className="w-12 h-12 rounded-xl flex items-center justify-center font-bold text-slate-950"
            style={{ background: "linear-gradient(135deg, var(--brand), #3b82f6)" }}
          >
            i
          </div>
          <div>
            <h1 className="text-xl font-semibold text-slate-100">imowi Operations Hub</h1>
            <p className="text-xs font-mono text-slate-500">Consola operativa · Agentic AI</p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-mono text-slate-500 block mb-1">Usuario</label>
            <input
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono focus:outline-none focus:border-[var(--brand)]"
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="text-xs font-mono text-slate-500 block mb-1">Contraseña</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono focus:outline-none focus:border-[var(--brand)]"
              autoComplete="current-password"
              required
            />
          </div>
          {error && (
            <p className="text-sm text-red-400 font-mono">{error}</p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl font-semibold text-slate-950 disabled:opacity-50"
            style={{ background: "var(--brand)" }}
          >
            {loading ? "Ingresando…" : "Ingresar"}
          </button>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-800 text-[10px] font-mono text-slate-600 space-y-1">
          <p>admin / admin — NOC imowi</p>
          <p>batan / batan · viamonte / viamonte — cooperativas</p>
        </div>
      </div>
    </div>
  );
}
