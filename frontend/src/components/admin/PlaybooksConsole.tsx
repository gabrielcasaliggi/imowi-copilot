"use client";

import { ChangeEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api-client";
import { GlassCard } from "@/components/ui/GlassCard";
import { inputCls } from "@/components/ui/forms";

export type PlaybookPaso = { id: string; pregunta: string };
export type PlaybookMap = Record<string, PlaybookPaso[]>;

type Props = {
  value: PlaybookMap;
  onChange: (next: PlaybookMap) => void;
  onMessage?: (msg: string) => void;
  busy?: boolean;
};

function cloneMap(m: PlaybookMap): PlaybookMap {
  return Object.fromEntries(
    Object.entries(m).map(([k, pasos]) => [k, pasos.map((p) => ({ ...p }))]),
  );
}

function slugify(raw: string, fallback: string): string {
  const s = raw
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
  return s || fallback;
}

export function PlaybooksConsole({ value, onChange, onMessage, busy }: Props) {
  const [draftText, setDraftText] = useState("");
  const [converting, setConverting] = useState(false);
  const [importMap, setImportMap] = useState<PlaybookMap>({});
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [activeFlow, setActiveFlow] = useState<string>("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [advancedJson, setAdvancedJson] = useState("");

  const flowKeys = useMemo(() => Object.keys(value).sort(), [value]);
  const importKeys = useMemo(() => Object.keys(importMap).sort(), [importMap]);

  useEffect(() => {
    if (!activeFlow && flowKeys.length) {
      setActiveFlow(flowKeys[0]);
    } else if (activeFlow && !value[activeFlow] && flowKeys.length) {
      setActiveFlow(flowKeys[0]);
    }
  }, [activeFlow, flowKeys, value]);

  useEffect(() => {
    setAdvancedJson(JSON.stringify(value, null, 2));
  }, [value]);

  const updateFlowPasos = useCallback(
    (flow: string, pasos: PlaybookPaso[]) => {
      const next = cloneMap(value);
      next[flow] = pasos;
      onChange(next);
    },
    [onChange, value],
  );

  const updateImportPasos = useCallback((flow: string, pasos: PlaybookPaso[]) => {
    setImportMap((prev) => {
      const next = cloneMap(prev);
      next[flow] = pasos;
      return next;
    });
  }, []);

  const onFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const text = await file.text();
      setDraftText(text);
      onMessage?.(`Archivo cargado: ${file.name}`);
    } catch {
      onMessage?.("No se pudo leer el archivo");
    }
  };

  const convert = async () => {
    if (!draftText.trim()) {
      onMessage?.("Pegá o subí un documento antes de convertir");
      return;
    }
    setConverting(true);
    try {
      const res = await api.convertPlaybooks(draftText.trim());
      const pb = res.playbooks || {};
      setImportMap(pb);
      const sug = new Set(res.sugeridos?.length ? res.sugeridos : Object.keys(pb));
      const sel: Record<string, boolean> = {};
      for (const k of Object.keys(pb)) sel[k] = sug.has(k);
      setSelected(sel);
      const first = Object.keys(pb)[0] || "";
      if (first) setActiveFlow(first);
      onMessage?.(
        `Convertido: ${Object.keys(pb).length} flujo(s). Revisá y aplicá los que quieras.`,
      );
    } catch (err) {
      onMessage?.(err instanceof Error ? err.message : "Error al convertir");
    } finally {
      setConverting(false);
    }
  };

  const applySelected = () => {
    const keys = Object.keys(importMap).filter((k) => selected[k]);
    if (!keys.length) {
      onMessage?.("Seleccioná al menos un flujo para aplicar");
      return;
    }
    const next = cloneMap(value);
    for (const k of keys) {
      next[k] = importMap[k].map((p) => ({ ...p }));
    }
    onChange(next);
    onMessage?.(
      `Listo para guardar: ${keys.join(", ")}. Pulsá «Guardar configuración» abajo.`,
    );
  };

  const addPaso = (flow: string, source: "current" | "import") => {
    const map = source === "current" ? value : importMap;
    const pasos = [...(map[flow] || [])];
    const id = slugify(`paso_${pasos.length + 1}`, `paso_${pasos.length + 1}`);
    pasos.push({ id, pregunta: "" });
    if (source === "current") updateFlowPasos(flow, pasos);
    else updateImportPasos(flow, pasos);
  };

  const removePaso = (flow: string, idx: number, source: "current" | "import") => {
    const map = source === "current" ? value : importMap;
    const pasos = (map[flow] || []).filter((_, i) => i !== idx);
    if (source === "current") updateFlowPasos(flow, pasos);
    else updateImportPasos(flow, pasos);
  };

  const movePaso = (
    flow: string,
    idx: number,
    dir: -1 | 1,
    source: "current" | "import",
  ) => {
    const map = source === "current" ? value : importMap;
    const pasos = [...(map[flow] || [])];
    const j = idx + dir;
    if (j < 0 || j >= pasos.length) return;
    [pasos[idx], pasos[j]] = [pasos[j], pasos[idx]];
    if (source === "current") updateFlowPasos(flow, pasos);
    else updateImportPasos(flow, pasos);
  };

  const editPaso = (
    flow: string,
    idx: number,
    field: "id" | "pregunta",
    text: string,
    source: "current" | "import",
  ) => {
    const map = source === "current" ? value : importMap;
    const pasos = (map[flow] || []).map((p, i) =>
      i === idx ? { ...p, [field]: text } : p,
    );
    if (source === "current") updateFlowPasos(flow, pasos);
    else updateImportPasos(flow, pasos);
  };

  const applyAdvancedJson = () => {
    try {
      const parsed = JSON.parse(advancedJson) as PlaybookMap;
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        onMessage?.("JSON inválido: se espera un objeto de flujos");
        return;
      }
      onChange(parsed);
      onMessage?.("JSON aplicado. Pulsá «Guardar configuración» para persistir.");
    } catch {
      onMessage?.("JSON inválido");
    }
  };

  const renderPasoEditor = (
    flow: string,
    pasos: PlaybookPaso[],
    source: "current" | "import",
  ) => (
    <div className="space-y-2">
      {pasos.map((p, idx) => (
        <div
          key={`${flow}-${source}-${idx}-${p.id}`}
          className="rounded-lg border border-slate-800/80 bg-slate-950/40 p-2 space-y-1.5"
        >
          <div className="flex gap-2 items-center">
            <span className="text-[10px] font-mono text-slate-500 w-5 shrink-0">
              {idx + 1}
            </span>
            <input
              className={`${inputCls} font-mono text-[11px] flex-1`}
              value={p.id}
              onChange={(e) => editPaso(flow, idx, "id", e.target.value, source)}
              placeholder="id"
              disabled={busy || converting}
            />
            <button
              type="button"
              className="text-[10px] text-slate-400 hover:text-slate-200 px-1"
              onClick={() => movePaso(flow, idx, -1, source)}
              disabled={busy || converting || idx === 0}
              title="Subir"
            >
              ↑
            </button>
            <button
              type="button"
              className="text-[10px] text-slate-400 hover:text-slate-200 px-1"
              onClick={() => movePaso(flow, idx, 1, source)}
              disabled={busy || converting || idx === pasos.length - 1}
              title="Bajar"
            >
              ↓
            </button>
            <button
              type="button"
              className="text-[10px] text-rose-400/90 hover:text-rose-300 px-1"
              onClick={() => removePaso(flow, idx, source)}
              disabled={busy || converting}
            >
              ✕
            </button>
          </div>
          <textarea
            className={`${inputCls} text-xs min-h-[52px]`}
            value={p.pregunta}
            onChange={(e) => editPaso(flow, idx, "pregunta", e.target.value, source)}
            placeholder="Pregunta al abonado"
            disabled={busy || converting}
          />
        </div>
      ))}
      <button
        type="button"
        onClick={() => addPaso(flow, source)}
        disabled={busy || converting}
        className="text-xs text-ecolan-brand hover:text-ecolan-brand-light disabled:opacity-50"
      >
        + Agregar paso
      </button>
    </div>
  );

  return (
    <div className="space-y-4">
      <GlassCard title="Importar documento" accent="cyan" variant="secondary">
        <p className="text-xs text-slate-500 mb-2 leading-relaxed">
          Pegá o subí un guión de troubleshooting (.txt / .md). La IA lo convierte a
          flujos lineales; después elegís cuáles aplicar al playbook general.
        </p>
        <textarea
          className={`${inputCls} font-mono text-xs min-h-[140px]`}
          value={draftText}
          onChange={(e) => setDraftText(e.target.value)}
          placeholder={'Ej: «El internet anda lento» → Fibra / ADSL / Radio…'}
          disabled={busy || converting}
        />
        <div className="flex flex-wrap gap-2 mt-2 items-center">
          <label className="text-xs px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:border-ecolan-brand/40 cursor-pointer">
            Subir archivo
            <input
              type="file"
              accept=".txt,.md,text/plain,text/markdown"
              className="hidden"
              onChange={(e) => void onFile(e)}
              disabled={busy || converting}
            />
          </label>
          <button
            type="button"
            onClick={() => void convert()}
            disabled={busy || converting || !draftText.trim()}
            className="px-3 py-1.5 rounded-lg bg-ecolan-brand hover:bg-ecolan-brand-dark text-xs font-semibold text-white disabled:opacity-50"
          >
            {converting ? "Convirtiendo…" : "Convertir con IA"}
          </button>
        </div>
      </GlassCard>

      {importKeys.length > 0 && (
        <GlassCard title="Vista previa de conversión" accent="emerald" variant="secondary">
          <p className="text-xs text-slate-500 mb-3">
            Marcá los flujos a incorporar. Podés editar pasos antes de aplicar.
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
            {importKeys.map((k) => (
              <label
                key={k}
                className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border cursor-pointer ${
                  selected[k]
                    ? "border-ecolan-brand/50 bg-ecolan-brand/10 text-slate-100"
                    : "border-slate-800 text-slate-400"
                }`}
              >
                <input
                  type="checkbox"
                  checked={Boolean(selected[k])}
                  onChange={(e) =>
                    setSelected((s) => ({ ...s, [k]: e.target.checked }))
                  }
                />
                <span className="font-mono">{k}</span>
                <span className="text-slate-500">({importMap[k]?.length || 0})</span>
              </label>
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-[180px_1fr] gap-3">
            <div className="flex flex-col gap-1">
              {importKeys.map((k) => (
                <button
                  key={k}
                  type="button"
                  onClick={() => setActiveFlow(k)}
                  className={`text-left text-[11px] font-mono px-2 py-1.5 rounded-md ${
                    activeFlow === k
                      ? "bg-slate-800 text-ecolan-brand"
                      : "text-slate-400 hover:bg-slate-900"
                  }`}
                >
                  {k}
                </button>
              ))}
            </div>
            <div>
              {activeFlow && importMap[activeFlow] && (
                <>
                  <p className="text-[11px] font-mono text-slate-500 mb-2">
                    Editando import · {activeFlow}
                  </p>
                  {renderPasoEditor(activeFlow, importMap[activeFlow], "import")}
                </>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={applySelected}
            disabled={busy || converting}
            className="mt-3 px-3 py-1.5 rounded-lg border border-ecolan-brand/40 text-xs font-semibold text-ecolan-brand hover:bg-ecolan-brand/10 disabled:opacity-50"
          >
            Aplicar flujos seleccionados
          </button>
        </GlassCard>
      )}

      <GlassCard title="Playbooks actuales" accent="cyan" variant="secondary">
        <p className="text-xs text-slate-500 mb-3">
          Editor de los flujos ya cargados. Los cambios se guardan con «Guardar
          configuración».
        </p>
        <div className="grid grid-cols-1 lg:grid-cols-[180px_1fr] gap-3">
          <div className="flex flex-col gap-1 max-h-[320px] overflow-y-auto">
            {flowKeys.map((k) => (
              <button
                key={k}
                type="button"
                onClick={() => setActiveFlow(k)}
                className={`text-left text-[11px] font-mono px-2 py-1.5 rounded-md ${
                  activeFlow === k
                    ? "bg-slate-800 text-ecolan-brand"
                    : "text-slate-400 hover:bg-slate-900"
                }`}
              >
                {k}
                <span className="text-slate-600 ml-1">({value[k]?.length || 0})</span>
              </button>
            ))}
          </div>
          <div>
            {activeFlow && value[activeFlow] ? (
              <>
                <p className="text-[11px] font-mono text-slate-500 mb-2">
                  Editando · {activeFlow}
                </p>
                {renderPasoEditor(activeFlow, value[activeFlow], "current")}
              </>
            ) : (
              <p className="text-xs text-slate-500">Sin flujos cargados.</p>
            )}
          </div>
        </div>
      </GlassCard>

      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="text-[11px] text-slate-500 hover:text-slate-300"
        >
          {showAdvanced ? "▾ Ocultar JSON avanzado" : "▸ JSON avanzado"}
        </button>
        {showAdvanced && (
          <div className="mt-2 space-y-2">
            <textarea
              className={`${inputCls} font-mono text-[11px] min-h-[200px]`}
              value={advancedJson}
              onChange={(e) => setAdvancedJson(e.target.value)}
              disabled={busy || converting}
            />
            <button
              type="button"
              onClick={applyAdvancedJson}
              disabled={busy || converting}
              className="text-xs text-slate-300 border border-slate-700 px-3 py-1.5 rounded-lg hover:border-slate-500 disabled:opacity-50"
            >
              Aplicar JSON
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
