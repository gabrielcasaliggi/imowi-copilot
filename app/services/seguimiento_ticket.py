"""Registro automático de pasos operativos en el timeline del ticket."""

from __future__ import annotations

from app.domain.flujos_operativos import PASO_LABELS
from app.estate import repository as repo
from app.services.intenciones_seguimiento import construir_resumen


# (paso_id, clave_hecho, valor_esperado). valor_esperado=None => cualquier valor nuevo distinto de ausente.
_AVANCES: tuple[tuple[str, str, object], ...] = (
    ("roaming_datos_moviles", "datos_moviles_activos", True),
    ("roaming_apn", "apn_configurado", True),
    ("roaming_jsc", "roaming_verificado", True),
    ("roaming_activar_jsc", "roaming_activado_jsc", True),
    ("roaming_reinicio", "reinicio_o_modo_avion", True),
    ("roaming_llamada_prueba", "llamadas_ok", None),
    ("datos_moviles", "datos_moviles_activos", True),
    ("datos_apn", "apn_configurado", True),
    ("datos_reinicio", "reinicio_o_modo_avion", True),
    ("datos_llamada_prueba", "llamadas_ok", None),
    ("datos_sim_descarte", "sim_cambiada", True),
    ("senal_llamadas", "llamadas_ok", None),
    ("senal_reinicio", "reinicio_o_modo_avion", True),
    ("sim_evaluar", "sim_cambiada", True),
)

_PASOS_RESUMEN_NOC = frozenset({
    "roaming_cerrar_seguimiento",
    "datos_cerrar_seguimiento",
    "senal_ticket_noc",
    "senal_cerrar_seguimiento",
})


def _zona_definida(hechos: dict) -> bool:
    return hechos.get("zona_unica") is not None or hechos.get("multiples_zonas") is not None


def _transicion(hechos_prev: dict, hechos_new: dict, clave: str, esperado: object) -> bool:
    prev_val = hechos_prev.get(clave)
    new_val = hechos_new.get(clave)
    if esperado is None:
        return prev_val is None and new_val is not None
    return prev_val != esperado and new_val == esperado


def _detectar_pasos_completados(hechos_prev: dict, hechos_new: dict) -> list[str]:
    completados: list[str] = []
    registrados = set(hechos_prev.get("pasos_ticket_registrados") or [])

    if _zona_definida(hechos_new) and not _zona_definida(hechos_prev):
        if "senal_zona" not in registrados:
            completados.append("senal_zona")

    for paso_id, clave, esperado in _AVANCES:
        if paso_id in registrados:
            continue
        if _transicion(hechos_prev, hechos_new, clave, esperado):
            completados.append(paso_id)

    if hechos_new.get("roaming_jsc_inactivo") and not hechos_prev.get("roaming_jsc_inactivo"):
        if "roaming_jsc" not in registrados and "roaming_jsc" not in completados:
            completados.append("roaming_jsc")

    return completados


def _detalle_paso(
    paso_id: str,
    hechos: dict,
    ultimo_operador: str,
    sintoma: str,
) -> str:
    partes: list[str] = []
    if ultimo_operador:
        partes.append(f"Operador: {ultimo_operador[:240]}")
    if sintoma:
        partes.append(f"Caso: {sintoma[:180]}")
    if hechos.get("roaming_jsc_inactivo"):
        partes.append("Hallazgo: roaming inactivo en JSC")
    if hechos.get("multiples_zonas"):
        partes.append("Alcance: varias zonas")
    elif hechos.get("zona_unica"):
        partes.append("Alcance: zona única")
    if hechos.get("llamadas_ok") is True:
        partes.append("Llamadas: OK")
    elif hechos.get("llamadas_ok") is False:
        partes.append("Llamadas: fallan")
    pasos = hechos.get("pasos_realizados") or []
    if pasos:
        partes.append("Acciones: " + "; ".join(pasos[-4:]))
    return " | ".join(partes)[:1800]


def registrar_avances_en_ticket(
    db,
    org_id: str,
    ticket_id: str,
    *,
    hechos_prev: dict,
    hechos_new: dict,
    datos_triaje: dict,
    ultimo_operador: str,
    actor: str,
    flujo_operativo: dict | None,
    ticket_nivel: str = "N1",
    ticket_estado: str = "Abierto",
) -> tuple[list[str], dict]:
    """Persiste eventos de pasos confirmados. Devuelve trazas y hechos actualizados."""
    hechos = dict(hechos_new)
    registrados = list(hechos.get("pasos_ticket_registrados") or [])
    registrados_set = set(registrados)
    traces: list[str] = []
    sintoma = datos_triaje.get("sintoma", "")

    for paso_id in _detectar_pasos_completados(hechos_prev, hechos):
        titulo = PASO_LABELS.get(paso_id, paso_id)
        detalle = _detalle_paso(paso_id, hechos, ultimo_operador, sintoma)
        repo.add_ticket_event(
            db,
            org_id,
            ticket_id,
            tipo="paso_operativo",
            titulo=titulo,
            detalle=detalle,
            nivel=ticket_nivel,
            estado=ticket_estado,
            actor=actor or "consola",
        )
        registrados.append(paso_id)
        registrados_set.add(paso_id)
        traces.append(f"📬 [Ticket]: Registrado paso {paso_id} en {ticket_id}")

    paso_actual = (flujo_operativo or {}).get("paso_id")
    if paso_actual in _PASOS_RESUMEN_NOC and paso_actual not in registrados_set:
        resumen = construir_resumen(hechos, datos_triaje, {"id": ticket_id, "estado": ticket_estado})
        repo.add_ticket_event(
            db,
            org_id,
            ticket_id,
            tipo="resumen_noc",
            titulo="Resumen operativo para NOC",
            detalle=resumen[:2000],
            nivel=ticket_nivel,
            estado=ticket_estado,
            actor=actor or "consola",
        )
        registrados.append(paso_actual)
        traces.append(f"📋 [Ticket]: Resumen NOC registrado en {ticket_id}")

        if paso_actual == "senal_ticket_noc":
            repo.update_ticket(
                db,
                org_id,
                ticket_id,
                estado="En Revisión",
                destino="imowi_noc",
                motivo_escalamiento="Señal/cobertura con pruebas N1 agotadas o afectación multisector",
            )
            repo.add_ticket_notification(
                db,
                org_id,
                ticket_id,
                destinatario="imowi_noc",
                titulo=f"Escalamiento NOC — {ticket_id}",
                mensaje=resumen[:500],
            )

    hechos["pasos_ticket_registrados"] = registrados
    return traces, hechos


def serializar_timeline(db, org_id: str, ticket_id: str) -> list[dict]:
    return [
        {
            "id": e.id,
            "ticket_id": e.ticket_id,
            "tipo": e.tipo,
            "titulo": e.titulo,
            "detalle": e.detalle,
            "nivel": e.nivel,
            "estado": e.estado,
            "actor": e.actor,
            "created_at": e.created_at.isoformat() if e.created_at else "",
        }
        for e in repo.list_ticket_events(db, org_id, ticket_id)
    ]
