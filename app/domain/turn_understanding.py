"""Modelo estructurado de comprensión de un turno conversacional."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PreguntaPendiente(str, Enum):
    """Qué esperaba el bot en su último mensaje."""

    NINGUNA = ""
    CONFIRMAR_PERSISTENCIA = "confirmar_persistencia"
    CONFIRMAR_TICKET = "confirmar_ticket"
    CONFIRMAR_PASO = "confirmar_paso"
    CONFIRMAR_RESOLUCION = "confirmar_resolucion"
    ESTADO_TICKET = "estado_ticket"
    APORTAR_DATOS_ESCALAMIENTO = "aportar_datos_escalamiento"
    INFORMAR_PRUEBA = "informar_prueba"
    INFORMAR_ALCANCE = "informar_alcance"


class IntencionTurno(str, Enum):
    CONTINUAR = "continuar"
    ESTADO_TICKET = "estado_ticket"
    SOLICITAR_TICKET = "solicitar_ticket"
    CONFIRMAR_PERSISTENCIA = "confirmar_persistencia"
    CONFIRMAR_PASO = "confirmar_paso"
    PERSISTENCIA = "persistencia"
    CASO_RESUELTO = "caso_resuelto"
    CORRECCION = "correccion"
    AGRADECIMIENTO = "agradecimiento"
    RESUMEN_CASO = "resumen_caso"
    NOVEDAD_TICKET = "novedad_ticket"
    CERRAR_TICKET = "cerrar_ticket"
    PREGUNTA_RECOMENDACION = "pregunta_recomendacion"
    INFORME_PRUEBA = "informe_prueba"
    INFORME_ALCANCE = "informe_alcance"
    APORTAR_DATO = "aportar_dato"
    SEGUIMIENTO_ACTIVO = "seguimiento_activo"


@dataclass
class HechosTurno:
    """Hechos inferidos del turno actual (no del historial completo)."""

    persistencia_confirmada: bool | None = None
    solicita_ticket: bool | None = None
    resuelto: bool | None = None
    confirmacion_paso: bool | None = None
    linea_jsc_verificada: bool | None = None
    reinicio_o_modo_avion: bool | None = None
    llamadas_ok: bool | None = None
    datos_ok: bool | None = None
    apn_configurado: bool | None = None
    alcance_confirmado: bool | None = None
    sms_remitente_ejemplo: str | None = None
    sms_horario_incidente: str | None = None

    def a_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class TurnUnderstanding:
    """Comprensión estructurada de un turno — separada de la decisión operativa."""

    intencion: IntencionTurno = IntencionTurno.CONTINUAR
    confianza: float = 0.4
    fuente: str = "reglas"
    pregunta_pendiente: PreguntaPendiente = PreguntaPendiente.NINGUNA
    hechos: HechosTurno = field(default_factory=HechosTurno)
    evidencia: list[str] = field(default_factory=list)
    mensaje_operador: str = ""

    def to_intencion_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.intencion.value,
            "confianza": self.confianza,
            "fuente": self.fuente,
            "pregunta_pendiente": self.pregunta_pendiente.value,
            "evidencia": self.evidencia,
        }
