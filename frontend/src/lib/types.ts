export interface LoginResponse {
  token: string;
  rol: string;
  usuario: string;
  cooperativa?: string;
  nombre: string;
  org_slug?: string;
}

export interface MeResponse {
  usuario: string;
  rol: string;
  cooperativa?: string;
  nombre: string;
  org_slug?: string;
}

export interface Organization {
  slug: string;
  nombre: string;
  brand_color: string;
  logo_label: string;
  es_plataforma?: boolean;
  usuarios?: number;
  tickets?: number;
  lineas?: number;
  tickets_abiertos?: number;
}

export interface AdminUser {
  id: string;
  email: string;
  nombre: string;
  rol: string;
  telefono: string;
  linea_principal: string;
}

export interface ImportCsvResult {
  status: string;
  slug: string;
  creados: number;
  actualizados: number;
  lineas_creadas: number;
  omitidos: number;
  errores: string[];
  filas: { email: string; nombre: string; rol: string; linea_principal: string }[];
}

export interface TenantContext {
  organizacion_id: string;
  organizacion_slug: string;
  organizacion_nombre: string;
  brand_color: string;
  logo_label: string;
  usuario_email: string;
  usuario_nombre: string;
  rol: string;
  es_admin_imowi: boolean;
  cooperativa_legacy?: string | null;
}

export interface ChatMessage {
  rol: "usuario" | "asistente";
  contenido: string;
}

export interface FichaJsc {
  msisdn: string;
  abonado: string;
  plan: string;
  estado_linea: string;
  estado_cuenta: string;
  saldo_resumen: string;
  apn: string;
  roaming_habilitado: string;
  fuente?: string;
}

export interface TicketIntelligence {
  priority_score: number;
  risk_level: string;
  risk_reasons: string[];
  probable_cause: string;
  next_best_action: string;
  horas_abierto: number;
  recurrence_count: number;
  organizacion?: string;
}

export interface Ticket {
  id: string;
  organizacion?: string;
  organizacion_id?: string;
  linea: string;
  dispositivo: string;
  descripcion_falla: string;
  origen: string;
  estado: string;
  resolucion_tecnica?: string;
  categoria: string;
  intent_ejecutado?: string;
  creado_por?: string;
  nivel?: string;
  destino?: string;
  proveedor?: string;
  motivo_escalamiento?: string;
  evidencia?: string;
  regla_clasificacion?: string;
  estado_sla?: string;
  ticket_externo_id?: string;
  created_at?: string;
  updated_at?: string;
  intelligence?: TicketIntelligence;
}

export interface KBSuggestion {
  id: string;
  titulo: string;
  categoria: string;
  fragmento: string;
}

export interface TicketLearning {
  kb_sugerencias: KBSuggestion[];
  similares_resueltos: TicketSimilar[];
  postmortem?: string | null;
}

export interface ExecutiveAnalytics {
  tenant: string;
  resumen_ejecutivo: string;
  ranking_riesgo: {
    label: string;
    org_id: string;
    backlog: number;
    n2: number;
    score_riesgo: number;
    score_max: number;
    tickets_criticos: number;
  }[];
  evolucion_semanal: StatsDistribution[];
  ahorro_operativo: {
    casos_n1_resueltos: number;
    escalaciones_evitadas_estimadas: number;
    horas_ahorradas_estimadas: number;
    porcentaje_n2: number;
  };
  alertas: { tipo: string; mensaje: string; severidad: string }[];
}

export interface TicketEvent {
  id: string;
  ticket_id: string;
  tipo: string;
  titulo: string;
  detalle: string;
  nivel: string;
  estado: string;
  actor: string;
  visible_cliente: string;
  created_at: string;
}

export interface TicketNotification {
  id: string;
  ticket_id: string;
  destinatario: string;
  canal: string;
  titulo: string;
  mensaje: string;
  leida: string;
  created_at: string;
}

export interface CasoConversacion {
  id: string;
  session_id: string;
  linea_msisdn: string;
  estado: string;
  intencion_pendiente?: string;
  datos_triaje: Record<string, unknown>;
  ticket_id?: string;
  paso_kb_idx: number;
  kb_agotada: boolean;
  updated_at?: string;
}

export interface LineaCambiada {
  anterior: string;
  nueva: string;
  caso_id?: string;
}

export interface TicketSimilar {
  id: string;
  linea: string;
  estado: string;
  categoria: string;
  nivel?: string;
  descripcion_falla?: string;
  created_at?: string;
  resolucion_tecnica?: string;
  cerrado?: boolean;
}

export interface AlertaRed {
  elemento_red: string;
  metrica: string;
  valor_actual: string;
  estado_actual: string;
  correlacionada: boolean;
}

export interface ChatV1Response {
  respuesta: string;
  relevante: boolean;
  prefilter_motivo?: string;
  agent_traces: string[];
  informe_tecnico: Record<string, unknown>;
  acciones_red: Record<string, unknown>[];
  ticket: Ticket | null;
  datos_triaje: Record<string, unknown>;
  ficha_jsc: FichaJsc | null;
  clasificacion: Record<string, unknown> | null;
  estado_conversacion: string | null;
  caso_conversacion: CasoConversacion | null;
  usar_ia: boolean;
  linea_cambiada?: LineaCambiada | null;
  tickets_similares?: TicketSimilar[];
  ticket_existente?: TicketSimilar | null;
  alertas_red?: AlertaRed[];
  intencion_pendiente?: string | null;
  flujo_operativo?: FlujoOperativo | null;
  ticket_timeline?: TicketEvent[];
}

export interface FlujoOperativo {
  categoria: string;
  categoria_label?: string;
  paso_id: string | null;
  paso_label?: string | null;
  paso_mensaje: string | null;
  completado: boolean;
  hechos_resumen: string[];
}

export interface TelemetryElement {
  id: string;
  elemento_red: string;
  metrica: string;
  valor_actual: string;
  estado_actual: string;
  ultima_actualizacion: string;
}

export interface KBArticle {
  id: string;
  titulo: string;
  categoria: string;
  contenido: string;
  created_at?: string;
}

export interface StatsDistribution {
  label: string;
  count: number;
}

export interface StatsResponse {
  tenant: string;
  desde: string;
  hasta: string;
  resumen: {
    total: number;
    abiertos: number;
    cerrados: number;
    n1: number;
    n2: number;
    promedio_horas: number;
    tasa_cierre?: number;
    porcentaje_n2?: number;
  };
  series: {
    diaria: StatsDistribution[];
    mensual: StatsDistribution[];
  };
  distribuciones: {
    categoria: StatsDistribution[];
    estado: StatsDistribution[];
    nivel: StatsDistribution[];
    origen: StatsDistribution[];
    destino: StatsDistribution[];
    proveedor: StatsDistribution[];
    cooperativa?: StatsDistribution[];
    lineas_recurrentes: StatsDistribution[];
  };
  promedios: {
    por_categoria: { label: string; count: number; avg_hours: number }[];
    por_cooperativa?: {
      label: string;
      count: number;
      abiertos: number;
      n2: number;
      tasa_cierre: number;
      promedio_horas: number;
    }[];
  };
  backlog: {
    id: string;
    linea: string;
    nivel: string;
    estado: string;
    categoria: string;
    horas_abierto: number;
    priority_score?: number;
    risk_level?: string;
    next_best_action?: string;
  }[];
}

export interface DemoTurnoGuion {
  orden: number;
  operador: string;
  esperado: string;
  verificar: string[];
  accion?: string;
}

export interface DemoEscenario {
  id: string;
  titulo: string;
  descripcion: string;
  linea: string;
  dispositivo: string;
  cooperativa: string;
  categoria_flujo: string;
  mensaje_inicial: string;
  turnos_guion: DemoTurnoGuion[];
  checklist_imowi: string[];
}

export interface DemoEscenariosResponse {
  tenant: string;
  escenarios: DemoEscenario[];
  checklist_general: string[];
}

export interface PilotMetricas {
  total_eventos: number;
  por_tipo: Record<string, number>;
  por_escenario: Record<string, { iniciados: number; pasos: number; tickets: number }>;
  sesiones_recientes: {
    session_id: string;
    escenario_id: string;
    pasos: number;
    ticket_id: string;
    inicio: string;
    ultimo_evento: string;
  }[];
  ultimos_eventos: {
    id: string;
    tipo: string;
    escenario_id: string;
    paso_id: string;
    ticket_id: string;
    created_at: string;
  }[];
}

export const ESTADO_CASO_LABELS: Record<string, string> = {
  nuevo_reclamo: "Nuevo reclamo",
  recolectando_datos: "Recolectando datos",
  buscando_kb: "Buscando en KB",
  guiando_resolucion: "Guía N1",
  esperando_confirmacion: "Esperando confirmación",
  ticket_creado: "Ticket registrado",
  cerrado_resuelto: "Cerrado resuelto",
};
