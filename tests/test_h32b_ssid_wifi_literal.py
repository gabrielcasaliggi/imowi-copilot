"""H32b — el nombre de red (SSID) llega a BCM exactamente como lo escribió el abonado.

Mismo patrón que H32 (``tests/test_h32_clave_wifi_literal.py``): en la fase ``pedir_ssid`` el texto normalizado por la
capa de comprensión no puede ser el SSID. Turnos reales de ``procesar_mensaje_entrante``; destino y write BCM mockeados.
"""

from __future__ import annotations

import contextlib
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

import app.config as app_config
import app.services.eko_action_bridge as bridge
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.services import canal_abonado as c
from app.services import wifi_bcm as wb
from tests.test_h32_clave_wifi_literal import _FIBRA, _down


def _turnos(script: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Corre ``script``; devuelve (valores que llegaron a BCM por tipo, fase Wi‑Fi tras cada turno)."""
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

    bcm: dict[str, list[str]] = {"clave": [], "ssid": []}
    fases: list[str] = []

    def _aplicar(tipo):
        def _f(_db, _dest, valor):
            bcm[tipo].append(valor)
            return "ok", "", []

        return _f

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
        stack.enter_context(patch.object(wb, "_aplicar_password", _aplicar("clave")))
        stack.enter_context(patch.object(wb, "_aplicar_ssid", _aplicar("ssid")))
        stack.enter_context(patch.object(c, "_enviar_respuesta", lambda *a, **k: None))
        for texto in script:
            with Session() as db:
                c.procesar_mensaje_entrante(db, org_id, telefono=tel, texto=texto, canal="whatsapp", wa_id=tel)
                fases.append(crepo.get_contexto(db.get(ConversacionCanal, conv_id)).get("wifi_bcm_fase"))
    return bcm, fases


def _cambiar_ssid(ssid: str) -> tuple[list[str], list[str]]:
    bcm, fases = _turnos(["quiero cambiar el nombre de la red", ssid, "sí"])
    return bcm["ssid"], fases


_FLUJO_OK = ["pedir_ssid", "confirmar_ssid", "hecho"]

# Antes de H32b llegaban alterados a BCM (normalización léxica antes del turno Wi‑Fi).
_ALTERADOS = [
    "Red  De  Maria",  # espacios internos repetidos
    "Casa Wi Fi",  # «wi fi» → «wifi»
    "La table de Ana",  # «table» → «tablet»
]

# Llegaban iguales antes de H32b: control.
_CONTROL = ["RedMaria5G", "Casa_Perez-2.4", "Ñandú Hogar", "mi red 2024"]


@pytest.mark.xfail(strict=True, reason="H32b: el SSID llega a BCM normalizado por el léxico")
@pytest.mark.parametrize("ssid", _ALTERADOS)
def test_ssid_literal_llega_a_bcm(ssid):
    bcm, fases = _cambiar_ssid(ssid)
    assert fases == _FLUJO_OK
    assert bcm == [ssid]


@pytest.mark.xfail(strict=True, reason="H32b: el SSID llega a BCM normalizado por el léxico curado")
def test_ssid_literal_con_reemplazo_del_lexico_curado(monkeypatch):
    # El JSON curado no trae reemplazos regex; se inyecta uno para cubrir esa fuente de normalización.
    import app.services.comprension_lexico as lex

    monkeypatch.setattr(lex, "cargar_lexico_curado", lambda: {"reemplazos_regex": [{"patron": r"\bkasa\b", "reemplazo": "casa"}]})
    bcm, fases = _cambiar_ssid("Kasa Perez")
    assert fases == _FLUJO_OK
    assert bcm == ["Kasa Perez"]


@pytest.mark.xfail(strict=True, reason="H32b: en el flujo «ambos» el SSID llega a BCM normalizado")
def test_ambos_clave_y_ssid_literales():
    bcm, fases = _turnos(["quiero cambiar clave y nombre del wifi", "Mi  Clave  99", "sí", "Casa Wi Fi", "sí"])
    assert fases == ["pedir_clave", "confirmar_clave", "pedir_ssid", "confirmar_ssid", "hecho"]
    assert bcm == {"clave": ["Mi  Clave  99"], "ssid": ["Casa Wi Fi"]}


@pytest.mark.parametrize("ssid", _CONTROL)
def test_control_ssid_sin_normalizacion_llega_igual(ssid):
    bcm, fases = _cambiar_ssid(ssid)
    assert fases == _FLUJO_OK
    assert bcm == [ssid]


def test_control_ssid_bordes_se_recortan():
    """Como con la clave: los espacios de inicio y fin no forman parte del SSID."""
    bcm, _ = _cambiar_ssid("  RedMaria  ")
    assert bcm == ["RedMaria"]
