"""Taxonomía de incidentes, destinos y reglas de clasificación N1/N2/Proveedor."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class NivelTicket(str, Enum):
    N1 = "N1"
    N2 = "N2"
    PROVEEDOR = "Proveedor"


class DestinoTicket(str, Enum):
    COOPERATIVA = "cooperativa"
    IMOWI_NOC = "imowi_noc"
    CARRIER = "carrier"
    SIM_PROVIDER = "sim_provider"
    PLATAFORMA = "plataforma"


class AccionClasificacion(str, Enum):
    RESOLVER_N1 = "resolver_n1"
    CREAR_TICKET_N1 = "crear_ticket_n1"
    CREAR_TICKET_N2 = "crear_ticket_n2"
    DERIVAR_PROVEEDOR = "derivar_proveedor"
    PEDIR_DATOS = "pedir_datos"


@dataclass
class CategoriaIncidente:
    id: str
    nombre: str
    keywords: tuple[str, ...]
    destino_default: DestinoTicket
    nivel_default: NivelTicket
    proveedor_tipo: str = ""


CATEGORIAS: list[CategoriaIncidente] = [
    CategoriaIncidente("red", "Red / Core", ("anomalia", "cobertura", "sin señal", "sin servicio masivo", "lte", "5g", "volte"), DestinoTicket.IMOWI_NOC, NivelTicket.N2),
    CategoriaIncidente("roaming", "Roaming", ("roaming", "brasil", "extranjero", "visita"), DestinoTicket.IMOWI_NOC, NivelTicket.N2),
    CategoriaIncidente("apn", "APN / Datos", ("apn", "datos", "internet", "navegacion", "navegación", "pdp"), DestinoTicket.IMOWI_NOC, NivelTicket.N2),
    CategoriaIncidente("esim", "eSIM", ("esim", "e-sim", "perfil", "qr", "ota", "eid"), DestinoTicket.SIM_PROVIDER, NivelTicket.PROVEEDOR, "fabricante_sim"),
    CategoriaIncidente("sim", "SIM física", ("sim", "chip", "iccid", "tarjeta sim"), DestinoTicket.SIM_PROVIDER, NivelTicket.PROVEEDOR, "fabricante_sim"),
    CategoriaIncidente("sms", "SMS / A2P", ("sms", "mensaje", "a2p", "imessage", "apple"), DestinoTicket.CARRIER, NivelTicket.PROVEEDOR, "carrier"),
    CategoriaIncidente("llamadas", "Voz", ("llamada", "llamadas", "voz", "no puede llamar"), DestinoTicket.CARRIER, NivelTicket.PROVEEDOR, "carrier"),
    CategoriaIncidente("billing", "Facturación / Cuenta", ("deuda", "suspendida", "suspension", "suspensión", "factura", "saldo", "cuenta"), DestinoTicket.COOPERATIVA, NivelTicket.N1),
    CategoriaIncidente("provision", "Provisión", ("alta", "baja", "portabilidad", "activacion", "activación"), DestinoTicket.PLATAFORMA, NivelTicket.N2),
]

PROVEEDORES: dict[str, str] = {
    "carrier": "Carrier principal (MNO)",
    "fabricante_sim": "Fabricante SIM / eSIM",
    "plataforma": "Plataforma OSS/BSS",
    "imowi_noc": "NOC imowi",
    "cooperativa": "Cooperativa / revendedor",
}

CARRIER_KEYWORDS = ("movistar", "personal", "claro", "tuenti", "carrier", "mno", "red movil", "red móvil")


@dataclass
class ReglaClasificacion:
    id: str
    descripcion: str
    prioridad: int = 100


REGLAS: list[ReglaClasificacion] = [
    ReglaClasificacion("datos_minimos", "Faltan datos mínimos (línea o síntoma)", 10),
    ReglaClasificacion("cuenta_suspendida", "Línea suspendida o con deuda — resolver en N1", 20),
    ReglaClasificacion("anomalia_red", "Anomalía de red regional — ticket N2", 30),
    ReglaClasificacion("kb_resolucion", "KB con procedimiento N1 pendiente", 40),
    ReglaClasificacion("escalamiento_explicito", "Operador solicitó escalamiento", 50),
    ReglaClasificacion("categoria_proveedor", "Categoría técnica derivable a proveedor desde N2", 60),
    ReglaClasificacion("triaje_completo_n2", "Triaje completo sin resolución KB — N2", 70),
    ReglaClasificacion("ticket_n1_demo", "Caso completo no resuelto que permanece en N1", 80),
    ReglaClasificacion("default_n1", "Caso aislado — continuar resolución N1", 90),
]


@dataclass
class ResultadoClasificacion:
    accion: AccionClasificacion
    nivel: NivelTicket | None = None
    destino: DestinoTicket | None = None
    proveedor: str = ""
    categoria: str = "General"
    motivo_escalamiento: str = ""
    regla_aplicada: str = ""
    confianza: float = 1.0
    datos_faltantes: list[str] = field(default_factory=list)
    pasos_n1: list[str] = field(default_factory=list)
    evidencia: list[str] = field(default_factory=list)


def inferir_categoria(texto: str, categoria_diag: str = "General") -> CategoriaIncidente | None:
    t = (texto or "").lower()
    if categoria_diag and categoria_diag != "General":
        for cat in CATEGORIAS:
            if cat.nombre.lower() == categoria_diag.lower() or cat.id == categoria_diag.lower():
                return cat
    mejor: CategoriaIncidente | None = None
    mejor_score = 0
    for cat in CATEGORIAS:
        score = sum(1 for kw in cat.keywords if kw in t)
        if score > mejor_score:
            mejor_score = score
            mejor = cat
    return mejor
