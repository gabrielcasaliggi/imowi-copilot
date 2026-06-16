"use client";

import { FormEvent, useState } from "react";
import { DataRow, GlassCard, SidebarSection, SlaBadge } from "@/components/ui/GlassCard";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useApp } from "@/contexts/AppContext";
import { FlujoOperativoPanel } from "@/components/soporte/FlujoOperativoPanel";
import { EstadoOperativoPanel } from "@/components/soporte/EstadoOperativoPanel";
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
        <p className="text-slate-500 text-xs">Sin caso en curso. Iniciá un reclamo.</p>
      </GlassCard>
    );
  }
  return (
    <GlassCard title="Caso activo" accent="cyan" variant="secondary">
      <div className="space-y-2">
        {caso?.linea_msisdn && (
          <DataRow label="Línea" mono>
            <span className="text-cyan-300">{caso.linea_msisdn}</span>
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
            className="w-full text-left p-2.5 rounded-lg border border-slate-800 bg-slate-900/60 hover:border-cyan-500/30 transition-colors"
          >
            <div className="flex justify-between gap-1">
              <span className="font-mono text-cyan-300 text-[11px]">{t.id}</span>
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

function FichaJscCard() {
  const { fichaJsc, casoActivo, lineaDetectada } = useApp();
  const linea = fichaJsc?.msisdn || casoActivo?.linea_msisdn || lineaDetectada;
  if (!fichaJsc) {
    return (
      <GlassCard title="Ficha JSC" accent="cyan" variant="secondary">
        {linea ? (
          <div className="space-y-2">
            <DataRow label="Línea detectada" mono>
              <span className="text-cyan-300">{linea}</span>
            </DataRow>
            <p className="text-[11px] text-amber-300/90 leading-relaxed">
              No figura en el catálogo operativo del tenant. El triaje continúa, pero conviene
              importar o sincronizar la línea para validar abonado, plan y estado de cuenta.
            </p>
          </div>
        ) : (
          <p className="text-slate-500 text-xs">Ingresá la línea para consultar el catálogo operativo.</p>
        )}
      </GlassCard>
    );
  }
  return (
    <GlassCard title="Ficha JSC" accent="cyan" variant="secondary">
      <div className="space-y-2">
        <DataRow label="MSISDN" mono>
          <span className="text-cyan-300">{fichaJsc.msisdn}</span>
        </DataRow>
        <DataRow label="Abonado">{fichaJsc.abonado}</DataRow>
        <DataRow label="Plan">{fichaJsc.plan}</DataRow>
        <div className="flex justify-between gap-2 items-center text-xs">
          <span className="text-slate-500">Línea</span>
          <StatusBadge value={fichaJsc.estado_linea} />
        </div>
        <div className="flex justify-between gap-2 items-center text-xs">
          <span className="text-slate-500">Cuenta</span>
          <span className="flex gap-2 items-center">
            <StatusBadge value={fichaJsc.estado_cuenta} />
            <span className="text-slate-400">{fichaJsc.saldo_resumen}</span>
          </span>
        </div>
        <p className="text-[11px] text-slate-500 pt-1">
          APN {fichaJsc.apn} · Roaming {fichaJsc.roaming_habilitado}
        </p>
      </div>
    </GlassCard>
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
      destino: nivel === "N2" ? "imowi_noc" : "cooperativa",
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
        className="w-full py-1.5 rounded border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/10"
      >
        Actualizar seguimiento
      </button>
      <button
        type="button"
        onClick={onExplainClick}
        className="w-full py-1.5 rounded border border-violet-500/30 text-violet-300 hover:bg-violet-500/10 text-[11px]"
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

function TicketFormacionCard() {
  const { ticketFormacion, isAdmin, updateTicket, explainEscalation } = useApp();

  if (!ticketFormacion) {
    return (
      <GlassCard title="Ticket en formación" variant="secondary">
        <p className="text-slate-500 text-xs font-mono">Pendiente de escalamiento.</p>
      </GlassCard>
    );
  }

  const t = ticketFormacion;
  const intel = t.intelligence;

  return (
    <GlassCard title="Ticket en formación" variant="secondary">
      <div className="space-y-2 text-xs">
        <DataRow label="ID" mono>
          <span className="text-cyan-300">{t.id}</span>
        </DataRow>
        {intel && intel.priority_score > 0 && (
          <div className="p-2.5 rounded-lg border border-violet-500/20 bg-violet-500/5 space-y-1.5">
            <div className="flex justify-between">
              <span className="text-violet-300">Score IA</span>
              <span>
                {intel.priority_score}/100 · {intel.risk_level}
              </span>
            </div>
            <p className="text-[11px] text-slate-400">Causa: {intel.probable_cause}</p>
            <p className="text-[11px] text-cyan-400/90">→ {intel.next_best_action}</p>
            {(t.sla_label || intel.sla?.label) && (
              <div className="pt-1">
                <SlaBadge
                  label={t.sla_label || intel.sla?.label}
                  estado={t.estado_sla || intel.sla?.estado_sla}
                />
              </div>
            )}
            {intel.risk_reasons?.length ? (
              <p className="text-[11px] text-slate-500">{intel.risk_reasons.join(" · ")}</p>
            ) : null}
          </div>
        )}
        <DataRow label="Línea" mono>
          {t.linea}
        </DataRow>
        <div className="flex flex-wrap gap-1.5 pt-0.5">
          {t.nivel && <StatusBadge value={t.nivel} />}
          {t.destino && (
            <span className="px-2 py-0.5 text-[11px] font-mono uppercase rounded border bg-slate-600/30 text-slate-300 border-slate-500/30">
              {t.destino}
            </span>
          )}
          <StatusBadge value={t.origen} />
          <StatusBadge value={t.estado} />
        </div>
        {t.proveedor && (
          <p className="text-amber-300 text-[11px]">→ {t.proveedor}</p>
        )}
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
          <p className="text-[11px] text-slate-500 pt-2 mt-2 border-t border-slate-800 leading-relaxed">
            Vista de seguimiento: el NOC actualizará el estado y las novedades del ticket.
          </p>
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
  } = useApp();

  return (
    <div className="flex flex-col min-h-0 h-full overflow-y-auto p-3 gap-5">
      <SidebarSection title="Resumen operativo">
        <CasoActivoCard caso={casoActivo} ticketExistente={ticketExistente} />
        <FlujoOperativoPanel flujo={flujoOperativo} />
        <EstadoOperativoPanel />
      </SidebarSection>

      <SidebarSection title="Contexto técnico">
        <FichaJscCard />
        <TicketFormacionCard />

        {ticketKbSuggestions.length > 0 && (
          <GlassCard title="KB sugerida" variant="secondary">
            <div className="space-y-2.5">
              {ticketKbSuggestions.map((k) => (
                <div key={k.id} className="text-xs border-b border-slate-800/60 pb-2.5 last:border-0">
                  <p className="text-slate-200 font-medium">{k.titulo}</p>
                  <p className="text-[11px] text-slate-500 mt-0.5">{k.categoria}</p>
                  <p className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                    {k.fragmento}
                  </p>
                </div>
              ))}
            </div>
          </GlassCard>
        )}
      </SidebarSection>

      <SidebarSection title="Evidencia e historial">
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
            <p className="text-slate-500 text-xs font-mono">
              Seleccioná un ticket para ver avances.
            </p>
          ) : !ticketTimeline.length ? (
            <p className="text-slate-500 text-xs font-mono">Sin eventos todavía.</p>
          ) : (
            <div className="space-y-3">
              {ticketTimeline.map((ev) => (
                <div key={ev.id} className="pl-3 border-l border-cyan-500/30">
                  <div className="flex justify-between gap-2">
                    <p className="text-xs text-slate-200 font-medium">{ev.titulo}</p>
                    {ev.nivel && <StatusBadge value={ev.nivel} />}
                  </div>
                  <p className="text-[11px] text-slate-500 font-mono mt-0.5">
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
            <p className="text-slate-500 text-xs font-mono">Sin novedades.</p>
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
                    <span className="text-[11px] font-mono text-slate-500">{n.leida}</span>
                  </div>
                  <p className="text-xs text-slate-400 mt-1 leading-relaxed">{n.mensaje}</p>
                </div>
              ))}
            </div>
          )}
        </GlassCard>

        <GlassCard title="Tickets" variant="secondary" className="min-h-[120px]">
          {!tickets.length ? (
            <p className="text-slate-500 text-xs">Sin tickets.</p>
          ) : (
            <div className="space-y-2">
              {tickets.slice(0, 10).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => selectTicket(t.id)}
                  className="w-full text-left p-2.5 rounded-lg bg-slate-900/60 border border-slate-800 hover:border-cyan-500/30 transition-colors"
                >
                  <div className="flex justify-between items-center gap-1">
                    <span className="font-mono text-cyan-300 text-[11px]">{t.id}</span>
                    <span className="flex gap-1 items-center">
                      {t.intelligence && t.intelligence.priority_score > 0 && (
                        <span className="text-[11px] font-mono text-amber-400">
                          {t.intelligence.priority_score}
                        </span>
                      )}
                      {t.nivel && <StatusBadge value={t.nivel} />}
                      <StatusBadge value={t.estado} />
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 truncate mt-0.5">
                    {t.linea}
                    {t.destino ? ` · ${t.destino}` : ""}
                  </p>
                  {t.organizacion && (
                    <p className="text-[11px] text-slate-600 truncate">{t.organizacion}</p>
                  )}
                </button>
              ))}
            </div>
          )}
        </GlassCard>
      </SidebarSection>
    </div>
  );
}
