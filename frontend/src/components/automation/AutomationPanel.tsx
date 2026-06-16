"use client";

import {
  CapabilityCard,
  GlassCard,
  SectionHeader,
  SidebarSection,
  StatusPill,
} from "@/components/ui/GlassCard";

const JSC_ACTIONS = [
  "Consultar estado de línea y abonado",
  "Verificar roaming internacional y datos roaming",
  "Activar roaming en JSC (con aprobación)",
  "Forzar re-registro de red / reset PDP",
  "Sincronizar catálogo de líneas del tenant",
] as const;

const AUTO_RULES = [
  {
    trigger: "Roaming inactivo detectado en JSC",
    condition: "Síntoma = sin datos en exterior",
    action: "Sugerir activación + reinicio equipo",
    approval: "Operador confirma",
  },
  {
    trigger: "Llamadas fallan en varias zonas",
    condition: "Flujo señal completado sin resolución",
    action: "Abrir ticket NOC automático",
    approval: "Requiere aprobación NOC",
  },
  {
    trigger: "Alerta de red correlacionada",
    condition: "Múltiples líneas misma celda",
    action: "Escalar a proveedor + notificar cooperativa",
    approval: "Automático con umbral",
  },
] as const;

const CONNECTORS = [
  { name: "JSC / BSS", status: "Demo", tone: "demo" as const, desc: "Lectura de línea y acciones de red" },
  { name: "CRM cooperativa", status: "Próximamente", tone: "soon" as const, desc: "Sincronizar abonado y casos" },
  { name: "WhatsApp / Email", status: "Próximamente", tone: "soon" as const, desc: "Notificaciones al cliente" },
  { name: "Monitor de red", status: "Disponible", tone: "available" as const, desc: "Correlación con telemetría" },
  { name: "Webhooks", status: "Requiere credenciales", tone: "credentials" as const, desc: "Eventos hacia sistemas externos" },
] as const;

export function AutomationPanel() {
  return (
    <div className="p-4 space-y-6 overflow-y-auto min-h-0">
      <SectionHeader
        title="Centro de Automatización"
        subtitle="Integraciones y acciones automáticas · vista preparatoria (no ejecuta cambios reales hoy)"
      />

      <div className="demo-banner rounded-xl px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-violet-200">Modo demo / roadmap</p>
          <p className="text-[11px] text-slate-400 mt-0.5 max-w-2xl leading-relaxed">
            Esta sección muestra capacidades futuras de automatización. Ninguna acción se ejecuta
            contra JSC, CRM o red en esta versión.
          </p>
        </div>
        <StatusPill label="Solo visualización" tone="demo" />
      </div>

      <SidebarSection title="Integración JSC">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <CapabilityCard
            title="JSC Connector"
            description="Punto de integración con el catálogo operativo y acciones de red. Hoy opera en lectura desde consola; aquí se visualizan acciones automatizables."
            status="Demo"
            statusTone="demo"
            items={[...JSC_ACTIONS]}
            footer={
              <p className="text-[11px] text-slate-500">
                Próximo paso: credenciales por tenant + políticas de aprobación antes de ejecutar.
              </p>
            }
          />
          <CapabilityCard
            title="Acciones automáticas sugeridas"
            description="Playbooks que el motor podrá ejecutar cuando la integración esté habilitada."
            status="Próximamente"
            statusTone="soon"
            items={[
              "Reset PDP / forzar registro en red visitada",
              "Verificar y activar roaming internacional",
              "Abrir ticket NOC con evidencia del caso",
              "Actualizar estado y notificar cooperativa",
              "Registrar paso en auditoría operativa",
            ]}
          />
        </div>
      </SidebarSection>

      <SidebarSection title="Reglas de automatización">
        <div className="space-y-3">
          {AUTO_RULES.map((rule) => (
            <GlassCard key={rule.trigger} variant="secondary">
              <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                <h3 className="text-sm font-medium text-slate-100">{rule.trigger}</h3>
                <StatusPill label={rule.approval} tone="neutral" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
                <div>
                  <p className="text-slate-500 uppercase tracking-wide font-mono mb-0.5">Disparador</p>
                  <p className="text-slate-300">{rule.trigger}</p>
                </div>
                <div>
                  <p className="text-slate-500 uppercase tracking-wide font-mono mb-0.5">Condición</p>
                  <p className="text-slate-300">{rule.condition}</p>
                </div>
                <div>
                  <p className="text-slate-500 uppercase tracking-wide font-mono mb-0.5">Acción</p>
                  <p className="text-cyan-300/90">{rule.action}</p>
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      </SidebarSection>

      <SidebarSection title="Conectores e integraciones">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {CONNECTORS.map((c) => (
            <CapabilityCard
              key={c.name}
              title={c.name}
              description={c.desc}
              status={c.status}
              statusTone={c.tone}
            />
          ))}
        </div>
      </SidebarSection>

      <GlassCard title="Hoja de ruta" variant="technical">
        <ol className="space-y-2 text-xs text-slate-400 list-decimal list-inside">
          <li>Conectar credenciales JSC por cooperativa (solo lectura)</li>
          <li>Habilitar acciones con doble confirmación del operador</li>
          <li>Reglas de automatización configurables desde Admin Hub</li>
          <li>Webhooks y notificaciones hacia CRM / canales externos</li>
          <li>Auditoría completa de cada acción automática ejecutada</li>
        </ol>
      </GlassCard>
    </div>
  );
}
