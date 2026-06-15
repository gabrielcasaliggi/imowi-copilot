"use client";

import { useApp } from "@/contexts/AppContext";
import { ESTADO_CASO_LABELS } from "@/lib/types";

export function NetworkAlertBanner() {
  const { networkAlert, alertasRed } = useApp();
  if (!networkAlert && !alertasRed.length) return null;

  return (
    <div className="mx-4 mt-3 px-4 py-3 rounded-xl border border-amber-500/40 bg-amber-500/10 text-amber-200 text-sm space-y-1">
      <p className="font-medium text-amber-300 text-xs font-mono uppercase tracking-wider">
        Alerta de red
      </p>
      {networkAlert && <p>{networkAlert}</p>}
      {alertasRed.length > 0 && (
        <ul className="text-xs space-y-1">
          {alertasRed.map((a) => (
            <li key={a.elemento_red}>
              {a.elemento_red}: {a.metrica}={a.valor_actual} ({a.estado_actual})
              {a.correlacionada ? " · correlacionada" : " · general"}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function LineaCambiadaBanner() {
  const { lineaCambiada, confirmarNuevoReclamoLinea, sending } = useApp();
  if (!lineaCambiada) return null;

  return (
    <div className="mx-4 mt-3 px-4 py-3 rounded-xl border border-violet-500/40 bg-violet-500/10 text-violet-200 text-sm">
      <p className="font-medium text-violet-300 text-xs font-mono uppercase tracking-wider mb-1">
        Otra línea detectada
      </p>
      <p className="mb-2">
        El caso activo es la línea {lineaCambiada.anterior}. Para atender la línea{" "}
        {lineaCambiada.nueva} sin mezclar historias, iniciá un nuevo reclamo.
      </p>
      <button
        type="button"
        onClick={() => confirmarNuevoReclamoLinea()}
        disabled={sending}
        className="text-xs font-mono px-3 py-1.5 rounded-lg border border-violet-400/50 text-violet-200 hover:bg-violet-500/10"
      >
        Nuevo reclamo para {lineaCambiada.nueva}
      </button>
    </div>
  );
}

export function EstadoCasoBadge() {
  const { estadoConversacion, lineaDetectada, casoActivo, isAdmin } = useApp();
  if (isAdmin) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 mt-1">
      {estadoConversacion && (
        <span className="inline-flex items-center px-2 py-0.5 text-[10px] font-mono uppercase rounded border bg-cyan-500/10 text-cyan-300 border-cyan-500/30">
          {ESTADO_CASO_LABELS[estadoConversacion] || estadoConversacion}
        </span>
      )}
      {(lineaDetectada || casoActivo?.linea_msisdn) && (
        <span className="text-[10px] font-mono text-slate-500">
          Línea:{" "}
          <span className="text-cyan-300">{lineaDetectada || casoActivo?.linea_msisdn}</span>
        </span>
      )}
      {casoActivo?.ticket_id && (
        <span className="text-[10px] font-mono text-slate-500">
          Ticket: <span className="text-amber-300">{casoActivo.ticket_id}</span>
        </span>
      )}
    </div>
  );
}
