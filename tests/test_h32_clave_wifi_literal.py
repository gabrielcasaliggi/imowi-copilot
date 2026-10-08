"""H32 — la clave Wi‑Fi llega a BCM exactamente como la escribió el abonado.

La capa de comprensión normaliza el texto del turno (junta espacios, reemplazos léxicos) antes del flujo Wi‑Fi; en la
fase ``pedir_clave`` ese texto normalizado no puede ser la clave. Turnos reales de ``procesar_mensaje_entrante``
(journeys ON, Action Runtime con ``create_ticket``, LLM caído), destino BCM y write mockeados. Claves inventadas.
"""

from __future__ import annotations

import contextlib
import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.radius.contract import ServicioConectividad
from app.services import canal_abonado as c
from app.services import wifi_bcm as wb

_FIBRA = ServicioConectividad(
    login="lemuramatiBAI", service_type_code="INTFO", service_type_label="ACCESO INTERNET FIBRA OPTICA",
    product="Internet acceso Fo Hogar 100MB", locality="", service_on=True,
)


def _down(*_a, **_k):
    raise HTTPException(status_code=503, detail="LLM no disponible")


def _cambiar_clave(clave: str, *, pedido: str = "quiero cambiar la clave del wifi") -> tuple[list[str], list[str]]:
    """Pedido → clave → «sí». Devuelve (valores que llegaron a BCM, fase Wi‑Fi tras cada turno)."""
    wb.clear_wifi_ephemeral_for_tests()
    uid = uuid.uuid4().int
    tel = f"549223{uid % 10_000_000:07d}"
    dni = f"9{(uid >> 20) % 10_000_000:07d}"
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        abo = Abonado(organizacion_id=org.id, dni=dni, nombre="María Pérez", servicio="internet",
                      deuda_monto="0", client_number=str(uid % 10_000_000), plan="Fibra 100")
        db.add(abo)
        db.commit()
        conv = crepo.get_or_create_conversacion(db, org.id, telefono=tel, canal="whatsapp", wa_id=tel)
        conv.estado, conv.abonado_id = "bot", abo.id
        crepo.set_contexto(conv, {"identificado": True, "dni": dni})
        db.commit()
        org_id, conv_id = org.id, conv.id

    bcm: list[str] = []
    fases: list[str] = []

    def _aplicar(_db, _dest, password):
        bcm.append(password)
        return "ok", "", []

    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(app_config, "EKO_JOURNEYS_ENABLED", True))
        stack.enter_context(patch.object(app_config, "EKO_JOURNEYS_CHANNELS", frozenset()))
        stack.enter_context(patch.object(app_config, "EKO_JOURNEYS_ORG_IDS", frozenset()))
        stack.enter_context(patch.object(bridge, "ACTION_RUNTIME_ENABLED", True))
        stack.enter_context(patch.object(bridge, "ACTION_RUNTIME_ACTIONS", frozenset({"create_ticket"})))
        stack.enter_context(patch("app.llm.chat_completion", _down))
        stack.enter_context(patch("app.services.billtrack.lookup_servicios_conectividad", lambda **k: [_FIBRA]))
        stack.enter_context(patch("app.services.billtrack.lookup_servicios_conectividad_por_dni", lambda **k: [_FIBRA]))
        stack.enter_context(patch("app.services.billtrack.lookup_servicios_cuenta_por_dni", lambda **k: ([], True)))
        stack.enter_context(patch("app.services.handoff_notify.notify_espera_agente", lambda *a, **k: 0))
        stack.enter_context(patch.object(
            wb, "_destino_autorizado", lambda *_a, **_k: (wb.DestinoWifiBcm("serial", "SNTEST0001"), "", "")
        ))
        stack.enter_context(patch.object(wb, "_servicios_abonado", lambda *_a, **_k: []))
        stack.enter_context(patch.object(wb, "_aplicar_password", _aplicar))
        stack.enter_context(patch.object(c, "_enviar_respuesta", lambda *a, **k: None))
        for texto in (pedido, clave, "sí"):
            with Session() as db:
                c.procesar_mensaje_entrante(db, org_id, telefono=tel, texto=texto, canal="whatsapp", wa_id=tel)
                fases.append(crepo.get_contexto(db.get(ConversacionCanal, conv_id)).get("wifi_bcm_fase"))
    return bcm, fases


_FLUJO_OK = ["pedir_clave", "confirmar_clave", "hecho"]

# Hoy llegan alterados a BCM (normalización léxica antes del turno Wi‑Fi).
_ALTERADAS = [
    "Mi  Casa  2024",  # caracterización H31: espacios internos repetidos
    "casa wi fi 2024",  # caracterización H31: «wi fi» → «wifi»
    "mi table 2024",  # caracterización H31: «table» → «tablet»
    "Perro  Gato  99",  # espacios dobles en el medio
    "mi wi fi segura 1",  # «wi fi»
]

# Llegan iguales hoy: control.
_CONTROL = ["ClaveSegura99", "P@ss#W0rd$2024", "ñandú€2024ÁÉ", "mi casa 2024"]


@pytest.mark.xfail(strict=True, reason="H32: la clave llega a BCM normalizada por el léxico")
@pytest.mark.parametrize("clave", _ALTERADAS)
def test_clave_literal_llega_a_bcm(clave):
    bcm, fases = _cambiar_clave(clave)
    assert fases == _FLUJO_OK
    assert bcm == [clave]


@pytest.mark.xfail(strict=True, reason="H32: la clave llega a BCM normalizada por el léxico curado")
def test_clave_literal_con_reemplazo_del_lexico_curado(monkeypatch):
    # Hoy el JSON curado no trae reemplazos regex; se inyecta uno para cubrir esa fuente de normalización.
    import app.services.comprension_lexico as lex

    monkeypatch.setattr(lex, "cargar_lexico_curado", lambda: {"reemplazos_regex": [{"patron": r"\bkasa\b", "reemplazo": "casa"}]})
    assert lex.aplicar_reemplazos_lexico("Kasa Perez 2024") == "casa Perez 2024"
    bcm, fases = _cambiar_clave("Kasa Perez 2024")
    assert fases == _FLUJO_OK
    assert bcm == ["Kasa Perez 2024"]


@pytest.mark.parametrize("clave", _CONTROL)
def test_control_clave_sin_normalizacion_llega_igual(clave):
    bcm, fases = _cambiar_clave(clave)
    assert fases == _FLUJO_OK
    assert bcm == [clave]


def test_control_bordes_se_recortan():
    """Intencional: el validador excluye los espacios de inicio y fin de la clave."""
    bcm, _ = _cambiar_clave("  Clave1234  ")
    assert bcm == ["Clave1234"]


def test_control_pedido_sigue_normalizado():
    """Fuera de la clave, la normalización sigue: «wi fi» en el pedido se entiende como «wifi»."""
    bcm, fases = _cambiar_clave("ClaveSegura99", pedido="quiero cambiar la clave del wi fi")
    assert fases == _FLUJO_OK
    assert bcm == ["ClaveSegura99"]
