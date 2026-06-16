"""Motor de decisión operativa basado en invariantes — sin depender de frases literales."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.escalamiento import detectar_escalamiento
from app.domain.turn_understanding import IntencionTurno, TurnUnderstanding


@dataclass
class DecisionOperativa:
    accion: str
    crear_ticket: bool = False
    nivel: str = "N1"
    destino: str = "cooperativa"
    proveedor: str = ""
    categoria: str = ""
    regla_aplicada: str = ""
    motivo_escalamiento: str = ""
    auto_confirmado: bool = False
    cerrar: bool = False

    def a_dict(self) -> dict[str, Any]:
        return {
            "accion": self.accion,
            "crear_ticket": self.crear_ticket,
            "nivel": self.nivel,
            "destino": self.destino,
            "proveedor": self.proveedor,
            "categoria": self.categoria,
            "regla_aplicada": self.regla_aplicada,
            "motivo_escalamiento": self.motivo_escalamiento,
        }


def _cat(hechos: dict, flujo: dict) -> str:
    return hechos.get("categoria_flujo") or flujo.get("categoria", "")


def _paso_final_n1(cat: str) -> set[str]:
    base = {
        "roaming_cerrar_seguimiento",
        "datos_cerrar_seguimiento",
        "senal_ticket_noc",
        "senal_cerrar_seguimiento",
    }
    if cat == "sms":
        base.add("sms_ticket_carrier")
    return base


def _historial_indica_persistencia(historial: list[dict], hechos: dict) -> bool:
    if hechos.get("persistencia_confirmada"):
        return True
    if detectar_escalamiento(historial):
        return True
    return hechos.get("resuelto") is False and bool(hechos.get("pasos_realizados"))


def decidir_desde_intencion(
    understanding: TurnUnderstanding,
    *,
    ticket_id: str = "",
) -> DecisionOperativa | None:
    """Mapea intención estructurada a acción conversacional (sin crear ticket aún)."""
    i = understanding.intencion
    if i == IntencionTurno.ESTADO_TICKET:
        return DecisionOperativa(accion="estado_ticket", regla_aplicada="intencion_estado_ticket")
    if i == IntencionTurno.NOVEDAD_TICKET:
        return DecisionOperativa(accion="novedad_ticket", regla_aplicada="intencion_novedad")
    if i == IntencionTurno.RESUMEN_CASO:
        return DecisionOperativa(accion="resumen_caso", regla_aplicada="intencion_resumen")
    if i in (IntencionTurno.CERRAR_TICKET, IntencionTurno.CASO_RESUELTO):
        return DecisionOperativa(accion="cerrar_ticket", cerrar=True, regla_aplicada="intencion_cierre")
    if i == IntencionTurno.CORRECCION:
        return DecisionOperativa(accion="correccion", regla_aplicada="intencion_correccion")
    if i == IntencionTurno.AGRADECIMIENTO:
        return DecisionOperativa(accion="agradecimiento", regla_aplicada="intencion_agradecimiento")
    if i == IntencionTurno.PREGUNTA_RECOMENDACION:
        return DecisionOperativa(accion="recomendar_paso", regla_aplicada="intencion_recomendacion")
    if i in (
        IntencionTurno.PERSISTENCIA,
        IntencionTurno.CONFIRMAR_PERSISTENCIA,
        IntencionTurno.CONFIRMAR_PASO,
        IntencionTurno.INFORME_PRUEBA,
        IntencionTurno.INFORME_ALCANCE,
        IntencionTurno.APORTAR_DATO,
    ):
        accion = "seguimiento_activo" if ticket_id else "resolver_n1"
        return DecisionOperativa(accion=accion, regla_aplicada=f"intencion_{i.value}")
    if i == IntencionTurno.SOLICITAR_TICKET:
        accion = "seguimiento_activo" if ticket_id else "resolver_n1"
        return DecisionOperativa(accion=accion, regla_aplicada="intencion_solicitar_ticket")
    if i == IntencionTurno.SEGUIMIENTO_ACTIVO and ticket_id:
        return DecisionOperativa(accion="seguimiento_activo", regla_aplicada="intencion_seguimiento")
    return None


def evaluar_crear_ticket(
    *,
    historial: list[dict],
    hechos: dict,
    flujo_operativo: dict | None,
    understanding: TurnUnderstanding,
    ticket: dict | None = None,
    ticket_existente: dict | None = None,
) -> DecisionOperativa | None:
    """Invariantes para escalamiento — independientes de la redacción exacta."""
    if ticket or ticket_existente:
        return None

    flujo = flujo_operativo or {}
    cat = _cat(hechos, flujo)
    paso_id = flujo.get("paso_id", "")
    h = understanding.hechos

    persistencia = (
        h.persistencia_confirmada
        or hechos.get("persistencia_confirmada")
        or understanding.intencion == IntencionTurno.CONFIRMAR_PERSISTENCIA
    )
    solicita = (
        h.solicita_ticket
        or hechos.get("solicita_ticket")
        or understanding.intencion == IntencionTurno.SOLICITAR_TICKET
    )
    playbook_agotado = paso_id in _paso_final_n1(cat) or flujo.get("completado")
    jsc_ok = hechos.get("linea_jsc_verificada") or h.linea_jsc_verificada
    resuelto = hechos.get("resuelto") is True

    if resuelto and not persistencia:
        return None

    # Invariante SMS: verificaciones N1 hechas + persistencia confirmada/solicitada → carrier
    if cat == "sms" and not resuelto:
        datos_sms = bool(
            hechos.get("sms_remitente_ejemplo")
            or hechos.get("sms_horario_incidente")
            or h.sms_remitente_ejemplo
            or h.sms_horario_incidente
        )
        alcance_ok = hechos.get("alcance_confirmado") or hechos.get("categoria_flujo") == "sms"
        listo_escalar = playbook_agotado or jsc_ok or solicita or (persistencia and alcance_ok)
        if paso_id == "sms_ticket_carrier" and (persistencia or solicita or datos_sms):
            return DecisionOperativa(
                accion="crear_ticket_n2",
                crear_ticket=True,
                nivel="N2",
                destino="carrier",
                proveedor="Carrier principal (MNO)",
                categoria="SMS / A2P",
                regla_aplicada="invariante_sms_datos_escalamiento",
                motivo_escalamiento=(
                    "SMS/A2P en paso de escalamiento carrier; contexto operativo listo para ticket."
                ),
                auto_confirmado=persistencia or solicita or datos_sms,
            )
        if persistencia and listo_escalar:
            return DecisionOperativa(
                accion="crear_ticket_n2",
                crear_ticket=True,
                nivel="N2",
                destino="carrier",
                proveedor="Carrier principal (MNO)",
                categoria="SMS / A2P",
                regla_aplicada="invariante_sms_persistencia",
                motivo_escalamiento=(
                    "SMS/A2P persiste tras verificaciones N1; escalar a carrier con contexto operativo."
                ),
                auto_confirmado=persistencia or solicita,
            )

    if not _historial_indica_persistencia(historial, hechos) and not persistencia:
        return None

    if playbook_agotado or (persistencia and solicita):
        destino = "imowi_noc"
        proveedor = "imowi NOC"
        categoria = flujo.get("categoria_label", "General")
        if cat == "sms":
            destino = "carrier"
            proveedor = "Carrier principal (MNO)"
            categoria = "SMS / A2P"
        return DecisionOperativa(
            accion="crear_ticket_n2",
            crear_ticket=True,
            nivel="N2",
            destino=destino,
            proveedor=proveedor,
            categoria=categoria,
            regla_aplicada="invariante_persistencia_post_n1",
            motivo_escalamiento=(
                "El inconveniente persiste después de las verificaciones N1; requiere escalamiento."
            ),
            auto_confirmado=persistencia or solicita,
        )

    pasos = hechos.get("pasos_realizados") or []
    if len(pasos) >= 4 and hechos.get("resuelto") is False:
        return DecisionOperativa(
            accion="crear_ticket_n2",
            crear_ticket=True,
            nivel="N2",
            destino="imowi_noc",
            proveedor="imowi NOC",
            categoria=flujo.get("categoria_label", "General"),
            regla_aplicada="invariante_pasos_n1_agotados",
            motivo_escalamiento="Persistencia tras múltiples verificaciones N1.",
            auto_confirmado=False,
        )

    return None
