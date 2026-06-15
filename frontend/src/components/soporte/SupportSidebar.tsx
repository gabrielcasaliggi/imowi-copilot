"use client";

import { FormEvent, useState } from "react";
import { GlassCard, SlaBadge } from "@/components/ui/GlassCard";
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
      <GlassCard title="Caso activo" accent="cyan">
        <p className="text-slate-500 text-xs">Sin caso en curso. Iniciá un reclamo.</p>
      </GlassCard>
    );
  }
  return (
    <GlassCard title="Caso activo" accent="cyan">
      <div className="space-y-1 text-xs font-mono">
        {caso?.linea_msisdn && (
          <div className="flex justify-between">
            <span className="text-slate-500">Línea</span>
            <span className="text-cyan-300">{caso.linea_msisdn}</span>
          </div>
        )}
        {caso?.estado && (
          <div className="flex justify-between gap-2">
            <span className="text-slate-500">Estado</span>
            <span>{ESTADO_CASO_LABELS[caso.estado] || caso.estado}</span>
          </div>
        )}
        {caso?.id && (
          <div className="flex justify-between">
            <span className="text-slate-500">Caso</span>
            <span className="text-slate-400 truncate max-w-[140px]">{caso.id.slice(0, 8)}…</span>
          </div>
        )}
        {(caso?.ticket_id || ticketExistente?.id) && (
          <div className="flex justify-between">
            <span className="text-slate-500">Ticket</span>
            <span className="text-amber-300">{caso?.ticket_id || ticketExistente?.id}</span>
          </div>
        )}
        {caso?.paso_kb_idx !== undefined && caso.paso_kb_idx > 0 && (
          <p className="text-[10px] text-slate-500">Paso KB: {caso.paso_kb_idx}</p>
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
    <GlassCard title="Reclamos similares">
      <div className="space-y-2">
        {similares.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => onSelect(t.id)}
            className="w-full text-left p-2 rounded-lg border border-slate-800 bg-slate-900/60 hover:border-cyan-500/30"
          >
            <div className="flex justify-between gap-1">
              <span className="font-mono text-cyan-300 text-[10px]">{t.id}</span>
              <StatusBadge value={t.estado} />
            </div>
            <p className="text-[10px] text-slate-500 truncate">{t.categoria}</p>
            {t.resolucion_tecnica && (
              <p className="text-[10px] text-emerald-400/80 mt-1 line-clamp-2">
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
  const { fichaJsc } = useApp();
  if (!fichaJsc) {
    return (
      <GlassCard title="Ficha JSC" accent="cyan">
        <p className="text-slate-500 text-xs">Sin línea resuelta en JSC.</p>
      </GlassCard>
    );
  }
  return (
    <GlassCard title="Ficha JSC" accent="cyan">
      <div className="space-y-1.5 text-xs">
        <div className="flex justify-between">
          <span className="text-slate-500">MSISDN</span>
          <span className="text-cyan-300">{fichaJsc.msisdn}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">Abonado</span>
          <span>{fichaJsc.abonado}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-500">Plan</span>
          <span>{fichaJsc.plan}</span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">Línea</span>
          <StatusBadge value={fichaJsc.estado_linea} />
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">Cuenta</span>
          <StatusBadge value={fichaJsc.estado_cuenta} />
          <span className="text-slate-500">{fichaJsc.saldo_resumen}</span>
        </div>
        <p className="text-[10px] text-slate-600 pt-1">
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
          className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-[11px]"
        >
          <option value="N1">N1</option>
          <option value="N2">N2</option>
        </select>
        <select
          value={estado}
          onChange={(e) => setEstado(e.target.value)}
          className="bg-slate-950 border border-slate-700 rounded px-2 py-1 text-[11px]"
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
        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-[11px]"
      />
      <textarea
        value={resolucion}
        onChange={(e) => setResolucion(e.target.value)}
        placeholder="Agregar avance visible para la cooperativa..."
        className="w-full bg-slate-950 border border-slate-700 rounded px-2 py-1 text-[11px] min-h-[54px]"
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
        <pre className="text-[10px] text-slate-400 whitespace-pre-wrap bg-slate-950/80 p-2 rounded max-h-32 overflow-y-auto">
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
      <GlassCard title="Ticket en formación">
        <p className="text-slate-500 text-xs font-mono">Pendiente de escalamiento.</p>
      </GlassCard>
    );
  }

  const t = ticketFormacion;
  const intel = t.intelligence;

  return (
    <GlassCard title="Ticket en formación">
      <div className="space-y-1 text-xs font-mono">
        <div className="flex justify-between">
          <span className="text-slate-500">ID</span>
          <span className="text-cyan-300">{t.id}</span>
        </div>
        {intel && intel.priority_score > 0 && (
          <div className="p-2 rounded-lg border border-violet-500/20 bg-violet-500/5 space-y-1">
            <div className="flex justify-between">
              <span className="text-violet-300">Score IA</span>
              <span>
                {intel.priority_score}/100 · {intel.risk_level}
              </span>
            </div>
            <p className="text-[10px] text-slate-400">Causa: {intel.probable_cause}</p>
            <p className="text-[10px] text-cyan-400/90">→ {intel.next_best_action}</p>
            {(t.sla_label || intel.sla?.label) && (
              <div className="pt-1">
                <SlaBadge
                  label={t.sla_label || intel.sla?.label}
                  estado={t.estado_sla || intel.sla?.estado_sla}
                />
              </div>
            )}
            {intel.risk_reasons?.length ? (
              <p className="text-[9px] text-slate-600">{intel.risk_reasons.join(" · ")}</p>
            ) : null}
          </div>
        )}
        <div className="flex justify-between">
          <span className="text-slate-500">Línea</span>
          <span>{t.linea}</span>
        </div>
        <div className="flex flex-wrap gap-1">
          {t.nivel && <StatusBadge value={t.nivel} />}
          {t.destino && (
            <span className="px-2 py-0.5 text-[10px] font-mono uppercase rounded border bg-slate-600/30 text-slate-300 border-slate-500/30">
              {t.destino}
            </span>
          )}
          <StatusBadge value={t.origen} />
          <StatusBadge value={t.estado} />
        </div>
        {t.proveedor && (
          <p className="text-amber-300 text-[10px]">→ {t.proveedor}</p>
        )}
        {t.motivo_escalamiento && (
          <p className="text-slate-400 text-[10px]">{t.motivo_escalamiento}</p>
        )}
        {isAdmin ? (
          <TicketAdminForm
            key={t.id}
            ticket={t}
            onUpdate={updateTicket}
            onExplain={explainEscalation}
          />
        ) : (
          <p className="text-[10px] text-slate-500 pt-2 mt-2 border-t border-slate-800">
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
    <div className="flex flex-col min-h-0 gap-3 overflow-y-auto">
      <CasoActivoCard caso={casoActivo} ticketExistente={ticketExistente} />
      <EstadoOperativoPanel />
      <FlujoOperativoPanel flujo={flujoOperativo} />
      <FichaJscCard />
      <TicketFormacionCard />

      {ticketKbSuggestions.length > 0 && (
        <GlassCard title="KB sugerida">
          <div className="space-y-2">
            {ticketKbSuggestions.map((k) => (
              <div key={k.id} className="text-xs border-b border-slate-800/60 pb-2 last:border-0">
                <p className="text-slate-200">{k.titulo}</p>
                <p className="text-[10px] text-slate-500">{k.categoria}</p>
                <p className="text-[10px] text-slate-400 mt-1 line-clamp-2">{k.fragmento}</p>
              </div>
            ))}
          </div>
        </GlassCard>
      )}

      {ticketLearning?.postmortem && (
        <GlassCard title="Aprendizaje operativo" accent="emerald">
          <pre className="text-[10px] text-slate-400 whitespace-pre-wrap">{ticketLearning.postmortem}</pre>
        </GlassCard>
      )}

      <ReclamosSimilares similares={ticketsSimilares} onSelect={selectTicket} />

      <GlassCard title="Historial del ticket">
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
                  <p className="text-xs text-slate-200">{ev.titulo}</p>
                  {ev.nivel && <StatusBadge value={ev.nivel} />}
                </div>
                <p className="text-[10px] text-slate-500 font-mono">
                  {ev.estado}
                  {ev.actor ? ` · ${ev.actor}` : ""}
                </p>
                {ev.detalle && (
                  <p className="text-[11px] text-slate-400 mt-1">{ev.detalle}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      <GlassCard title="Notificaciones" accent="amber">
        {!notifications.length ? (
          <p className="text-slate-500 text-xs font-mono">Sin novedades.</p>
        ) : (
          <div className="space-y-2">
            {notifications.slice(0, 5).map((n) => (
              <div
                key={n.id}
                className={`p-2 rounded-lg border ${
                  n.leida === "No"
                    ? "border-amber-500/30 bg-amber-500/10"
                    : "border-slate-800 bg-slate-900/50"
                }`}
              >
                <div className="flex justify-between gap-2">
                  <p className="text-xs text-slate-200">{n.titulo}</p>
                  <span className="text-[9px] font-mono text-slate-500">{n.leida}</span>
                </div>
                <p className="text-[11px] text-slate-400 mt-1">{n.mensaje}</p>
              </div>
            ))}
          </div>
        )}
      </GlassCard>

      <GlassCard title="Tickets" className="flex-1 min-h-[120px]">
        {!tickets.length ? (
          <p className="text-slate-500 text-xs">Sin tickets.</p>
        ) : (
          <div className="space-y-2">
            {tickets.slice(0, 10).map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => selectTicket(t.id)}
                className="w-full text-left p-2 rounded-lg bg-slate-900/60 border border-slate-800 hover:border-cyan-500/30"
              >
                <div className="flex justify-between items-center gap-1">
                  <span className="font-mono text-cyan-300 text-[10px]">{t.id}</span>
                  <span className="flex gap-1 items-center">
                    {t.intelligence && t.intelligence.priority_score > 0 && (
                      <span className="text-[9px] font-mono text-amber-400">
                        {t.intelligence.priority_score}
                      </span>
                    )}
                    {t.nivel && <StatusBadge value={t.nivel} />}
                    <StatusBadge value={t.estado} />
                  </span>
                </div>
                <p className="text-[10px] text-slate-500 truncate">
                  {t.linea}
                  {t.destino ? ` · ${t.destino}` : ""}
                </p>
                {t.organizacion && (
                  <p className="text-[9px] text-slate-600 truncate">{t.organizacion}</p>
                )}
              </button>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  );
}
