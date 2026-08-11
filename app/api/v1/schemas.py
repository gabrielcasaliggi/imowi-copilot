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
    permisos: list[str] = Field(default_factory=list)

    def puede(self, codigo: str) -> bool:
        return codigo in self.permisos


class ChatMessage(BaseModel):
    rol: str = Field(..., max_length=32)
    contenido: str = Field(..., max_length=4000)


class ChatV1Request(BaseModel):
    historial: list[ChatMessage] = []
    mensaje: str = Field(default="", max_length=4000)
    forzar_escalamiento: bool = False
    session_id: str = Field(default="", max_length=120)
    accion_operador: str = Field(default="", max_length=64)

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
    asignado_a: str | None = None


class TicketBulkClose(BaseModel):
    """Cierre masivo para limpieza operativa (no genera KB/CSAT)."""

    resolucion_tecnica: str = (
        "Cierre masivo previo a pruebas en producción / validación piloto."
    )
    dry_run: bool = False
    confirmar: bool = False


class TicketReassign(BaseModel):
    asignado_a: str
    nota: str = ""


class TicketEventCreate(BaseModel):
    titulo: str = "Nota interna"
    detalle: str
    interno: bool = True


class TicketKbPublish(BaseModel):
    titulo: str | None = None
    categoria: str | None = None
    contenido: str | None = None


class KBContributionCreate(BaseModel):
    titulo: str
    categoria: str = "General"
    contenido: str
    ticket_id: str = ""
    origen: str = "agente"


class KBContributionReview(BaseModel):
    titulo: str | None = None
    categoria: str | None = None
    contenido: str | None = None
    motivo_revision: str = ""


class OrganizationCreate(BaseModel):
    nombre: str
    slug: str | None = None
    logo_label: str = "C"
    brand_color: str = "#2298A6"


class OrganizationUpdate(BaseModel):
    nombre: str | None = None
    logo_label: str | None = None
    brand_color: str | None = None


class UserCreate(BaseModel):
    email: str
    nombre: str
    password: str = ""  # vacío → se genera temporal
    rol: str = "agente"
    telefono: str = ""
    linea_principal: str = ""


class UserUpdate(BaseModel):
    nombre: str | None = None
    rol: str | None = None
    telefono: str | None = None
    linea_principal: str | None = None
    activo: bool | None = None
    password: str | None = None


class AvailabilityUpdate(BaseModel):
    disponibilidad: str
