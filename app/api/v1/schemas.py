from __future__ import annotations

from pydantic import BaseModel, Field


class TenantContext(BaseModel):
    organizacion_id: str
    organizacion_slug: str
    organizacion_nombre: str
    brand_color: str
    logo_label: str
    usuario_email: str
    usuario_nombre: str
    rol: str
    es_admin_imowi: bool = False
    cooperativa_legacy: str | None = None


class ChatMessage(BaseModel):
    rol: str
    contenido: str


class ChatV1Request(BaseModel):
    historial: list[ChatMessage] = []
    mensaje: str = ""
    forzar_escalamiento: bool = False
    session_id: str = ""
    accion_operador: str = ""


class ChatV1Response(BaseModel):
    respuesta: str
    relevante: bool = True
    prefilter_motivo: str = ""
    agent_traces: list[str] = []
    informe_tecnico: dict = Field(default_factory=dict)
    acciones_red: list[dict] = Field(default_factory=list)
    ticket: dict | None = None
    datos_triaje: dict = Field(default_factory=dict)
    ficha_jsc: dict | None = None
    clasificacion: dict | None = None
    estado_conversacion: str | None = None
    caso_conversacion: dict | None = None
    usar_ia: bool = False
    linea_cambiada: dict | None = None
    tickets_similares: list[dict] = Field(default_factory=list)
    ticket_existente: dict | None = None
    alertas_red: list[dict] = Field(default_factory=list)
    intencion_pendiente: str | None = None
    flujo_operativo: dict | None = None
    ticket_timeline: list[dict] = Field(default_factory=list)


class KBCreate(BaseModel):
    titulo: str
    categoria: str = "General"
    contenido: str


class TelemetrySimulate(BaseModel):
    elemento_red: str


class TicketUpdateV1(BaseModel):
    estado: str | None = None
    resolucion_tecnica: str | None = None
    descripcion_falla: str | None = None
    nivel: str | None = None
    destino: str | None = None
    proveedor: str | None = None
    motivo_escalamiento: str | None = None
    estado_sla: str | None = None
    ticket_externo_id: str | None = None


class TicketEventCreate(BaseModel):
    titulo: str = "Nota interna"
    detalle: str
    interno: bool = True


class TicketKbPublish(BaseModel):
    titulo: str | None = None
    categoria: str | None = None
    contenido: str | None = None


class OrganizationCreate(BaseModel):
    nombre: str
    slug: str | None = None
    logo_label: str = "C"
    brand_color: str = "#34d399"


class OrganizationUpdate(BaseModel):
    nombre: str | None = None
    logo_label: str | None = None
    brand_color: str | None = None


class UserCreate(BaseModel):
    email: str
    nombre: str
    password: str = "cliente"
    rol: str = "cliente"
    telefono: str = ""
    linea_principal: str = ""
