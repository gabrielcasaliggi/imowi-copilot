"use client";

import { FormEvent, useMemo, useState } from "react";
import { useApp } from "@/contexts/AppContext";
import {
  GlassCard,
  KpiCard,
  SectionHeader,
  SidebarSection,
} from "@/components/ui/GlassCard";
import { KbReviewTray } from "@/components/kb/KbReviewTray";
import { inputCls } from "@/components/ui/forms";
import { getBranding } from "@/lib/brand";

const SUGGESTED_CATEGORIES = [
  "Internet Ecolan",
  "Móvil",
  "Facturación / deuda",
  "WhatsApp N1",
  "Escalamiento N2",
  "Procedimientos internos",
] as const;

function intelligenceUses(botName: string) {
  return [
    `Mejora respuestas de ${botName} en la consola`,
    "Refuerza clasificación de síntomas (internet, móvil, deuda)",
    "Alimenta recomendaciones de próximo paso y escalamiento N2",
    "Reduce repreguntas cuando el agente usa lenguaje libre",
    "Enriquece sugerencias KB en tickets y casos similares",
  ] as const;
}

const CONTENT_GUIDE = [
  "Procedimientos N1 paso a paso (módem, WiFi, señal móvil)",
  "Reglas de escalamiento y criterios para abrir ticket N2",
  "Excepciones operativas por zona o plan Ecolan",
  "Medios de pago y rehabilitación tras corte por deuda",
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
  const {
    kb,
    createKbArticle,
    proposeKbArticle,
    deleteKbArticle,
    isAdmin,
    tenantSlug,
    tenantContext,
  } = useApp();
  const botName = getBranding().botDisplayName;
  const uses = intelligenceUses(botName);
  const [titulo, setTitulo] = useState("");
  const [categoria, setCategoria] = useState("General");
  const [contenido, setContenido] = useState("");
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [filterCat, setFilterCat] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");

  const tenantLabel =
    tenantContext?.organizacion_nombre ||
    tenantSlug ||
    "cooperativa activa";

  const categorias = useMemo(() => {
    const set = new Set(kb.map((a) => a.categoria).filter(Boolean));
    return set.size;
  }, [kb]);

  const tecnicos = useMemo(
    () =>
      kb.filter((a) =>
        /ecolan|internet|módem|modem|wifi|móvil|movil|deuda|factura|whatsapp|n2|sim|señal|senal/i.test(
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
    setFeedback("");
    try {
      if (isAdmin) {
        await createKbArticle(
          titulo.trim(),
          categoria.trim() || "General",
          contenido.trim(),
        );
        setFeedback("Artículo publicado en la KB.");
      } else {
        await proposeKbArticle(
          titulo.trim(),
          categoria.trim() || "General",
          contenido.trim(),
        );
        setFeedback("Propuesta enviada a la bandeja del administrador.");
      }
      setTitulo("");
      setContenido("");
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "No se pudo guardar");
    } finally {
      setSaving(false);
    }
  };

  const onDelete = async (id: string, tituloArt: string) => {
    if (!window.confirm(`¿Eliminar «${tituloArt}»? Esta acción no se puede deshacer.`)) {
      return;
    }
    setDeletingId(id);
    setFeedback("");
    try {
      await deleteKbArticle(id);
      setFeedback("Artículo eliminado.");
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "No se pudo eliminar");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="p-4 space-y-6 overflow-y-auto min-h-0">
      <SectionHeader
        title="Intelligence Knowledge Center"
        subtitle={`Memoria operativa · ${tenantLabel} · cada artículo mejora a ${botName} (N1/N2)`}
      />

      {isAdmin && (
        <p className="text-[11px] text-slate-500 -mt-3 mb-1">
          La biblioteca muestra solo la KB de la cooperativa seleccionada arriba
          {tenantSlug ? ` (${tenantSlug})` : ""}. Si aprobás una propuesta de otra
          coop, el sistema cambia el tenant automáticamente.
        </p>
      )}

      {isAdmin && (
        <SidebarSection title="Revisión de aportes">
          <KbReviewTray />
        </SidebarSection>
      )}

      <SidebarSection title="Impacto en inteligencia">
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
          <KpiCard label="Artículos" value={kb.length} tone="cyan" helper="Base activa del tenant" />
          <KpiCard label="Categorías" value={categorias} tone="emerald" helper="Dominios cubiertos" />
          <KpiCard
            label="Procedimientos técnicos"
            value={tecnicos}
            tone="violet"
            helper="Ecolan, móvil, deuda…"
          />
        </div>

        <GlassCard title="Cómo alimenta al sistema" variant="primary" className="mt-3">
          <ul className="space-y-2">
            {uses.map((line) => (
              <li key={line} className="text-xs text-slate-300 flex gap-2 leading-relaxed">
                <span className="text-ecolan-brand shrink-0">→</span>
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
                    className="p-4 rounded-xl border border-slate-800/80 bg-slate-900/50 hover:border-ecolan-brand/20 transition-colors"
                  >
                    <div className="flex justify-between gap-3 mb-2">
                      <h4 className="text-sm font-semibold text-slate-100">{a.titulo}</h4>
                      <div className="flex items-start gap-2 shrink-0">
                        <span className="text-[11px] font-mono text-ecolan-brand">
                          {a.categoria}
                        </span>
                        {isAdmin && (
                          <button
                            type="button"
                            onClick={() => void onDelete(a.id, a.titulo)}
                            disabled={deletingId === a.id}
                            className="text-[11px] text-rose-400/90 hover:text-rose-300 disabled:opacity-50"
                          >
                            {deletingId === a.id ? "…" : "Eliminar"}
                          </button>
                        )}
                      </div>
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
              {isAdmin ? "Publicar artículo (admin)" : "Proponer mejora a KB"}
            </h3>
            {!isAdmin && (
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Tu aporte llega a la bandeja del administrador. No se publica hasta que lo apruebe.
              </p>
            )}
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
              placeholder="Contenido: pasos N1, criterios N2, medios de pago, excepciones Ecolan…"
              className={`${inputCls} min-h-[180px] resize-y`}
            />
            <button
              type="submit"
              disabled={saving}
              className="w-full py-2.5 rounded-xl font-semibold text-white text-sm bg-ecolan-brand hover:bg-ecolan-brand-dark disabled:opacity-50 shadow-sm transition-all duration-200 ease-in-out"
            >
              {saving
                ? isAdmin
                  ? "Publicando…"
                  : "Enviando…"
                : isAdmin
                  ? "Publicar en KB"
                  : "Enviar a revisión"}
            </button>
            {feedback && (
              <p className="text-[11px] text-ecolan-brand/90 text-center">{feedback}</p>
            )}
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
