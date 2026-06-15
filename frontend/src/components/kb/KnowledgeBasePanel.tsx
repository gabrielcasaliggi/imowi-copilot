"use client";

import { FormEvent, useState } from "react";
import { useApp } from "@/contexts/AppContext";

export function KnowledgeBasePanel() {
  const { kb, createKbArticle } = useApp();
  const [titulo, setTitulo] = useState("");
  const [categoria, setCategoria] = useState("General");
  const [contenido, setContenido] = useState("");
  const [saving, setSaving] = useState(false);

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

  return (
    <div className="p-4 space-y-4 overflow-y-auto">
      <div>
        <h2 className="font-semibold text-slate-100">Centro de Conocimiento</h2>
        <p className="text-[10px] font-mono text-slate-500">
          KB tenant · artículos operativos N1
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="space-y-3">
          {kb.length ? (
            kb.map((a) => (
              <article
                key={a.id}
                className="p-4 rounded-xl border border-slate-800 bg-slate-900/60"
              >
                <div className="flex justify-between mb-1">
                  <h4 className="text-sm font-medium">{a.titulo}</h4>
                  <span className="text-[10px] font-mono text-cyan-300">
                    {a.categoria}
                  </span>
                </div>
                <p className="text-xs text-slate-400 line-clamp-4">{a.contenido}</p>
              </article>
            ))
          ) : (
            <p className="text-slate-500 text-sm">Sin artículos.</p>
          )}
        </div>

        <form
          onSubmit={onSubmit}
          className="rounded-2xl border border-slate-800 bg-slate-900/40 p-4 space-y-3 h-fit"
        >
          <h3 className="text-xs font-mono uppercase text-slate-500">
            Publicar artículo
          </h3>
          <input
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Título"
            className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm"
          />
          <input
            value={categoria}
            onChange={(e) => setCategoria(e.target.value)}
            placeholder="Categoría"
            className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm"
          />
          <textarea
            value={contenido}
            onChange={(e) => setContenido(e.target.value)}
            placeholder="Contenido (pasos, procedimiento...)"
            className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-2 text-sm min-h-[160px]"
          />
          <button
            type="submit"
            disabled={saving}
            className="w-full py-2 rounded-xl font-medium text-slate-950 text-sm disabled:opacity-50"
            style={{ background: "var(--brand)" }}
          >
            {saving ? "Publicando…" : "Publicar"}
          </button>
        </form>
      </div>
    </div>
  );
}
