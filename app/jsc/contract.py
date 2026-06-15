"""
Contrato de integración JSC — define la interfaz para reemplazar la demo por API real.

La implementación actual (`connector.py`) usa SQLite seed.
Para producción, implementar `JSCProviderHTTP` o `JSCProviderSync` contra el API del proveedor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class FichaLineaJSC:
    """Contrato normalizado de línea/abonado — independiente del backend."""

    msisdn: str
    jsc_ref: str = ""
    abonado: str = ""
    plan: str = ""
    estado_linea: str = "Activa"
    iccid: str = ""
    roaming_habilitado: str = "Sí"
    apn: str = ""
    estado_cuenta: str = "Al día"
    saldo_resumen: str = "$0"
    ultima_sync: datetime | None = None
    fuente: str = "JSC"
    contable: str = ""

    def to_dict(self) -> dict:
        return {
            "msisdn": self.msisdn,
            "jsc_ref": self.jsc_ref,
            "abonado": self.abonado,
            "plan": self.plan,
            "estado_linea": self.estado_linea,
            "iccid": self.iccid,
            "roaming_habilitado": self.roaming_habilitado,
            "apn": self.apn,
            "estado_cuenta": self.estado_cuenta,
            "saldo_resumen": self.saldo_resumen,
            "ultima_sync": self.ultima_sync.isoformat() if self.ultima_sync else None,
            "fuente": self.fuente,
            "contable": self.contable,
        }


@runtime_checkable
class JSCProvider(Protocol):
    """Interfaz que debe cumplir cualquier conector JSC (demo, HTTP, batch sync)."""

    def buscar_linea(
        self, org_id: str, msisdn: str, *, admin_global: bool = False
    ) -> FichaLineaJSC | None: ...

    def listar_lineas(
        self, org_id: str, *, limit: int = 50, admin_global: bool = False
    ) -> list[FichaLineaJSC]: ...

    def buscar(
        self, org_id: str, query: str, *, limit: int = 10, admin_global: bool = False
    ) -> list[FichaLineaJSC]: ...


# Campos mínimos requeridos para automatizar tickets con datos reales
CAMPOS_TICKET_JSC = (
    "msisdn",
    "abonado",
    "plan",
    "estado_linea",
    "iccid",
    "apn",
    "estado_cuenta",
)

# Endpoints sugeridos para integración HTTP (fase 2)
JSC_API_ENDPOINTS = {
    "linea_por_msisdn": "GET /lineas/{msisdn}",
    "listar_lineas": "GET /lineas?org={org_id}&limit={limit}",
    "buscar": "GET /lineas/search?q={query}",
    "sync_batch": "POST /sync/lineas",
    "crear_ticket": "POST /tickets",
    "escalar_ticket": "POST /tickets/{id}/escalar",
    "consultar_ticket": "GET /tickets/{id}",
}


@dataclass
class TicketJSCPayload:
    """Payload normalizado para alta/escalamiento en JSC externo."""

    msisdn: str
    descripcion: str
    nivel: str = "N1"
    cooperativa: str = ""
    cooperativa_id: str = ""
    tipo_incidencia: str = "General"
    operador: str = ""
    motivo_escalamiento: str = ""
    evidencia_n1: str = ""
    proveedor: str = ""
    ticket_local_id: str = ""
    destino: str = "cooperativa"

    def to_dict(self) -> dict:
        return {
            "msisdn": self.msisdn,
            "descripcion": self.descripcion,
            "nivel": self.nivel,
            "cooperativa": self.cooperativa,
            "cooperativa_id": self.cooperativa_id,
            "tipo_incidencia": self.tipo_incidencia,
            "operador": self.operador,
            "motivo_escalamiento": self.motivo_escalamiento,
            "evidencia_n1": self.evidencia_n1,
            "proveedor": self.proveedor,
            "ticket_local_id": self.ticket_local_id,
            "destino": self.destino,
        }


def mapear_ticket_a_jsc(ticket: dict, *, org_nombre: str = "", org_id: str = "") -> TicketJSCPayload:
    """Mapea un ticket del Data Estate al contrato JSC externo."""
    return TicketJSCPayload(
        msisdn=str(ticket.get("linea", "")),
        descripcion=str(ticket.get("descripcion_falla", "")),
        nivel=str(ticket.get("nivel", "N1")),
        cooperativa=org_nombre,
        cooperativa_id=org_id,
        tipo_incidencia=str(ticket.get("categoria", "General")),
        operador=str(ticket.get("creado_por", "")),
        motivo_escalamiento=str(ticket.get("motivo_escalamiento", "")),
        evidencia_n1=str(ticket.get("acciones_n1_realizadas", "")),
        proveedor=str(ticket.get("proveedor", "")),
        ticket_local_id=str(ticket.get("id", "")),
        destino=str(ticket.get("destino", "cooperativa")),
    )
