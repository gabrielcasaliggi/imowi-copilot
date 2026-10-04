"""Red de seguridad conversacional: escenarios multi-turno con la configuración de producción.

Producción = ``EKO_JOURNEYS_ENABLED=true`` + Action Runtime solo con ``create_ticket``. LLM caído (fallback
determinista), BillTrack y planta mockeados. Cada test corre en WhatsApp y portal.

Los escenarios que HOY fallan llevan ``xfail(strict=True)`` con el hallazgo y el síntoma. Cuando un arreglo
los haga pasar, el test avisa (XPASS estricto) y hay que retirar el marcador.
"""

from __future__ import annotations

import re

import pytest

from tests.e2e_conv import invariants as inv
from tests.e2e_conv.harness import converse

DERIVAR = re.compile(r"(derivar|derive|confirmame con un|ticket [a-z]+-\d+)", re.I)
ACUSE_RESUELTO = re.compile(r"(me alegra|solucion|resuelt|de nada|cualquier otra|escribime|que bueno)", re.I)


@pytest.fixture(params=["whatsapp", "portal"])
def canal(request):
    return request.param


def xf(reason: str):
    return pytest.mark.xfail(strict=True, reason=reason)


def sin_violaciones(turns, **kw):
    v = inv.violaciones(turns, **kw)
    assert not v, "\n".join(v) + "\n" + "\n".join(f"  [{t.branch}] {t.user!r} -> {t.reply[:100]!r}" for t in turns)


# =============================================================== los 14 escenarios definidos
def test_01_hola(canal):
    t = converse(["hola"], canal=canal)
    sin_violaciones(t)
    assert "identifiqué" in t[0].reply or "consulta" in t[0].reply.lower()


def test_02_no_tengo_internet_un_servicio_fijo(canal):
    t = converse(["no tengo internet"], canal=canal, profile="int1")
    sin_violaciones(t)
    assert inv.VOCAB_INTERNET.search(t[0].reply)


def test_03_no_tengo_internet_multi_cuenta(canal):
    t = converse(["no tengo internet", "lemuramatiBAI"], canal=canal, profile="multi")
    sin_violaciones(t, servicio=(0, inv.VOCAB_INTERNET, ("lemuramatiBAI",)))
    assert "3 cuentas" in t[0].reply
    assert "No veo una sesión" in t[1].reply or inv.VOCAB_INTERNET.search(t[1].reply)


def test_04_deuda(canal):
    t = converse(["tengo deuda?"], canal=canal, profile="deuda")
    sin_violaciones(t)
    assert re.search(r"15\.000|saldo", t[0].reply, re.I)


def test_05_movil_elegir_y_llamadas(canal):
    t = converse(["tengo problemas con mi línea de imowi", "1", "no puedo hacer llamadas"], canal=canal, profile="movil")
    sin_violaciones(t, servicio=(1, inv.VOCAB_MOVIL, ("Imowi 5 GB",)))
    assert "línea 2235550001" in t[0].reply and "línea 2235550003" in t[0].reply  # menú distinguible (C)


@xf("S6: tras un diagnóstico sin sesión, «ya funciona, muchas gracias» ofrece derivar a un agente en vez de cerrar")
def test_06_gracias_tras_resolver(canal):
    t = converse(["no tengo internet", "ya funciona, muchas gracias"], canal=canal)
    sin_violaciones(t)
    assert not DERIVAR.search(t[1].reply), t[1].reply


@xf("S7/H7: «ya se arregló» tras un diagnóstico no se reconoce como resuelto y ofrece derivar")
def test_07_ya_se_arreglo(canal):
    t = converse(["no tengo internet", "ya se arregló"], canal=canal)
    sin_violaciones(t)
    assert ACUSE_RESUELTO.search(t[1].reply) and not DERIVAR.search(t[1].reply), t[1].reply


def test_08_consulta_de_ticket_abierto(canal):
    t = converse(["cómo va mi ticket"], canal=canal, ticket_abierto=True)
    sin_violaciones(t)
    assert re.search(r"ticket .*abierto", t[0].reply, re.I)


@xf("S9: con journeys ON el corte masivo activo se ignora («No veo una sesión…»); el aviso de corte solo existe en el legacy")
def test_09_corte_activo(canal):
    t = converse(["no tengo internet"], canal=canal, corte_activo=True)
    sin_violaciones(t)
    assert re.search(r"(incidencia|corte|zona)", t[0].reply, re.I), t[0].reply


@xf("S10/H8: elegir Sensa/TV responde «Listo: seleccioné…» sin pregunta ni guía siguiente (callejón)")
def test_10_sensa_tv(canal):
    t = converse(["no me anda la tele sensa"], canal=canal, profile="sensa")
    sin_violaciones(t, servicio=(-1, inv.VOCAB_TV, ()))
    assert "?" in t[0].reply or "contame" in t[0].reply.lower(), t[0].reply


def test_11_pedir_agente_pide_confirmacion(canal):
    t = converse(["no tengo internet", "quiero hablar con un agente"], canal=canal)
    sin_violaciones(t)
    assert not t[1].ticket_created  # I6: confirma antes de crear el ticket


@xf("S12: «ahora revisame el de tupaciretaBAI» (cambio de servicio) vuelve a mostrar el menú en vez de cambiar de servicio")
def test_12_cambio_de_servicio_tras_diagnostico(canal):
    t = converse(
        ["no tengo internet", "lemuramatiBAI", "ahora revisame el de tupaciretaBAI"], canal=canal, profile="multi"
    )
    sin_violaciones(t)
    assert "¿Cuál servicio querés usar?" not in t[2].reply, t[2].reply


def _on_off_aviso(reason_off: str | None, reason_on: str | None):
    marks = lambda r: [xf(r)] if r else []  # noqa: E731
    return [
        pytest.param(True, marks=marks(reason_on), id="journeys_on"),
        pytest.param(False, marks=marks(reason_off), id="journeys_off"),
    ]


@pytest.mark.parametrize(
    "journeys",
    _on_off_aviso(
        "legacy: «no sigamos con el diagnóstico» tras el aviso de deuda cae en el saludo genérico",
        "S13: con journeys ON no hay aviso de deuda y «no sigamos con el diagnóstico» ofrece derivar a un agente",
    ),
)
def test_13_aviso_de_deuda_y_no_sigamos(canal, journeys):
    t = converse(["no tengo internet", "no sigamos con el diagnóstico"], canal=canal, profile="deuda", journeys=journeys)
    sin_violaciones(t)
    assert re.search(r"(pag|factura|saldo|deuda|oficina|de acuerdo|ok)", t[1].reply, re.I) and not DERIVAR.search(t[1].reply), t[1].reply


@pytest.mark.parametrize(
    "journeys",
    _on_off_aviso("legacy: «quiero pagar» tras el aviso de deuda cae en el saludo genérico", None),
)
def test_14a_respuesta_al_aviso_pagar(canal, journeys):
    t = converse(["no tengo internet", "quiero pagar"], canal=canal, profile="deuda", journeys=journeys)
    sin_violaciones(t)
    assert re.search(r"(oficina virtual|pagar|pago)", t[1].reply, re.I), t[1].reply


@pytest.mark.parametrize(
    "journeys",
    _on_off_aviso(None, "S14b: con journeys ON «seguí con el diagnóstico» ofrece derivar a un agente en vez de seguir"),
)
def test_14b_respuesta_al_aviso_seguir(canal, journeys):
    t = converse(["no tengo internet", "seguí con el diagnóstico"], canal=canal, profile="deuda", journeys=journeys)
    sin_violaciones(t)
    assert inv.VOCAB_INTERNET.search(t[1].reply) and not DERIVAR.search(t[1].reply), t[1].reply


# =============================================================== hallazgos abiertos (H5–H10)
@xf("H5: un login que contiene «id» (tupaciretacuidaBAI) se toma como service_id → «Ese servicio no pertenece a tu cuenta»")
def test_h5_login_con_id_en_multicuenta(canal):
    t = converse(
        ["no tengo internet", "lemuramatiBAI", "ahora revisame el de tupaciretacuidaBAI"], canal=canal, profile="multi"
    )
    sin_violaciones(t)
    assert "no pertenece" not in t[2].reply.lower(), t[2].reply


def test_h5b_login_con_id_solo_funciona(canal):
    t = converse(["no tengo internet", "tupaciretacuidaBAI"], canal=canal, profile="multi")
    sin_violaciones(t)
    assert "no pertenece" not in t[1].reply.lower()


@xf("H6: el «sí» a la confirmación de derivación repite la confirmación y nunca crea el ticket (journeys ON, solo create_ticket)")
def test_h6_diagnostico_agente_si(canal):
    t = converse(["no tengo internet", "quiero hablar con un agente", "sí"], canal=canal)
    sin_violaciones(t)
    assert t[2].ticket_created, t[2].reply


@xf("H7: «ya se arregló» tras un diagnóstico ofrece derivar en lugar de acusar la resolución")
def test_h7_ya_se_arreglo_tras_diagnostico(canal):
    t = converse(["no tengo internet", "ya se arregló", "gracias"], canal=canal)
    sin_violaciones(t)
    assert ACUSE_RESUELTO.search(t[1].reply) and not DERIVAR.search(t[1].reply), t[1].reply


@xf("H8: elegir Sensa/TV confirma la selección y no pregunta qué pasa con la TV")
def test_h8_elegir_sensa(canal):
    t = converse(["quiero ver el servicio de sensa tv"], canal=canal, profile="sensa")
    sin_violaciones(t)
    assert "?" in t[0].reply or "contame" in t[0].reply.lower(), t[0].reply


@xf("H9: abonado sin Internet fijo: «hola» repite el mensaje de «sin Internet fijo» (el journey queda abierto)")
def test_h9_sin_fijo_y_luego_hola(canal):
    t = converse(["no tengo internet", "hola"], canal=canal, profile="movil")
    sin_violaciones(t)


@xf("H10: el problema declarado antes de elegir servicio se pierde: tras elegir solo confirma, sin retomar el problema")
def test_h10_problema_declarado_antes_de_elegir(canal):
    t = converse(["tengo problemas con mi línea de imowi", "1"], canal=canal, profile="movil")
    sin_violaciones(t)
    assert "?" in t[1].reply or "contame" in t[1].reply.lower() or "problema" in t[1].reply.lower(), t[1].reply


# =============================================================== comparación con journeys OFF (línea base legacy)
def test_base_off_corte_activo_avisa(canal):
    t = converse(["no tengo internet"], canal=canal, journeys=False, corte_activo=True)
    sin_violaciones(t)
    assert re.search(r"(incidencia|zona)", t[0].reply, re.I)


def test_base_off_agente_si_crea_ticket(canal):
    t = converse(["no tengo internet", "quiero hablar con un agente", "sí"], canal=canal, journeys=False)
    sin_violaciones(t)
    assert t[2].ticket_created and not t[1].ticket_created


def test_base_off_gracias_cierra(canal):
    t = converse(["no tengo internet", "ya anda, gracias"], canal=canal, journeys=False)
    sin_violaciones(t)
    assert ACUSE_RESUELTO.search(t[1].reply)


def test_base_off_sensa_pregunta(canal):
    t = converse(["no me anda la tele sensa"], canal=canal, journeys=False, profile="sensa")
    sin_violaciones(t)
    assert "?" in t[0].reply
