"""H27g (pieza 1): la confirmación del Action Runtime nombra la acción, en voseo y terminando en «?» (I7).

Solo copy: el «sí» (``confirmation_received``) sigue ejecutando la acción y el «no» (``confirmation_rejected``) la cancela.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.eko_action_runtime import (
    ActionRequest,
    TrustedContext,
    execute_action,
    get_action,
    list_registered_actions,
)

VIEJO = "¿Confirmás que querés continuar con esta acción?"
TEXTOS = {
    "create_ticket": "¿Querés que te derive con un agente?",
    "escalate_human": "¿Querés que te pase con un agente?",
    "close_conversation": "¿Querés que cierre esta consulta?",
}


def _trusted(**kw) -> TrustedContext:
    base = dict(
        conversation_id="conv-1",
        organization_id="org-1",
        abonado_id="abo-1",
        abonado=SimpleNamespace(id="abo-1", organizacion_id="org-1", nombre="María", dni="30111222", servicio="internet",
                                plan="100Mb", estado="activo", deuda_monto="0", linea_msisdn="", client_number="200"),
        conv=SimpleNamespace(id="conv-1", ticket_id="", estado="bot", telefono="223", canal="whatsapp", servicio_detectado=""),
        ctx={},
        db=MagicMock(),
        canal="whatsapp",
        decision_name="test",
    )
    base.update(kw)
    return TrustedContext(**base)


def _run(action: str, **kw):
    with (
        patch("app.services.canal_abonado._crear_ticket_n2", return_value="IBOT-1"),
        patch("app.services.handoff_notify.notify_espera_agente", return_value=0),
    ):
        return execute_action(ActionRequest(action=action, parameters={"motivo": "sin internet"}), _trusted(**kw))


def test_toda_accion_con_confirmacion_tiene_texto_propio():
    con_confirmacion = sorted(a for a in list_registered_actions() if get_action(a).confirmation_required)
    assert con_confirmacion == sorted(TEXTOS), con_confirmacion


@pytest.mark.parametrize("action", sorted(TEXTOS))
def test_confirmacion_nombra_la_accion(action):
    r = _run(action)
    assert r.status == "needs_confirmation", r
    assert r.user_message == TEXTOS[action] and r.user_message.endswith("?"), r.user_message


@pytest.mark.parametrize("action", sorted(TEXTOS))
def test_el_si_ejecuta_la_accion(action):
    r = _run(action, confirmation_received=True)
    assert r.status == "success", r


@pytest.mark.parametrize("action", sorted(TEXTOS))
def test_el_no_cancela_la_accion(action):
    r = _run(action, confirmation_rejected=True)
    assert r.status == "denied" and r.reason_code == "confirmation_rejected", r


def test_generico_sin_texto_propio():
    from app.services.eko_action_runtime import mensaje_confirmacion

    assert mensaje_confirmacion("accion_sin_texto") == "¿Querés que lo haga?"
    assert all(mensaje_confirmacion(a) != VIEJO for a in list_registered_actions())
