"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api-client";

function InviteForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token") || "";
  const [email, setEmail] = useState("");
  const [orgNombre, setOrgNombre] = useState("");
  const [nombre, setNombre] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [purpose, setPurpose] = useState<"invite" | "password_reset">("invite");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("Falta el token de invitación");
      return;
    }
    api
      .peekInvite(token)
      .then((d) => {
        setEmail(d.email);
        setOrgNombre(d.org_nombre);
        setNombre(d.nombre || "");
        setPurpose(d.purpose === "password_reset" ? "password_reset" : "invite");
        setReady(true);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Invitación inválida"));
  }, [token]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setError("Las contraseñas no coinciden");
      return;
    }
    setLoading(true);
    setError("");
    try {
      await api.acceptInvite({ token, password, nombre });
      router.replace("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo activar");
    } finally {
      setLoading(false);
    }
  };

  const isReset = purpose === "password_reset";

  return (
    <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900/60 p-8">
      <h1 className="text-xl font-semibold text-slate-100 mb-2">
        {isReset ? "Nueva contraseña" : "Activar cuenta"}
      </h1>
      <p className="text-xs text-slate-500 mb-6">
        {orgNombre ? `${orgNombre} · ` : ""}
        {email || "Invitación"}
      </p>
      {ready ? (
        <form onSubmit={onSubmit} className="space-y-4">
          {!isReset && (
            <div>
              <label className="text-xs font-mono text-slate-500 block mb-1">Nombre</label>
              <input
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm"
                required
              />
            </div>
          )}
          <div>
            <label className="text-xs font-mono text-slate-500 block mb-1">
              {isReset ? "Nueva contraseña" : "Contraseña"}
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono"
              required
              minLength={10}
            />
            <p className="text-[10px] text-slate-600 mt-1">
              Mín. 10 caracteres, mayúscula, minúscula y dígito
            </p>
          </div>
          <div>
            <label className="text-xs font-mono text-slate-500 block mb-1">Confirmar</label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2.5 text-sm font-mono"
              required
              minLength={10}
            />
          </div>
          {error && <p className="text-sm text-red-400">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl font-semibold text-slate-950 disabled:opacity-50"
            style={{ background: "var(--brand)" }}
          >
            {loading ? "Guardando…" : isReset ? "Guardar contraseña" : "Crear contraseña e ingresar"}
          </button>
        </form>
      ) : (
        <p className="text-sm text-slate-400">{error || "Cargando invitación…"}</p>
      )}
      <p className="mt-6 text-center text-xs">
        <Link href="/login" className="text-cyan-400/80">
          Volver al login
        </Link>
      </p>
    </div>
  );
}

export default function InvitePage() {
  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <Suspense fallback={<p className="text-slate-400 text-sm">Cargando…</p>}>
        <InviteForm />
      </Suspense>
    </div>
  );
}
