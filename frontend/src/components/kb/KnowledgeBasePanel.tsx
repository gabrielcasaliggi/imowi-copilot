"use client";

import { FormEvent, useMemo, useState } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  GlassCard,
  KpiCard,
  SectionHeader,
  SidebarSection,
} from "@/components/ui/GlassCard";

const SUGGESTED_CATEGORIES = [
  "Señal y cobertura",
  "Datos / APN",
  "Roaming",
  "JSC",
  "Escalamiento NOC",
  "Procedimientos internos",
] as const;

const INTELLIGENCE_USES = [
  "Mejora respuestas del Copilot en consola de soporte",
  "Refuerza clasificación de síntomas y categorías operativas",
  "Alimenta recomendaciones de próximo paso y escalamiento",
  "Reduce repreguntas cuando el operador usa lenguaje libre",
  "Enriquece sugerencias KB en tickets y casos similares",
] as const;

const CONTENT_GUIDE = [
  "Procedimientos N1 paso a paso (señal, datos, roaming, SIM)",
  "Reglas de escalamiento y criterios para abrir ticket NOC",
  "Excepciones operativas por cooperativa o zona",
  "Integraciones JSC: qué validar antes de automatizar",
  "Playbooks de resolución y criterios de cierre",
] as const;

function formatDate(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("es-AR", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  } catch {
    return iso.slice(0, 10);
  }
}

export function KnowledgeBasePanel() {
  const { kb, createKbArticle } = useApp();
  const [titulo, setTitulo] = useState("");
  const [categoria, setCategoria] = useState("General");
  const [contenido, setContenido] = useState("");
  const [saving, setSaving] = useState(false);
  const [filterCat, setFilterCat] = useState<string | null>(null);

  const categorias = useMemo(() => {
    const set = new Set(kb.map((a) => a.categoria).filter(Boolean));
    return set.size;
  }, [kb]);

  const tecnicos = useMemo(
    () =>
      kb.filter((a) =>
        /señal|senal|datos|apn|roaming|jsc|noc|sim|red/i.test(
          `${a.categoria} ${a.titulo} ${a.contenido}`,
        ),
      ).length,
    [kb],
  );

  const filtered = filterCat
    ? kb.filter((a) => a.categoria.toLowerCase().includes(filterCat.toLowerCase()))
    : kb;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!titulo.trim() || !contenido.trim()) return;
    setSaving(true);
    try {
      await createKbArticle(titulo.trim(), categoria.trim() || "General", contenido.trim());
      setTitulo("");
      setContenido("");
    } finally {
      setSaving(false);
    }
  };

  const inputCls =
    "w-full bg-slate-950 border border-slate-700/80 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-cyan-500/40";

  return (
    <div className="p-4 space-y-6 overflow-y-auto min-h-0">
      <SectionHeader
        title="Intelligence Knowledge Center"
        subtitle="Memoria operativa del tenant · cada artículo hace más inteligente al Copilot"
      />

      <SidebarSection title="Impacto en inteligencia">
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          <KpiCard label="Artículos" value={kb.length} tone="cyan" helper="Base activa del tenant" />
          <KpiCard label="Categorías" value={categorias} tone="emerald" helper="Dominios cubiertos" />
          <KpiCard
            label="Procedimientos técnicos"
            value={tecnicos}
            tone="violet"
            helper="Señal, datos, roaming, JSC…"
          />
        </div>

        <GlassCard title="Cómo alimenta al sistema" variant="primary" className="mt-3">
          <ul className="space-y-2">
            {INTELLIGENCE_USES.map((line) => (
              <li key={line} className="text-xs text-slate-300 flex gap-2 leading-relaxed">
                <span className="text-emerald-400 shrink-0">→</span>
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </GlassCard>
      </SidebarSection>

      <div className="grid grid-cols-1 xl:grid-cols-[1.4fr_1fr] gap-4">
        <div className="space-y-4">
          <SidebarSection title="Biblioteca operativa">
            <div className="flex flex-wrap gap-1.5 mb-2">
              <button
                type="button"
                onClick={() => setFilterCat(null)}
                className={`kb-category-chip ${!filterCat ? "kb-category-chip-active" : ""}`}
              >
                Todas ({kb.length})
              </button>
              {SUGGESTED_CATEGORIES.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => {
                    setFilterCat(cat);
                    setCategoria(cat);
                  }}
                  className={`kb-category-chip ${
                    filterCat === cat ? "kb-category-chip-active" : ""
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>

            {filtered.length ? (
              <div className="space-y-3">
                {filtered.map((a) => (
                  <article
                    key={a.id}
                    className="p-4 rounded-xl border border-slate-800/80 bg-slate-900/50 hover:border-cyan-500/20 transition-colors"
                  >
                    <div className="flex justify-between gap-3 mb-2">
                      <h4 className="text-sm font-semibold text-slate-100">{a.titulo}</h4>
                      <span className="text-[11px] font-mono text-cyan-300 shrink-0">
                        {a.categoria}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 font-mono mb-2">
                      {formatDate(a.created_at)}
                    </p>
                    <p className="text-xs text-slate-400 leading-relaxed line-clamp-5 whitespace-pre-wrap">
                      {a.contenido}
                    </p>
                  </article>
                ))}
              </div>
            ) : (
              <GlassCard variant="secondary">
                <p className="text-slate-500 text-sm">
                  {filterCat
                    ? `Sin artículos en "${filterCat}". Publicá el primero con el formulario.`
                    : "Sin artículos. Cada procedimiento que cargues mejora respuestas y escalamiento."}
                </p>
              </GlassCard>
            )}
          </SidebarSection>
        </div>

        <div className="space-y-4">
          <form
            onSubmit={onSubmit}
            className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-4 space-y-3 h-fit sticky top-4"
          >
            <h3 className="text-xs font-mono uppercase tracking-wider text-slate-400">
              Publicar artículo
            </h3>
            <input
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Título del procedimiento"
              className={inputCls}
            />
            <input
              value={categoria}
              onChange={(e) => setCategoria(e.target.value)}
              placeholder="Categoría"
              className={inputCls}
              list="kb-categories"
            />
            <datalist id="kb-categories">
              {SUGGESTED_CATEGORIES.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            <textarea
              value={contenido}
              onChange={(e) => setContenido(e.target.value)}
              placeholder="Contenido: pasos, criterios, excepciones, integraciones JSC…"
              className={`${inputCls} min-h-[180px] resize-y`}
            />
            <button
              type="submit"
              disabled={saving}
              className="w-full py-2.5 rounded-xl font-semibold text-slate-950 text-sm disabled:opacity-50"
              style={{ background: "var(--brand)" }}
            >
              {saving ? "Publicando…" : "Publicar en KB"}
            </button>
          </form>

          <GlassCard title="Qué incorporar" accent="emerald" variant="secondary">
            <ul className="space-y-2">
              {CONTENT_GUIDE.map((item) => (
                <li key={item} className="text-[11px] text-slate-400 flex gap-2 leading-relaxed">
                  <span className="text-emerald-500/80 shrink-0">+</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
