"""Modelo de comprensión contextual del canal abonado (EKO)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PreguntaPendienteAbonado(str, Enum):
    """Qué esperaba el bot en su último mensaje."""

    NINGUNA = ""
    AVISO_DEUDA = "aviso_deuda"
    MENU_SERVICIO = "menu_servicio"
    MENU_TIPO_ACCESO = "menu_tipo_acceso"
    WIFI_INTERFERENCIAS = "wifi_interferencias"
    WIFI_MEJORA = "wifi_mejora"
    CONFIRMAR_PASO = "confirmar_paso"
    CONFIRMAR_SI_NO = "confirmar_si_no"


@dataclass
class ComprensionTurnoAbonado:
    """Lectura estructurada de un turno — no decide tickets ni playbooks."""

    texto_original: str = ""
    texto_para_reglas: str = ""
    pregunta_pendiente: PreguntaPendienteAbonado = PreguntaPendienteAbonado.NINGUNA
    confianza: float = 0.0
    fuente: str = "lexico"
    hechos_nuevos: dict[str, Any] = field(default_factory=dict)
    eleccion_aviso_deuda: str | None = None  # "pago" | "tecnico"
    evidencia: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "texto_original": self.texto_original,
            "texto_para_reglas": self.texto_para_reglas,
            "pregunta_pendiente": self.pregunta_pendiente.value,
            "confianza": self.confianza,
            "fuente": self.fuente,
            "hechos_nuevos": dict(self.hechos_nuevos),
            "eleccion_aviso_deuda": self.eleccion_aviso_deuda,
            "evidencia": list(self.evidencia),
        }
