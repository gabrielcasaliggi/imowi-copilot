from pydantic import BaseModel


class MensajeHistorial(BaseModel):
    rol: str
    contenido: str


class LoginInput(BaseModel):
    usuario: str
    password: str


class LoginResponse(BaseModel):
    token: str
    rol: str
    usuario: str
    cooperativa: str | None = None
    nombre: str
    org_slug: str = "imowi"
    must_change_password: bool = False


class ContextoTicket(BaseModel):
    cooperativa: str = ""
    linea: str = ""
    dispositivo: str = ""
    falla_tecnica: str = ""
    listo_para_jsc: bool = False
    tipo_caso: str = ""
    ticket_activo_id: str = ""
    usuario_confirmo_ok: bool = False
    modulo_inferido: str = ""
    kb_encontrado: bool = False
    modo_resolucion_kb: bool = False
    requiere_ticket_noc: bool = False


class ChatInput(BaseModel):
    modulo_contexto: str = ""  # legacy opcional; el LLM infiere si está vacío
    historial: list[MensajeHistorial] = []
    mensaje_usuario: str = ""
    contexto_ticket: ContextoTicket | None = None


class ChatResponse(BaseModel):
    respuesta: str
    modulo_inferido: str
    modulo_nombre: str
    tipo_caso_sugerido: str = ""
    kb_encontrado: bool = False
    modo_resolucion_kb: bool = False
    puntaje_kb: float = 0.0


class EstructurarInput(BaseModel):
    historial: list[MensajeHistorial]
    modulo_contexto: str = ""


class EstructurarResponse(BaseModel):
    cooperativa: str = ""
    modulo: str = ""
    modulo_id: str = ""
    linea: str = ""
    dispositivo: str = ""
    descripcion: str = ""
    falla_tecnica: str = ""
    tipo_caso: str = "escalamiento"
    usuario_confirmo_ok: bool = False
    listo_para_jsc: bool = False
    envio_automatico: bool = False
    kb_encontrado: bool = False
    modo_resolucion_kb: bool = False
    requiere_ticket_noc: bool = False


class GuardarTicketInput(BaseModel):
    modulo: str = ""
    modulo_id: str = ""
    linea: str = ""
    dispositivo: str = ""
    falla_exacta: str = ""
    descripcion: str = ""
    cooperativa: str = "Cooperativa Test"
    tipo_caso: str = "escalamiento"


class TicketUpdateInput(BaseModel):
    estado: str | None = None
    resolucion: str | None = None
    cooperativa: str | None = None
    linea: str | None = None
    dispositivo: str | None = None
    descripcion: str | None = None
    modulo: str | None = None
    modulo_id: str | None = None
    tipo_caso: str | None = None


class Ticket(BaseModel):
    id: str
    cooperativa: str
    modulo: str
    modulo_id: str
    linea: str
    dispositivo: str
    descripcion: str
    estado: str
    resolucion: str = ""
    fecha: str
    fecha_actualizacion: str = ""
    tipo_caso: str = "escalamiento"
    creado_por: str = ""
