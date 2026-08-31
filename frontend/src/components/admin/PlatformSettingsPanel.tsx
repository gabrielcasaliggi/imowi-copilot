"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api-client";
import type { PlatformSettingsResponse } from "@/lib/types";
import { GlassCard, StatusPill } from "@/components/ui/GlassCard";
import { inputCls } from "@/components/ui/forms";
import { getBranding } from "@/lib/brand";
import {
  PlaybooksConsole,
  type PlaybookMap,
} from "@/components/admin/PlaybooksConsole";

const labelCls = "block text-xs text-slate-400 mb-1";

type SettingsSection = "ai" | "whatsapp" | "telegram" | "database" | "billtrack" | "uisp" | "knowledge" | "playbooks";

export function PlatformSettingsPanel({ onMessage }: { onMessage?: (msg: string) => void }) {
  const botName = getBranding().botDisplayName;
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
  const [tg, setTg] = useState({
    bot_token: "",
    webhook_secret: "",
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
  const [uisp, setUisp] = useState({
    enabled: false,
    base_url: "https://uisp.ecolan.com",
    token: "",
    timeout: "12",
    verify_ssl: true,
  });
  const [uispLogin, setUispLogin] = useState("");
  const [uispTest, setUispTest] = useState<{
    ok: boolean;
    detail: string;
  } | null>(null);
  const [kb, setKb] = useState({ min_score: 0.15, top_k: 1, max_fragment_chars: 1800 });
  const [playbooks, setPlaybooks] = useState<PlaybookMap>({});
  const [playbooksResetToken, setPlaybooksResetToken] = useState(0);

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
    setTg({
      bot_token: s.telegram?.bot_token || "",
      webhook_secret: s.telegram?.webhook_secret || "",
      default_org_slug: s.telegram?.default_org_slug || "",
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
    setUisp({
      enabled: Boolean(s.uisp?.enabled ?? res.uisp_enabled),
      base_url: s.uisp?.base_url || "https://uisp.ecolan.com",
      token: s.uisp?.token || "",
      timeout: String(s.uisp?.timeout ?? 12),
      verify_ssl: s.uisp?.verify_ssl !== false,
    });
    setKb({
      min_score: Number(s.knowledge?.min_score ?? 0.15),
      top_k: Number(s.knowledge?.top_k ?? 1),
      max_fragment_chars: Number(s.knowledge?.max_fragment_chars ?? 1800),
    });
    setPlaybooks((s.playbooks as PlaybookMap) || {});
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
      const res = await api.updateAdminSettings({
        ai,
        whatsapp: wa,
        telegram: tg,
        database: dbCfg,
        billtrack,
        uisp: {
          enabled: uisp.enabled,
          base_url: uisp.base_url,
          token: uisp.token,
          timeout: Number(uisp.timeout) || 12,
          verify_ssl: uisp.verify_ssl,
        },
        knowledge: kb,
        playbooks,
      });
      applyResponse(res);
      if (section === "playbooks") {
        setPlaybooksResetToken((n) => n + 1);
        const n = Object.keys(playbooks).length;
        onMessage?.(
          `Playbooks guardados (${n} flujo${n === 1 ? "" : "s"}). El panel de importación quedó listo para otro documento.`,
        );
      } else {
        onMessage?.("Configuración de plataforma guardada.");
      }
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
      if (r.ok) {
        const display = r.display_phone_number || "número OK";
        const name = r.verified_name ? ` · ${r.verified_name}` : "";
        onMessage?.(
          `WhatsApp listo · ${display}${name} · org ${r.default_org_slug} · verify «${r.verify_token}»`,
        );
      } else {
        onMessage?.(
          r.error
            ? `WhatsApp falló: ${r.error.slice(0, 180)}`
            : "WhatsApp incompleto: falta token o phone_number_id",
        );
      }
    } catch (err) {
      onMessage?.(err instanceof Error ? err.message : "Error test WhatsApp");
    } finally {
      setBusy(false);
    }
  };

  const testTg = async () => {
    setBusy(true);
    try {
      const r = await api.testAdminTelegram();
      if (!r.ok) {
        onMessage?.(`Telegram falló: ${r.error || "falta bot_token"}`);
        return;
      }
      const cb = r.callbacks_enabled
        ? "callbacks OK"
        : "⚠ sin callback_query — registrá el webhook de nuevo";
      onMessage?.(
        `Telegram OK · @${r.bot_username || "bot"} · org ${r.default_org_slug} · ${cb}`,
      );
    } catch (err) {
      onMessage?.(err instanceof Error ? err.message : "Error test Telegram");
    } finally {
      setBusy(false);
    }
  };

  const registerTgWebhook = async () => {
    setBusy(true);
    try {
      const r = await api.registerTelegramWebhook({ drop_pending: false });
      onMessage?.(
        r.ok
          ? `Webhook TG registrado · ${r.url} · updates: ${(r.allowed_updates || []).join(", ")}`
          : `Webhook TG falló: ${r.detail || r.reason || "error"}`,
      );
    } catch (err) {
      onMessage?.(err instanceof Error ? err.message : "Error registrando webhook TG");
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

  const testUisp = async () => {
    setBusy(true);
    try {
      const r = await api.testAdminUisp({
        base_url: uisp.base_url,
        token: uisp.token,
        verify_ssl: uisp.verify_ssl,
        timeout: Number(uisp.timeout) || 12,
        login: uispLogin.trim() || undefined,
      });
      if (r.ok) {
        const parts = [
          r.devices != null ? `${r.devices} equipos` : null,
          r.online != null ? `${r.online} en línea` : null,
          r.latency_ms != null ? `${r.latency_ms} ms` : null,
        ].filter(Boolean);
        let detail = parts.join(" · ");
        if (r.cpe) {
          detail += r.cpe.encontrado
            ? ` · CPE ${r.cpe.nombre || r.cpe.login}: ${r.cpe.online ? "en línea" : "fuera de línea"}`
            : ` · CPE «${uispLogin.trim()}» no encontrado`;
        }
        setUispTest({ ok: true, detail });
        onMessage?.(`UISP OK · ${detail}`);
      } else {
        const detail = [r.error || "No se pudo conectar", r.hint].filter(Boolean).join(" — ");
        setUispTest({ ok: false, detail });
        onMessage?.(`UISP falló: ${detail}`);
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Error test UISP";
      setUispTest({ ok: false, detail });
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
    { id: "telegram", label: "Telegram" },
    { id: "billtrack", label: "Clientes (BillTrack)" },
    { id: "uisp", label: "Radio (UISP)" },
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
                ? "border-ecolan-brand/50 bg-ecolan-brand/15 text-slate-100"
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
              label={data.telegram_configured ? "TG OK" : "TG pendiente"}
              tone={data.telegram_configured ? "available" : "soon"}
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
            <StatusPill
              label={
                uispTest
                  ? uispTest.ok
                    ? "UISP OK"
                    : "UISP falló"
                  : data.uisp_enabled
                    ? "UISP listo"
                    : data.uisp_configured
                      ? "UISP off"
                      : "UISP pendiente"
              }
              tone={
                uispTest
                  ? uispTest.ok
                    ? "available"
                    : "soon"
                  : data.uisp_enabled
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
                className="text-sm px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:border-ecolan-brand/40"
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
            <p className="md:col-span-2 text-xs text-slate-400">
              Webhook:{" "}
              <code className="text-slate-300">https://ibot.ecolan.com/api/v1/whatsapp/webhook</code>
              {" "}· suscribir campo <code className="text-slate-300">messages</code>
              {" "}· Phone Number ID = ID del número <em>propio</em> (no el +1 555 de prueba)
            </p>
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
                className="text-sm px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:border-ecolan-brand/40"
              >
                Validar configuración WhatsApp
              </button>
            </div>
          </div>
        </GlassCard>
      )}


      {section === "telegram" && (
        <GlassCard title="Telegram Bot API" accent="cyan" variant="secondary">
          <div className="grid gap-3 md:grid-cols-2">
            <p className="md:col-span-2 text-xs text-slate-400">
              Webhook: <code className="text-slate-300">POST /api/v1/telegram/webhook</code>
              {" "}· header <code className="text-slate-300">X-Telegram-Bot-Api-Secret-Token</code>
            </p>
            <div className="md:col-span-2">
              <label className={labelCls}>Bot token</label>
              <input
                className={inputCls}
                type="password"
                value={tg.bot_token}
                onChange={(e) => setTg({ ...tg, bot_token: e.target.value })}
              />
            </div>
            <div>
              <label className={labelCls}>Webhook secret</label>
              <input
                className={inputCls}
                type="password"
                value={tg.webhook_secret}
                onChange={(e) => setTg({ ...tg, webhook_secret: e.target.value })}
              />
            </div>
            <div>
              <label className={labelCls}>Org slug por defecto (webhook)</label>
              <input
                className={inputCls}
                value={tg.default_org_slug}
                onChange={(e) => setTg({ ...tg, default_org_slug: e.target.value })}
                placeholder="coop-batan"
              />
            </div>
            <div className="md:col-span-2 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => void testTg()}
                className="text-sm px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:border-ecolan-brand/40"
              >
                Validar bot (getMe)
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void registerTgWebhook()}
                className="text-sm px-3 py-1.5 rounded-lg border border-ecolan-brand/40 text-ecolan-brand hover:bg-ecolan-brand/10"
              >
                Registrar webhook (incluye botones CSAT)
              </button>
            </div>
            <p className="md:col-span-2 text-[11px] text-slate-500">
              Si la encuesta ☆ no responde en Telegram, el webhook suele estar limitado a{" "}
              <code className="text-slate-400">message</code>. Este botón lo re-registra con{" "}
              <code className="text-slate-400">callback_query</code>.
            </p>
          </div>
        </GlassCard>
      )}

      {section === "billtrack" && (
        <GlassCard title="BillTrack — padrón de clientes (solo lectura)" accent="amber" variant="secondary">
          <div className="grid gap-3 md:grid-cols-2">
            <p className="md:col-span-2 text-xs text-amber-200/90">
              Conexión externa para que {botName} consulte datos de clientes y valide acciones. No es la
              base del sistema. Este servidor on-prem no habla SSL: dejá <code>disable</code>.
            </p>
            <label className="md:col-span-2 flex items-center gap-2 text-sm text-slate-200">
              <input
                type="checkbox"
                checked={billtrack.enabled}
                onChange={(e) => setBilltrack({ ...billtrack, enabled: e.target.checked })}
                className="rounded border-slate-600"
              />
              Habilitar consultas BillTrack para {botName}
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

      {section === "uisp" && (
        <GlassCard title="UISP — red de radio (CPE)" accent="cyan" variant="secondary">
          <div className="grid gap-3 md:grid-cols-2">
            <p className="md:col-span-2 text-xs text-slate-400">
              Consulta de solo lectura a <code className="text-slate-300">uisp.ecolan.com</code>. El
              nombre del CPE en UISP es el mismo username Radius, así {botName} puede ver si la
              antena está en línea y la calidad de señal. Token: UISP → Settings → Users → API
              tokens → Read Only. Pegalo acá y guardá; no lo pongas en el chat.
            </p>
            <label className="md:col-span-2 flex items-center gap-2 text-sm text-slate-200">
              <input
                type="checkbox"
                checked={uisp.enabled}
                onChange={(e) => setUisp({ ...uisp, enabled: e.target.checked })}
                className="rounded border-slate-600"
              />
              Habilitar consultas UISP para {botName}
            </label>
            <div className="md:col-span-2">
              <label className={labelCls}>URL de UISP</label>
              <input
                className={inputCls}
                value={uisp.base_url}
                onChange={(e) => {
                  setUisp({ ...uisp, base_url: e.target.value });
                  setUispTest(null);
                }}
                placeholder="https://uisp.ecolan.com"
              />
            </div>
            <div className="md:col-span-2">
              <label className={labelCls}>Token NMS (dejar enmascarado si no cambiás)</label>
              <input
                className={inputCls}
                type="password"
                value={uisp.token}
                onChange={(e) => {
                  setUisp({ ...uisp, token: e.target.value });
                  setUispTest(null);
                }}
                placeholder="x-auth-token"
                autoComplete="off"
              />
            </div>
            <div>
              <label className={labelCls}>Timeout (segundos)</label>
              <input
                className={inputCls}
                value={uisp.timeout}
                onChange={(e) => setUisp({ ...uisp, timeout: e.target.value })}
                placeholder="12"
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-200 mt-5">
              <input
                type="checkbox"
                checked={uisp.verify_ssl}
                onChange={(e) => setUisp({ ...uisp, verify_ssl: e.target.checked })}
                className="rounded border-slate-600"
              />
              Verificar certificado SSL
            </label>
            <div className="md:col-span-2">
              <label className={labelCls}>Probar CPE (opcional, username Radius)</label>
              <input
                className={inputCls}
                value={uispLogin}
                onChange={(e) => setUispLogin(e.target.value)}
                placeholder="mismo login que en Radius / nombre del dispositivo"
              />
            </div>
            <div className="md:col-span-2 flex flex-wrap items-center gap-3">
              <button
                type="button"
                disabled={busy}
                onClick={() => void testUisp()}
                className="text-sm px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:border-ecolan-brand/40"
              >
                Probar conexión UISP
              </button>
              {uispTest && (
                <StatusPill
                  label={
                    uispTest.ok
                      ? `Conectada · ${uispTest.detail}`
                      : `Falló · ${uispTest.detail}`
                  }
                  tone={uispTest.ok ? "available" : "soon"}
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
                className="text-sm px-3 py-1.5 rounded-lg border border-slate-600 text-slate-200 hover:border-ecolan-brand/40"
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
        <PlaybooksConsole
          value={playbooks}
          onChange={setPlaybooks}
          onMessage={onMessage}
          busy={busy}
          resetToken={playbooksResetToken}
        />
      )}

      <div className="flex gap-3 items-center">
        <button
          type="submit"
          disabled={busy}
          className="px-4 py-2 rounded-lg bg-ecolan-brand hover:bg-ecolan-brand-dark text-sm font-semibold text-white disabled:opacity-50 shadow-sm transition-all duration-200 ease-in-out"
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
