"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api-client";
import { setToken } from "@/lib/storage";

export default function ChangePasswordPage() {
  const router = useRouter();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (next !== confirm) {
      setError("Las contraseñas no coinciden");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const res = await api.changePassword(current, next);
      // El backend invalida el JWT viejo (token_version); hay que guardar el nuevo
      if (res.token) {
        setToken(res.token);
        window.location.replace("/inbox");
        return;
      }
      // Fallback: forzar re-login limpio
      window.location.replace("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cambiar");
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8">
        <h1 className="text-xl font-semibold mb-2">Cambiar contraseña</h1>
        <p className="text-xs text-slate-500 mb-6">
          Debés definir una contraseña segura antes de continuar.
        </p>
        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label htmlFor="pwd-current" className="text-xs font-mono text-slate-400 block mb-1">
              Actual (si la sabés)
            </label>
            <input
              id="pwd-current"
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono"
              autoComplete="current-password"
            />
          </div>
          <div>
            <label htmlFor="pwd-new" className="text-xs font-mono text-slate-400 block mb-1">
              Nueva
            </label>
            <input
              id="pwd-new"
              type="password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono"
              required
              minLength={10}
              autoComplete="new-password"
            />
          </div>
          <div>
            <label htmlFor="pwd-confirm" className="text-xs font-mono text-slate-400 block mb-1">
              Confirmar
            </label>
            <input
              id="pwd-confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono"
              required
              minLength={10}
              autoComplete="new-password"
            />
          </div>
          {error && (
            <p className="text-sm text-red-400" role="alert">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl font-semibold text-slate-950 disabled:opacity-50"
            style={{ background: "var(--brand)" }}
          >
            {loading ? "Guardando…" : "Guardar y continuar"}
          </button>
        </form>
      </div>
    </div>
  );
}
