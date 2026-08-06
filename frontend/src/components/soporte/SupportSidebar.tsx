"use client";

import { FormEvent, useEffect, useState } from "react";
import { DataRow, GlassCard, SidebarSection, SlaBadge } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { inputClsCompact } from "@/components/ui/forms";
import { useToast } from "@/components/ui/Toast";
import { useApp } from "@/contexts/AppContext";
import { FlujoOperativoPanel } from "@/components/soporte/FlujoOperativoPanel";
import { EstadoOperativoPanel } from "@/components/soporte/EstadoOperativoPanel";
import { api } from "@/lib/api-client";
import { ESTADO_CASO_LABELS } from "@/lib/types";
import type { CasoConversacion, TicketSimilar } from "@/lib/types";

function CasoActivoCard({
  caso,
  ticketExistente,
}: {
  caso: CasoConversacion | null;
  ticketExistente: TicketSimilar | null;
}) {
  if (!caso && !ticketExistente) {
    return (
      <GlassCard title="Caso activo" accent="cyan" variant="secondary">
        <p className="text-slate-400 text-xs">Sin caso en curso. Iniciá un reclamo.</p>
      </GlassCard>
    );
  }
  return (
    <GlassCard title="Caso activo" accent="cyan" variant="secondary">
      <div className="space-y-2">
        {caso?.linea_msisdn && (
          <DataRow label="Línea" mono>
            <span className="text-ecolan-brand">{caso.linea_msisdn}</span>
          </DataRow>
        )}
        {caso?.estado && (
          <DataRow label="Estado">
            {ESTADO_CASO_LABELS[caso.estado] || caso.estado}
          </DataRow>
        )}
        {caso?.id && (
          <DataRow label="Caso" mono>
            <span className="text-slate-400 truncate max-w-[160px] inline-block">
              {caso.id.slice(0, 8)}…
            </span>
          </DataRow>
        )}
        {(caso?.ticket_id || ticketExistente?.id) && (
          <DataRow label="Ticket" mono>
            <span className="text-amber-300">{caso?.ticket_id || ticketExistente?.id}</span>
          </DataRow>
        )}
        {caso?.paso_kb_idx !== undefined && caso.paso_kb_idx > 0 && (
          <p className="text-[11px] text-slate-500 pt-1">Paso KB: {caso.paso_kb_idx}</p>
        )}
      </div>
    </GlassCard>
  );
}

function ReclamosSimilares({
  similares,
  onSelect,
}: {
  similares: TicketSimilar[];
  onSelect: (id: string) => void;
}) {
  if (!similares.length) return null;
  return (
    <GlassCard title="Reclamos similares" variant="secondary">
      <div className="space-y-2">
        {similares.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onSelect(t.id)}
            className="w-full text-left p-2.5 rounded-lg border border-slate-700/80 bg-slate-900/60 hover:border-ecolan-brand/35 hover:bg-slate-50/5 shadow-sm transition-all duration-200 ease-in-out"
          >
            <div className="flex justify-between gap-1">
              <span className="font-mono text-ecolan-brand text-[11px]">{t.id}</span>
              <StatusBadge value={t.estado} />
            </div>
            <p className="text-[11px] text-slate-500 truncate mt-0.5">{t.categoria}</p>
            {t.resolucion_tecnica && (
              <p className="text-[11px] text-emerald-400/80 mt-1 line-clamp-2">
                Resuelto: {t.resolucion_tecnica}
              </p>
            )}
          </button>
        ))}
      </div>
    </GlassCard>
  );
}

function FichaAbonadoCard() {
  const { fichaJsc, casoActivo, lineaDetectada } = useApp();
  const linea = fichaJsc?.msisdn || casoActivo?.linea_msisdn || lineaDetectada;
  if (!fichaJsc) {
    return (
      <GlassCard title="Ficha abonado" accent="cyan" variant="secondary">
        {linea ? (
          <div className="space-y-2">
            <DataRow label="Línea / teléfono" mono>
              <span className="text-ecolan-brand">{linea}</span>
            </DataRow>
            <p className="text-[11px] text-amber-300/90 leading-relaxed">
              Sin ficha completa aún. El triaje continúa; al identificar al abonado verás plan,
              estado de servicio y deuda.
            </p>
          </div>
        ) : (
          <p className="text-slate-500 text-xs">
            Ingresá teléfono o DNI del abonado para ver la ficha.
          </p>
        )}
      </GlassCard>
    );
  }
  return (
    <GlassCard title="Ficha abonado" accent="cyan" variant="secondary">
      <div className="space-y-2">
        <DataRow label="Teléfono" mono>
          <span className="text-ecolan-brand">{fichaJsc.msisdn}</span>
        </DataRow>
        <DataRow label="Abonado">{fichaJsc.abonado}</DataRow>
        <DataRow label="Plan">{fichaJsc.plan}</DataRow>
        <div className="flex justify-between gap-2 items-center text-xs">
          <span className="text-slate-500">Servicio</span>
          <StatusBadge value={fichaJsc.estado_linea} />
        </div>
        <div className="flex justify-between gap-2 items-center text-xs">
          <span className="text-slate-500">Cuenta</span>
          <span className="flex gap-2 items-center">
            <StatusBadge value={fichaJsc.estado_cuenta} />
            <span className="text-slate-400">{fichaJsc.saldo_resumen}</span>
          </span>
        </div>
      </div>
    </GlassCard>
  );
}

function NotaInternaForm({
  onSubmit,
}: {
  onSubmit: (detalle: string) => Promise<void>;
}) {
  const [nota, setNota] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const txt = nota.trim();
    if (!txt || saving) return;
    setSaving(true);
    try {
      await onSubmit(txt);
      setNota("");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <textarea
        value={nota}
        onChange={(e) => setNota(e.target.value)}
        placeholder="Nota interna (no visible al abonado)…"
        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-[11px] min-h-[56px]"
      />
      <button
        type="submit"
        disabled={!nota.trim() || saving}
        className="w-full py-1.5 rounded border border-slate-600 text-slate-300 hover:bg-slate-800/60 text-[11px] disabled:opacity-40"
      >
        {saving ? "Guardando…" : "Agregar nota interna"}
      </button>
    </form>
  );
}

function PlantillasRespuesta({
  categoria,
  onPick,
}: {
  categoria?: string;
  onPick: (contenido: string, nombre: string) => void;
}) {
  const { tenantSlug, isAdmin } = useApp();
  const [plantillas, setPlantillas] = useState<
    { id: string; nombre: string; categoria: string; contenido: string }[]
  >([]);

  useEffect(() => {
    api
      .responseTemplates(categoria, isAdmin ? tenantSlug : undefined)
      .then((r) => setPlantillas(r.plantillas || []))
      .catch(() => setPlantillas([]));
  }, [categoria, tenantSlug, isAdmin]);

  if (!plantillas.length) return null;

  return (
    <GlassCard title="Plantillas de respuesta" variant="secondary">
      <div className="space-y-1.5 max-h-40 overflow-y-auto">
        {plantillas.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => onPick(p.contenido, p.nombre)}
            className="w-full text-left p-2 rounded-lg border border-slate-700/80 hover:border-ecolan-brand/35 hover:bg-slate-50/5 text-[11px] transition-all duration-200 ease-in-out"
          >
            <span className="text-slate-200">{p.nombre}</span>
            <span className="text-slate-600 ml-1">· {p.categoria}</span>
          </button>
        ))}
      </div>
    </GlassCard>
  );
}

function PublicarKbButton({
  ticketId,
  onPublish,
}: {
  ticketId: string;
  onPublish: (body?: {
    titulo?: string;
    categoria?: string;
    contenido?: string;
  }) => Promise<void>;
}) {
  const { tenantSlug, isAdmin } = useApp();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [titulo, setTitulo] = useState("");
  const [categoria, setCategoria] = useState("");
  const [contenido, setContenido] = useState("");
  const [feedback, setFeedback] = useState("");

  const loadDraft = async () => {
    setLoading(true);
    setFeedback("");
    try {
      const res = await api.ticketKbDraft(ticketId, isAdmin ? tenantSlug : undefined);
      setTitulo(res.borrador.titulo || "");
      setCategoria(res.borrador.categoria || "General");
      setContenido(res.borrador.contenido || "");
      setOpen(true);
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : "No se pudo cargar el borrador");
    } finally {
      setLoading(false);
    }
  };

  const inputCls = inputClsCompact;

  if (!open) {
    return (
      <div className="space-y-1.5">
        <button
          type="button"
          disabled={loading}
          onClick={loadDraft}
          className="w-full py-1.5 rounded border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/10 text-[11px] disabled:opacity-40"
        >
          {loading ? "Preparando…" : "Proponer mejora a KB"}
        </button>
        <p className="text-[10px] text-slate-400 leading-relaxed">
          Envía el caso a la bandeja del admin. No se publica hasta aprobación.
        </p>
        {feedback && <p className="text-[10px] text-amber-300">{feedback}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <input
        className={inputCls}
        value={titulo}
        onChange={(e) => setTitulo(e.target.value)}
        placeholder="Título"
      />
      <input
        className={inputCls}
        value={categoria}
        onChange={(e) => setCategoria(e.target.value)}
        placeholder="Categoría"
      />
      <textarea
        className={`${inputCls} min-h-[100px] resize-y`}
        value={contenido}
        onChange={(e) => setContenido(e.target.value)}
        placeholder="Procedimiento / resolución"
      />
      <div className="flex gap-1.5">
        <button
          type="button"
          disabled={loading || !titulo.trim() || !contenido.trim()}
          onClick={async () => {
            setLoading(true);
            setFeedback("");
            try {
              await onPublish({
                titulo: titulo.trim(),
                categoria: categoria.trim() || "General",
                contenido: contenido.trim(),
              });
              setFeedback("Propuesta enviada a revisión admin.");
              setOpen(false);
            } catch (err) {
              setFeedback(err instanceof Error ? err.message : "Error al proponer");
            } finally {
              setLoading(false);
            }
          }}
          className="flex-1 py-1.5 rounded border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/10 text-[11px] disabled:opacity-40"
        >
          {loading ? "Enviando…" : "Enviar a revisión"}
        </button>
        <button
          type="button"
          disabled={loading}
          onClick={() => setOpen(false)}
          className="px-2 py-1.5 rounded border border-slate-700 text-slate-400 text-[11px]"
        >
          Cancelar
        </button>
      </div>
      {feedback && <p className="text-[10px] text-ecolan-brand/90">{feedback}</p>}
    </div>
  );
}

function TicketAdminForm({
  ticket,
  onUpdate,
  onExplain,
}: {
  ticket: NonNullable<ReturnType<typeof useApp>["ticketFormacion"]>;
  onUpdate: (body: Record<string, string>) => Promise<void>;
  onExplain: () => Promise<string | null>;
}) {
  const [nivel, setNivel] = useState(ticket.nivel || "N1");
  const [estado, setEstado] = useState(ticket.estado || "Abierto");
  const [proveedor, setProveedor] = useState(ticket.proveedor || "");
  const [resolucion, setResolucion] = useState("");
  const [explicacion, setExplicacion] = useState("");

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    onUpdate({
      nivel,
      estado,
      proveedor,
      resolucion_tecnica: resolucion,
      destino: nivel === "N2" ? "n2_soporte" : "cooperativa",
    });
  };

  const onExplainClick = async () => {
    const txt = await onExplain();
    if (txt) setExplicacion(txt);
  };

  return (
    <form onSubmit={onSubmit} className="pt-2 mt-2 border-t border-slate-800 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <select
          value={nivel}
          onChange={(e) => setNivel(e.target.value)}
          className="bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-[11px]"
        >
          <option value="N1">N1</option>
          <option value="N2">N2</option>
        </select>
        <select
          value={estado}
          onChange={(e) => setEstado(e.target.value)}
          className="bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-[11px]"
        >
          {["Abierto", "En Revisión", "Escalado", "Pendiente Cliente", "Cerrado"].map(
            (e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ),
          )}
        </select>
      </div>
      <input
        value={proveedor}
        onChange={(e) => setProveedor(e.target.value)}
        placeholder="Proveedor sugerido / referencia"
        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-[11px]"
      />
      <textarea
        value={resolucion}
        onChange={(e) => setResolucion(e.target.value)}
        placeholder="Agregar avance visible para la cooperativa..."
        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-[11px] min-h-[54px]"
      />
      <button
        type="submit"
        className="w-full py-2 rounded-lg border border-ecolan-brand/40 text-ecolan-brand font-medium hover:bg-ecolan-brand/10 transition-all duration-200 ease-in-out"
      >
        Actualizar seguimiento
      </button>
      <button
        type="button"
        onClick={onExplainClick}
        className="w-full py-2 rounded-lg border border-ecolan-brand/40 text-ecolan-brand font-medium hover:bg-ecolan-brand/10 transition-all duration-200 ease-in-out text-[11px]"
      >
        Explicar escalamiento
      </button>
      {explicacion && (
        <pre className="text-[11px] text-slate-400 whitespace-pre-wrap bg-slate-950/80 p-2 rounded max-h-32 overflow-y-auto">
          {explicacion}
        </pre>
      )}
    </form>
  );
}

function TicketAgentForm({
  ticket,
  onUpdate,
}: {
  ticket: NonNullable<ReturnType<typeof useApp>["ticketFormacion"]>;
  onUpdate: (body: Record<string, string>) => Promise<void>;
}) {
  const [estado, setEstado] = useState(ticket.estado || "Abierto");
  const [resolucion, setResolucion] = useState(ticket.resolucion_tecnica || "");

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    onUpdate({
      estado,
      resolucion_tecnica: resolucion,
    });
  };

  return (
    <form onSubmit={onSubmit} className="pt-2 mt-2 border-t border-slate-800 space-y-2">
      <select
        value={estado}
        onChange={(e) => setEstado(e.target.value)}
        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-[11px]"
      >
        {["Abierto", "En Revisión", "Pendiente Cliente", "Cerrado"].map((e) => (
          <option key={e} value={e}>
            {e}
          </option>
        ))}
      </select>
      <textarea
        value={resolucion}
        onChange={(e) => setResolucion(e.target.value)}
        placeholder="Qué hiciste / resolución del caso…"
        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1.5 text-[11px] min-h-[54px]"
      />
      <button
        type="submit"
        className="w-full py-2 rounded-lg border border-ecolan-brand/40 text-ecolan-brand font-medium hover:bg-ecolan-brand/10 transition-all duration-200 ease-in-out"
      >
        Guardar seguimiento
      </button>
      <p className="text-[10px] text-slate-500 leading-relaxed">
        Si resolviste bien, proponé una mejora a KB abajo. Si no, dejá el caso documentado para
        ticket externo (JSAT) más adelante.
      </p>
    </form>
  );
}

function TicketFormacionCard() {
  const { ticketFormacion, isAdmin, updateTicket, explainEscalation } = useApp();

  if (!ticketFormacion) {
    return (
      <GlassCard title="Ticket activo" variant="secondary">
        <p className="text-slate-500 text-xs leading-relaxed">
          Todavía no hay un ticket en esta consola. Tomá uno desde la{" "}
          <a href="/tickets" className="text-ecolan-brand hover:text-ecolan-brand">
            Cola
          </a>
          .
        </p>
      </GlassCard>
    );
  }

  const t = ticketFormacion;
  const intel = t.intelligence;

  return (
    <GlassCard title="Ticket activo" variant="secondary">
      <div className="space-y-2 text-xs">
        <DataRow label="ID" mono>
          <span className="text-ecolan-brand">{t.id}</span>
        </DataRow>
        {t.asignado_a && (
          <DataRow label="Asignado">
            <span className="text-ecolan-brand truncate">{t.asignado_a}</span>
          </DataRow>
        )}
        {intel && intel.priority_score > 0 && (
          <div className="p-2.5 rounded-lg border border-ecolan-brand/20 bg-ecolan-brand/5 space-y-1.5">
            <div className="flex justify-between">
              <span className="text-ecolan-brand">Score IA</span>
              <span>
                {intel.priority_score}/100 · {intel.risk_level}
              </span>
            </div>
            <p className="text-[11px] text-slate-400">Causa: {intel.probable_cause}</p>
            <p className="text-[11px] text-ecolan-brand/90">→ {intel.next_best_action}</p>
            {(t.sla_label || intel.sla?.label) && (
              <div className="pt-1">
                <SlaBadge
                  label={t.sla_label || intel.sla?.label}
                  estado={t.estado_sla || intel.sla?.estado_sla}
                />
              </div>
            )}
          </div>
        )}
        <DataRow label="Línea" mono>
          {t.linea}
        </DataRow>
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {t.nivel && <StatusBadge value={t.nivel} />}
          <StatusBadge value={t.estado} />
        </div>
        {t.motivo_escalamiento && (
          <p className="text-slate-400 text-[11px] leading-relaxed">{t.motivo_escalamiento}</p>
        )}
        {isAdmin ? (
          <TicketAdminForm
            key={t.id}
            ticket={t}
            onUpdate={updateTicket}
            onExplain={explainEscalation}
          />
        ) : (
          <TicketAgentForm key={t.id} ticket={t} onUpdate={updateTicket} />
        )}
      </div>
    </GlassCard>
  );
}

export function SupportSidebar() {
  const {
    ticketTimeline,
    ticketFormacion,
    notifications,
    tickets,
    selectTicket,
    casoActivo,
    ticketsSimilares,
    ticketExistente,
    flujoOperativo,
    ticketKbSuggestions,
    ticketLearning,
    isAdmin,
    can,
    addTicketNote,
    publishTicketKb,
    appendTrace,
    insertConsoleReply,
  } = useApp();

  const isSupervisor = can("tickets.reassign");
  const { push: toast } = useToast();

  const onPickPlantilla = async (contenido: string, nombre: string) => {
    insertConsoleReply(contenido);
    try {
      await navigator.clipboard?.writeText(contenido);
      toast(`Plantilla «${nombre}» insertada`, "success");
      appendTrace([`Plantilla «${nombre}» insertada en el composer`]);
    } catch {
      toast(`Plantilla «${nombre}» insertada`, "success");
      appendTrace([`Plantilla «${nombre}» insertada en el composer`]);
    }
  };

  const TimelineBlock = () => (
    <GlassCard title="Historial del ticket" variant="secondary">
      {!ticketFormacion ? (
        <p className="text-slate-400 text-xs font-mono">
          Seleccioná un ticket para ver avances.
        </p>
      ) : !ticketTimeline.length ? (
        <p className="text-slate-400 text-xs font-mono">Sin eventos todavía.</p>
      ) : (
        <div className="space-y-3">
          {ticketTimeline.map((ev) => (
            <div
              key={ev.id}
              className={`pl-3 border-l ${
                ev.visible_cliente === "No"
                  ? "border-ecolan-brand/40"
                  : "border-ecolan-brand/30"
              }`}
            >
              <div className="flex justify-between gap-2">
                <p className="text-xs text-slate-200 font-medium">{ev.titulo}</p>
                <span className="flex gap-1 items-center">
                  {ev.visible_cliente === "No" && (
                    <span className="text-[9px] font-mono text-ecolan-brand uppercase">
                      interno
                    </span>
                  )}
                  {ev.nivel && <StatusBadge value={ev.nivel} />}
                </span>
              </div>
              <p className="text-[11px] text-slate-500 font-mono mt-0.5">
                {ev.tipo}
                {ev.estado ? ` · ${ev.estado}` : ""}
                {ev.actor ? ` · ${ev.actor}` : ""}
                {ev.created_at
                  ? ` · ${ev.created_at.slice(0, 16).replace("T", " ")}`
                  : ""}
              </p>
              {ev.detalle && (
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">{ev.detalle}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </GlassCard>
  );

  // Agente: contexto del ticket tomado (no flujo N1 del asistente)
  if (!isAdmin && !isSupervisor) {
    return (
      <div className="flex flex-col min-h-0 h-full overflow-y-auto p-3 gap-5">
        <SidebarSection title="Caso que estás atendiendo" sticky defaultOpen>
          <TicketFormacionCard />
          <PlantillasRespuesta
            categoria={ticketFormacion?.categoria}
            onPick={onPickPlantilla}
          />
          {ticketFormacion && (
            <GlassCard title="Notas internas" variant="secondary">
              <NotaInternaForm onSubmit={(d) => addTicketNote(d, true)} />
            </GlassCard>
          )}
          {ticketFormacion && (
            <GlassCard title="Proponer a KB" variant="secondary">
              <PublicarKbButton
                ticketId={ticketFormacion.id}
                onPublish={publishTicketKb}
              />
            </GlassCard>
          )}
          {ticketKbSuggestions.length > 0 && (
            <GlassCard title="KB sugerida" variant="secondary">
              <div className="space-y-2.5">
                {ticketKbSuggestions.map((k) => (
                  <div
                    key={k.id}
                    className="text-xs border-b border-slate-800/60 pb-2.5 last:border-0"
                  >
                    <p className="text-slate-200 font-medium">{k.titulo}</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">{k.categoria}</p>
                    <p className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                      {k.fragmento}
                    </p>
                  </div>
                ))}
              </div>
            </GlassCard>
          )}
        </SidebarSection>

        <SidebarSection title="Historial del ticket" defaultOpen={false}>
          <TimelineBlock />
        </SidebarSection>
      </div>
    );
  }

  // Supervisor: seguimiento + trazabilidad completa (sin mesa N1)
  if (!isAdmin && isSupervisor) {
    return (
      <div className="flex flex-col min-h-0 h-full overflow-y-auto p-3 gap-5">
        <SidebarSection title="Seguimiento supervisor" sticky defaultOpen>
          <TicketFormacionCard />
          {ticketFormacion && (
            <GlassCard title="Notas internas" variant="secondary">
              <NotaInternaForm onSubmit={(d) => addTicketNote(d, true)} />
            </GlassCard>
          )}
        </SidebarSection>
        <SidebarSection title="Trazabilidad N2" defaultOpen={false}>
          <TimelineBlock />
          {ticketLearning?.postmortem && (
            <GlassCard title="Aprendizaje operativo" accent="emerald" variant="secondary">
              <pre className="text-[11px] text-slate-400 whitespace-pre-wrap leading-relaxed">
                {ticketLearning.postmortem}
              </pre>
            </GlassCard>
          )}
        </SidebarSection>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-0 h-full overflow-y-auto p-3 gap-5">
      <SidebarSection title="Resumen operativo" sticky defaultOpen>
        <CasoActivoCard caso={casoActivo} ticketExistente={ticketExistente} />
        <FlujoOperativoPanel flujo={flujoOperativo} />
        <EstadoOperativoPanel />
      </SidebarSection>

      <SidebarSection title="Contexto del abonado" defaultOpen>
        <FichaAbonadoCard />
        <TicketFormacionCard />
        <PlantillasRespuesta
          categoria={ticketFormacion?.categoria}
          onPick={onPickPlantilla}
        />
        {ticketFormacion && (
          <GlassCard title="Notas internas" variant="secondary">
            <NotaInternaForm onSubmit={(d) => addTicketNote(d, true)} />
          </GlassCard>
        )}
        {ticketFormacion && (
          <GlassCard title="Conocimiento" variant="secondary">
            <PublicarKbButton
              ticketId={ticketFormacion.id}
              onPublish={publishTicketKb}
            />
          </GlassCard>
        )}

        {ticketKbSuggestions.length > 0 && (
          <GlassCard title="KB sugerida" variant="secondary">
            <div className="space-y-2.5">
              {ticketKbSuggestions.map((k) => (
                <div key={k.id} className="text-xs border-b border-slate-800/60 pb-2.5 last:border-0">
                  <p className="text-slate-200 font-medium">{k.titulo}</p>
                  <p className="text-[11px] text-slate-400 mt-0.5">{k.categoria}</p>
                  <p className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                    {k.fragmento}
                  </p>
                </div>
              ))}
            </div>
          </GlassCard>
        )}
      </SidebarSection>

      <SidebarSection title="Evidencia e historial" defaultOpen={false}>
        {ticketLearning?.postmortem && (
          <GlassCard title="Aprendizaje operativo" accent="emerald" variant="secondary">
            <pre className="text-[11px] text-slate-400 whitespace-pre-wrap leading-relaxed">
              {ticketLearning.postmortem}
            </pre>
          </GlassCard>
        )}

        <ReclamosSimilares similares={ticketsSimilares} onSelect={selectTicket} />

        <GlassCard title="Historial del ticket" variant="secondary">
          {!ticketFormacion ? (
            <p className="text-slate-400 text-xs font-mono">
              Seleccioná un ticket para ver avances.
            </p>
          ) : !ticketTimeline.length ? (
            <p className="text-slate-400 text-xs font-mono">Sin eventos todavía.</p>
          ) : (
            <div className="space-y-3">
              {ticketTimeline.map((ev) => (
                <div
                  key={ev.id}
                  className={`pl-3 border-l ${
                    ev.visible_cliente === "No"
                      ? "border-ecolan-brand/40"
                      : "border-ecolan-brand/30"
                  }`}
                >
                  <div className="flex justify-between gap-2">
                    <p className="text-xs text-slate-200 font-medium">{ev.titulo}</p>
                    <span className="flex gap-1 items-center">
                      {ev.visible_cliente === "No" && (
                        <span className="text-[9px] font-mono text-ecolan-brand uppercase">
                          interno
                        </span>
                      )}
                      {ev.nivel && <StatusBadge value={ev.nivel} />}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                    {ev.estado}
                    {ev.actor ? ` · ${ev.actor}` : ""}
                  </p>
                  {ev.detalle && (
                    <p className="text-xs text-slate-400 mt-1 leading-relaxed">{ev.detalle}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard title="Notificaciones" accent="amber" variant="secondary">
          {!notifications.length ? (
            <p className="text-slate-400 text-xs font-mono">Sin novedades.</p>
          ) : (
            <div className="space-y-2">
              {notifications.slice(0, 5).map((n) => (
                <div
                  key={n.id}
                  className={`p-2.5 rounded-lg border ${
                    n.leida === "No"
                      ? "border-amber-500/30 bg-amber-500/10"
                      : "border-slate-800 bg-slate-900/50"
                  }`}
                >
                  <div className="flex justify-between gap-2">
                    <p className="text-xs text-slate-200 font-medium">{n.titulo}</p>
                    <span className="text-[11px] font-mono text-slate-400">{n.leida}</span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">{n.mensaje}</p>
                </div>
              ))}
            </div>
          )}
        </GlassCard>

        {isAdmin ? (
          <GlassCard title="Atajos" variant="secondary">
            <p className="text-xs text-slate-400 mb-2">
              La cola por riesgo está en el panel principal. Usá estos atajos para no duplicar listas.
            </p>
            <div className="flex flex-wrap gap-2">
              <a
                href="/tickets"
                className="text-[11px] font-mono px-2.5 py-1.5 rounded-lg border border-ecolan-brand/40 text-ecolan-brand hover:bg-ecolan-brand/10 transition-all duration-200 ease-in-out"
              >
                Cola filtrable →
              </a>
              <a
                href="/estadisticas"
                className="text-[11px] font-mono px-2.5 py-1 rounded border border-slate-600 text-slate-300 hover:bg-slate-800/50"
              >
                Estadísticas →
              </a>
            </div>
          </GlassCard>
        ) : (
          <GlassCard title="Mis tickets recientes" variant="secondary" className="min-h-[120px]">
            {!tickets.length ? (
              <p className="text-slate-400 text-xs">Sin tickets.</p>
            ) : (
              <div className="space-y-2">
                {tickets.slice(0, 6).map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => selectTicket(t.id)}
                    className="w-full text-left p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 hover:border-ecolan-brand/30 transition-colors"
                  >
                    <div className="flex justify-between items-center gap-1">
                      <span className="font-mono text-ecolan-brand text-[11px]">{t.id}</span>
                      <span className="flex gap-1 items-center">
                        {t.nivel && <StatusBadge value={t.nivel} />}
                        <StatusBadge value={t.estado} />
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 truncate mt-0.5">
                      {t.linea}
                      {t.asignado_a ? ` · ${t.asignado_a}` : ""}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </GlassCard>
        )}
      </SidebarSection>
    </div>
  );
}
