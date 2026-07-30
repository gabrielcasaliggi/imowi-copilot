"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type { PlatformSettingsResponse } from "@/lib/types";
import { GlassCard, StatusPill } from "@/components/ui/GlassCard";

const inputCls =
  "w-full bg-slate-950 border border-slate-700/80 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500/40";

const labelCls = "block text-xs text-slate-400 mb-1";

type PlaybookMap = Record<string, { id: string; pregunta: string }[]>;
type SettingsSection = "ai" | "whatsapp" | "database" | "billtrack" | "knowledge" | "playbooks";

export function PlatformSettingsPanel({ onMessage }: { onMessage?: (msg: string) => void }) {
  const [data, setData] = useState<PlatformSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [section, setSection] = useState<SettingsSection>("ai");

  const [ai, setAi] = useState({ base_url: "", api_key: "", model: "" });
  const [wa, setWa] = useState({
    token: "",
    phone_number_id: "",
    verify_token: "",
    app_secret: "",
    default_org_slug: "",
  });
  const [dbCfg, setDbCfg] = useState({ url: "", sslmode: "require", nota: "" });
  const [billtrack, setBilltrack] = useState({
    enabled: false,
    host: "",
    port: "5432",
    user: "",
    password: "",
    dbname: "postgres",
    sslmode: "disable",
    nota: "",
  });
  const [billtrackTest, setBilltrackTest] = useState<{
    ok: boolean;
    detail: string;
  } | null>(null);
  const [kb, setKb] = useState({ min_score: 0.15, top_k: 1, max_fragment_chars: 1800 });
  const [playbooksJson, setPlaybooksJson] = useState("");

  const applyResponse = useCallback((res: PlatformSettingsResponse) => {
    setData(res);
    const s = res.settings;
    setAi({
      base_url: s.ai?.base_url || "",
      api_key: s.ai?.api_key || "",
      model: s.ai?.model || "",
    });
    setWa({
      token: s.whatsapp?.token || "",
      phone_number_id: s.whatsapp?.phone_number_id || "",
      verify_token: s.whatsapp?.verify_token || "",
      app_secret: s.whatsapp?.app_secret || "",
      default_org_slug: s.whatsapp?.default_org_slug || "",
    });
    setDbCfg({
      url: s.database?.url || res.database_url_masked || "",
      sslmode: s.database?.sslmode || "require",
      nota: s.database?.nota || "",
    });
    setBilltrack({
      enabled: Boolean(s.billtrack?.enabled ?? res.billtrack_enabled),
      host: s.billtrack?.host || "",
      port: String(s.billtrack?.port || "5432"),
      user: s.billtrack?.user || "",
      password: s.billtrack?.password || "",
      dbname: s.billtrack?.dbname || "postgres",
      sslmode: s.billtrack?.sslmode || "disable",
      nota: s.billtrack?.nota || "",
    });
    setKb({
      min_score: Number(s.knowledge?.min_score ?? 0.15),
      top_k: Number(s.knowledge?.top_k ?? 1),
      max_fragment_chars: Number(s.knowledge?.max_fragment_chars ?? 1800),
    });
    setPlaybooksJson(JSON.stringify((s.playbooks as PlaybookMap) || {}, null, 2));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.adminSettings();
      applyResponse(res);
    } catch (err) {
      onMessage?.(err instanceof Error ? err.message : "Error al cargar configuración");
    } finally {
      setLoading(false);
    }
  }, [applyResponse, onMessage]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      let playbooks: PlaybookMap = {};
      try {
        playbooks = JSON.parse(playbooksJson) as PlaybookMap;
      } catch {
        onMessage?.("Playbooks: JSON inválido");
        setBusy(false);
        return;
      }
      const res = await api.updateAdminSettings({
        ai,
        whatsapp: wa,
        database: dbCfg,
        billtrack,
        knowledge: kb,
        playbooks,
      });
      applyResponse(res);
      onMessage?.("Configuración de plataforma guardada.");
    } catch (err) {
      onMessage?.(err instanceof Error ? err.message : "Error al guardar");
    } finally {
      setBusy(false);
    }
  };

  const testAi = async () => {
    setBusy(true);
    try {
      const r = await api.testAdminAi();
      onMessage?.(r.ok ? `IA OK · ${r.model} · «${r.reply}»` : `IA falló: ${r.error}`);
    } catch (err) {
      onMessage?.(err instanceof Error ? err.message : "Error test IA");
    } finally {
      setBusy(false);
    }
  };

  const testWa = async () => {
    setBusy(true);
    try {
      const r = await api.testAdminWhatsapp();
      onMessage?.(
        r.ok
          ? `WhatsApp listo · org ${r.default_org_slug} · verify «${r.verify_token}»`
          : "WhatsApp incompleto: falta token o phone_number_id",
      );
    } catch (err) {
      onMessage?.(err instanceof Error ? err.message : "Error test WhatsApp");
    } finally {
      setBusy(false);
    }
  };

  const testEstateDb = async () => {
    setBusy(true);
    try {
      const r = await api.testAdminDatabase();
      onMessage?.(
        r.ok
          ? `Data Estate OK · ${r.dialect} · ${r.latency_ms ?? "?"} ms`
          : `Data Estate falló: ${r.error || "sin conexión"}`,
      );
    } catch (err) {
      onMessage?.(err instanceof Error ? err.message : "Error test Data Estate");
    } finally {
      setBusy(false);
    }
  };

  const testBilltrack = async () => {
    setBusy(true);
    try {
      const r = await api.testAdminBilltrack({
        host: billtrack.host,
        port: billtrack.port,
        user: billtrack.user,
        password: billtrack.password,
        dbname: billtrack.dbname,
        sslmode: billtrack.sslmode || "disable",
      });
      if (r.ok) {
        const parts = [
          r.current_database ? `db ${r.current_database}` : null,
          r.current_user ? `user ${r.current_user}` : null,
          r.latency_ms != null ? `${r.latency_ms} ms` : null,
          r.sslmode ? `ssl ${r.sslmode}` : null,
          r.server_version ? `v${r.server_version}` : null,
        ].filter(Boolean);
        const detail = parts.join(" · ");
        setBilltrackTest({ ok: true, detail });
        onMessage?.(`BillTrack OK · ${detail}`);
      } else {
        const detail = [r.error || "No se pudo conectar", r.hint].filter(Boolean).join(" — ");
        setBilltrackTest({ ok: false, detail });
        onMessage?.(`BillTrack falló: ${detail}`);
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Error test BillTrack";
      setBilltrackTest({ ok: false, detail });
      onMessage?.(detail);
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <p className="text-slate-500 text-sm">Cargando configuración…</p>;
  }

  const tabs: { id: SettingsSection; label: string }[] = [
    { id: "ai", label: "API IA" },
    { id: "whatsapp", label: "WhatsApp" },
    { id: "billtrack", label: "Clientes (BillTrack)" },
    { id: "database", label: "Data Estate" },
    { id: "knowledge", label: "Conocimiento" },
    { id: "playbooks", label: "Playbooks" },
  ];

  return (
    <form onSubmit={save} className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setSection(t.id)}
            className={`px-3 py-1.5 rounded-lg text-sm border transition ${
              section === t.id
                ? "border-cyan-500/50 bg-cyan-500/15 text-cyan-100"
                : "border-slate-700/80 text-slate-400 hover:border-slate-500"
            }`}
          >
            {t.label}
          </button>
        ))}
        <div className="flex-1" />
        {data && (
          <div className="flex gap-2 text-xs">
            <StatusPill label={data.ai_configured ? "IA OK" : "IA pendiente"} tone={data.ai_configured ? "available" : "soon"} />
            <StatusPill
              label={data.whatsapp_configured ? "WA OK" : "WA pendiente"}
              tone={data.whatsapp_configured ? "available" : "soon"}
            />
            <StatusPill
              label={
                billtrackTest
                  ? billtrackTest.ok
                    ? "BillTrack OK"
                    : "BillTrack falló"
                  : data.billtrack_enabled
                    ? "BillTrack listo"
                    : data.billtrack_configured
                      ? "BillTrack off"
                      : "BillTrack pendiente"
              }
              tone={
                billtrackTest
                  ? billtrackTest.ok
                    ? "available"
                    : "soon"
                  : data.billtrack_enabled
                    ? "available"
                    : "neutral"
              }
            />
            <StatusPill label={`Estate · ${data.database_driver}`} tone="neutral" />
          </div>
        )}
      </div>

      {section === "ai" && (
        <GlassCard title="API de IA (Llama / Ollama / compatible OpenAI)" accent="cyan" variant="secondary">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="md:col-span-2">
              <label className={labelCls}>Base URL</label>
              <input
                className={inputCls}
                value={ai.base_url}
                onChange={(e) => setAi({ ...ai, base_url: e.target.value })}
                placeholder="http://localhost:11434/v1"
              />
            </div>
            <div>
              <label className={labelCls}>Modelo</label>
              <input
                className={inputCls}
                value={ai.model}
                onChange={(e) => setAi({ ...ai, model: e.target.value })}
                placeholder="llama3.2"
              />
            </div>
            <div>
              <label className={labelCls}>API Key (dejar enmascarada si no cambiás)</label>
              <input
                className={inputCls}
                type="password"
                value={ai.api_key}
                onChange={(e) => setAi({ ...ai, api_key: e.target.value })}
                placeholder="ollama / groq / …"
              />
            </div>
            <div className="md:col-span-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => void testAi()}
                className="text-sm px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:border-cyan-500/40"
              >
                Probar conexión IA
              </button>
            </div>
          </div>
        </GlassCard>
      )}

      {section === "whatsapp" && (
        <GlassCard title="WhatsApp Cloud API (Meta)" accent="cyan" variant="secondary">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="md:col-span-2">
              <label className={labelCls}>Token</label>
              <input
                className={inputCls}
                type="password"
                value={wa.token}
                onChange={(e) => setWa({ ...wa, token: e.target.value })}
              />
            </div>
            <div>
              <label className={labelCls}>Phone Number ID</label>
              <input
                className={inputCls}
                value={wa.phone_number_id}
                onChange={(e) => setWa({ ...wa, phone_number_id: e.target.value })}
              />
            </div>
            <div>
              <label className={labelCls}>Verify token (webhook)</label>
              <input
                className={inputCls}
                value={wa.verify_token}
                onChange={(e) => setWa({ ...wa, verify_token: e.target.value })}
              />
            </div>
            <div>
              <label className={labelCls}>App secret</label>
              <input
                className={inputCls}
                type="password"
                value={wa.app_secret}
                onChange={(e) => setWa({ ...wa, app_secret: e.target.value })}
              />
            </div>
            <div>
              <label className={labelCls}>Org slug por defecto (webhook)</label>
              <input
                className={inputCls}
                value={wa.default_org_slug}
                onChange={(e) => setWa({ ...wa, default_org_slug: e.target.value })}
                placeholder="coop-batan"
              />
            </div>
            <div className="md:col-span-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => void testWa()}
                className="text-sm px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:border-cyan-500/40"
              >
                Validar configuración WhatsApp
              </button>
            </div>
          </div>
        </GlassCard>
      )}

      {section === "billtrack" && (
        <GlassCard title="BillTrack — padrón de clientes (solo lectura)" accent="amber" variant="secondary">
          <div className="grid gap-3 md:grid-cols-2">
            <p className="md:col-span-2 text-xs text-amber-200/90">
              Conexión externa para que el bot consulte datos de clientes y valide acciones. No es la
              base del sistema. Este servidor on-prem no habla SSL: dejá <code>disable</code>.
            </p>
            <label className="md:col-span-2 flex items-center gap-2 text-sm text-slate-200">
              <input
                type="checkbox"
                checked={billtrack.enabled}
                onChange={(e) => setBilltrack({ ...billtrack, enabled: e.target.checked })}
                className="rounded border-slate-600"
              />
              Habilitar consultas BillTrack para el bot
            </label>
            <div>
              <label className={labelCls}>Host / IP</label>
              <input
                className={inputCls}
                value={billtrack.host}
                onChange={(e) => {
                  setBilltrack({ ...billtrack, host: e.target.value });
                  setBilltrackTest(null);
                }}
                placeholder="181.41.240.23"
              />
            </div>
            <div>
              <label className={labelCls}>Puerto</label>
              <input
                className={inputCls}
                value={billtrack.port}
                onChange={(e) => {
                  setBilltrack({ ...billtrack, port: e.target.value });
                  setBilltrackTest(null);
                }}
                placeholder="5432"
              />
            </div>
            <div>
              <label className={labelCls}>Usuario</label>
              <input
                className={inputCls}
                value={billtrack.user}
                onChange={(e) => {
                  setBilltrack({ ...billtrack, user: e.target.value });
                  setBilltrackTest(null);
                }}
                placeholder="billtrack_reader"
              />
            </div>
            <div>
              <label className={labelCls}>Contraseña (dejar enmascarada si no cambiás)</label>
              <input
                className={inputCls}
                type="password"
                value={billtrack.password}
                onChange={(e) => {
                  setBilltrack({ ...billtrack, password: e.target.value });
                  setBilltrackTest(null);
                }}
              />
            </div>
            <div>
              <label className={labelCls}>Nombre de base (dbname)</label>
              <input
                className={inputCls}
                value={billtrack.dbname}
                onChange={(e) => {
                  setBilltrack({ ...billtrack, dbname: e.target.value });
                  setBilltrackTest(null);
                }}
                placeholder="postgres"
              />
            </div>
            <div>
              <label className={labelCls}>SSL mode</label>
              <select
                className={inputCls}
                value={billtrack.sslmode}
                onChange={(e) => {
                  setBilltrack({ ...billtrack, sslmode: e.target.value });
                  setBilltrackTest(null);
                }}
              >
                <option value="disable">disable (recomendado para este servidor)</option>
                <option value="prefer">prefer</option>
                <option value="allow">allow</option>
                <option value="require">require</option>
              </select>
            </div>
            {data?.billtrack_url_masked && (
              <p className="md:col-span-2 text-xs text-slate-500">URL armada: {data.billtrack_url_masked}</p>
            )}
            <div className="md:col-span-2 flex flex-wrap items-center gap-3">
              <button
                type="button"
                disabled={busy}
                onClick={() => void testBilltrack()}
                className="text-sm px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:border-amber-500/40"
              >
                Probar conexión BillTrack
              </button>
              {billtrackTest && (
                <StatusPill
                  label={
                    billtrackTest.ok
                      ? `Conectada · ${billtrackTest.detail}`
                      : `Falló · ${billtrackTest.detail}`
                  }
                  tone={billtrackTest.ok ? "available" : "soon"}
                />
              )}
            </div>
          </div>
        </GlassCard>
      )}

      {section === "database" && (
        <GlassCard title="Data Estate — base del sistema" accent="cyan" variant="secondary">
          <div className="grid gap-3">
            <p className="text-xs text-slate-400">
              Acá vive lo que opera la plataforma: tickets, usuarios, config, canal, KB. Separado de
              BillTrack. La URL activa del proceso viene de <code>DATABASE_URL</code> del entorno.
            </p>
            <div>
              <label className={labelCls}>DATABASE_URL (documentación / migración)</label>
              <input
                className={inputCls}
                value={dbCfg.url}
                onChange={(e) => setDbCfg({ ...dbCfg, url: e.target.value })}
              />
            </div>
            <div>
              <label className={labelCls}>SSL mode</label>
              <input
                className={inputCls}
                value={dbCfg.sslmode}
                onChange={(e) => setDbCfg({ ...dbCfg, sslmode: e.target.value })}
              />
            </div>
            {data && (
              <p className="text-xs text-slate-500">
                Activa ahora: {data.database_url_masked} · driver {data.database_driver}
              </p>
            )}
            <div>
              <button
                type="button"
                disabled={busy}
                onClick={() => void testEstateDb()}
                className="text-sm px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:border-cyan-500/40"
              >
                Probar Data Estate activo
              </button>
            </div>
          </div>
        </GlassCard>
      )}

      {section === "knowledge" && (
        <GlassCard title="Base de conocimiento (RAG)" accent="cyan" variant="secondary">
          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <label className={labelCls}>Score mínimo</label>
              <input
                className={inputCls}
                type="number"
                step="0.01"
                value={kb.min_score}
                onChange={(e) => setKb({ ...kb, min_score: Number(e.target.value) })}
              />
            </div>
            <div>
              <label className={labelCls}>Top K</label>
              <input
                className={inputCls}
                type="number"
                value={kb.top_k}
                onChange={(e) => setKb({ ...kb, top_k: Number(e.target.value) })}
              />
            </div>
            <div>
              <label className={labelCls}>Máx. chars fragmento</label>
              <input
                className={inputCls}
                type="number"
                value={kb.max_fragment_chars}
                onChange={(e) => setKb({ ...kb, max_fragment_chars: Number(e.target.value) })}
              />
            </div>
            <p className="md:col-span-3 text-xs text-slate-500">
              Los artículos se gestionan en Conocimiento / por cooperativa. Acá solo umbrales del buscador.
            </p>
          </div>
        </GlassCard>
      )}

      {section === "playbooks" && (
        <GlassCard title="Playbooks N1 (internet / móvil / corte)" accent="cyan" variant="secondary">
          <div className="space-y-2">
            <p className="text-xs text-slate-500">
              JSON por flujo: lista de pasos con <code>id</code> y <code>pregunta</code>.
            </p>
            <textarea
              className={`${inputCls} font-mono min-h-[280px]`}
              value={playbooksJson}
              onChange={(e) => setPlaybooksJson(e.target.value)}
            />
          </div>
        </GlassCard>
      )}

      <div className="flex gap-3 items-center">
        <button
          type="submit"
          disabled={busy}
          className="px-4 py-2 rounded-lg bg-cyan-600/90 hover:bg-cyan-500 text-sm text-white disabled:opacity-50"
        >
          Guardar configuración
        </button>
        {data?.updated_at && (
          <span className="text-xs text-slate-500">
            Última actualización: {data.updated_at}
            {data.updated_by ? ` · ${data.updated_by}` : ""}
          </span>
        )}
      </div>
    </form>
  );
}
