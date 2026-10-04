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
HANDOFF_OK = re.compile(r"(te derivo|ticket [a-z]+-\d+|derivado|derivé)", re.I)
ACUSE_RESUELTO = re.compile(r"(me alegra|solucion|resuelt|de nada|cualquier otra|escribime|que bueno)", re.I)


@pytest.fixture(params=["whatsapp", "portal"])
def canal(request):
    return request.param


DEBT_NOTICE = re.compile(r"(saldo pendiente|figura un saldo|tenés una deuda|deuda pendiente)", re.I)
BLOQUEA = re.compile(r"(primero a pagar|o seguimos con el diagn)", re.I)
PAGO = re.compile(r"(oficina virtual|https?://|ov\.batan)", re.I)
BASE_MOVIL = ["tengo problemas con mi línea de imowi", "1", "no puedo hacer llamadas"]
PREGUNTA_LLAMADAS = re.compile(r"(llamar|llamada|te entran|se cortan)", re.I)


def avisos(turns) -> int:
    return sum(1 for t in turns if DEBT_NOTICE.search(t.reply))




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


def test_11_pedir_agente_deriva_directo(canal):
    """R1 + ADR regla 5: el pedido explícito de agente ES la confirmación; deriva directo."""
    t = converse(["no tengo internet", "quiero hablar con un agente"], canal=canal)
    sin_violaciones(t)
    assert t[1].ticket_created and HANDOFF_OK.search(t[1].reply), t[1].reply


def test_12_cambio_de_servicio_tras_diagnostico(canal):
    """RC-11: nombrar el login (no INT*) cambia de servicio sin volver a mostrar el menú."""
    t = converse(
        ["no tengo internet", "lemuramatiBAI", "ahora revisame el de tupaciretaBAI"], canal=canal, profile="multi"
    )
    sin_violaciones(t)
    assert "¿Cuál servicio querés usar?" not in t[2].reply, t[2].reply
    assert "tupaciretaBAI" in t[2].reply, t[2].reply


JOURNEYS_R2 = [
    pytest.param(
        True,
        marks=xf("R2/journeys: con journeys ON no hay aviso de saldo (el journey de conectividad responde «No veo una sesión…» antes de la rama de deuda)"),
        id="journeys_on",
    ),
    pytest.param(
        False,
        marks=xf("R2/legacy: el aviso de saldo bloquea («¿Querés que te ayude primero a pagar…?») y las respuestas al aviso caen al saludo genérico"),
        id="journeys_off",
    ),
]


# Viejos 13/14 (Internet con saldo pendiente) bajo R2: el aviso es informativo, una vez por conversación, no bloquea.
def _aviso_internet_ok(t):
    r = t[0].reply
    assert avisos(t) == 1 and DEBT_NOTICE.search(r), r
    assert inv.VOCAB_INTERNET.search(r) and "?" in r and not BLOQUEA.search(r), r


@pytest.mark.parametrize("journeys", JOURNEYS_R2)
def test_13_aviso_de_deuda_y_no_sigamos(canal, journeys):
    t = converse(["no tengo internet", "no sigamos con el diagnóstico"], canal=canal, profile="deuda", journeys=journeys)
    sin_violaciones(t)
    _aviso_internet_ok(t)
    assert PAGO.search(t[1].reply) or inv.VOCAB_INTERNET.search(t[1].reply), t[1].reply
    assert avisos(t) == 1


@pytest.mark.parametrize("journeys", JOURNEYS_R2)
def test_14a_respuesta_al_aviso_pagar(canal, journeys):
    t = converse(["no tengo internet", "quiero pagar"], canal=canal, profile="deuda", journeys=journeys)
    sin_violaciones(t)
    _aviso_internet_ok(t)
    assert PAGO.search(t[1].reply), t[1].reply
    assert avisos(t) == 1


@pytest.mark.parametrize("journeys", JOURNEYS_R2)
def test_14b_respuesta_al_aviso_seguir(canal, journeys):
    t = converse(["no tengo internet", "seguí con el diagnóstico"], canal=canal, profile="deuda", journeys=journeys)
    sin_violaciones(t)
    _aviso_internet_ok(t)
    assert inv.VOCAB_INTERNET.search(t[1].reply) and not DERIVAR.search(t[1].reply), t[1].reply
    assert avisos(t) == 1


# =============================================================== hallazgos abiertos (H5–H10)
def test_h5_login_con_id_en_multicuenta(canal):
    """H5/RC-10: un login con «id» adentro no se toma como service_id (la resolución por texto es RC-11)."""
    t = converse(
        ["no tengo internet", "lemuramatiBAI", "ahora revisame el de tupaciretacuidaBAI"], canal=canal, profile="multi"
    )
    sin_violaciones(t)
    assert "no pertenece" not in t[2].reply.lower(), t[2].reply


def test_h5b_login_con_id_solo_funciona(canal):
    t = converse(["no tengo internet", "tupaciretacuidaBAI"], canal=canal, profile="multi")
    sin_violaciones(t)
    assert "no pertenece" not in t[1].reply.lower()


def test_h6_diagnostico_agente_si(canal):
    """H6: pedido de agente tras el diagnóstico deriva directo; el «sí» posterior no crea otro ticket."""
    t = converse(["no tengo internet", "quiero hablar con un agente", "sí"], canal=canal)
    sin_violaciones(t)
    assert t[1].ticket_created and HANDOFF_OK.search(t[1].reply), t[1].reply
    assert not t[2].ticket_created and t[2].reply, t[2].reply


def test_h6b_agente_con_diagnostico_hecho_sin_confirmacion_pendiente(canal):
    """El journey queda en «respond» tras el diagnóstico (set completo de acciones): el pedido también deriva."""
    acciones = ("create_ticket", "run_diagnostic_pppoe", "service_list", "show_balance", "show_ticket", "request_account_selection")
    t = converse(["no tengo internet", "quiero hablar con un agente"], canal=canal, runtime_actions=acciones)
    sin_violaciones(t)
    assert t[1].ticket_created and HANDOFF_OK.search(t[1].reply), t[1].reply


@pytest.mark.parametrize("texto", ["no quiero hablar con un agente", "no necesito un agente", "¿necesito hablar con un agente?"])
def test_h6c_negacion_o_pregunta_no_crea_ticket(canal, texto):
    t = converse(["no tengo internet", texto], canal=canal)
    assert not any(x.ticket_created for x in t), (texto, t[1].reply)


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


def test_h9_sin_fijo_y_luego_hola(canal):
    """RC-12: el mensaje «sin Internet fijo» es terminal; el «hola» siguiente ya no lo repite."""
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


# =============================================================== reglas de producto R1/R2 (móvil + saldo pendiente)
#   R1 móvil/Sensa/VoIP: playbook + KB; si no se resuelve, ofrece agente y crea el ticket SOLO tras confirmar.
#   R2 deuda: aviso informativo, una sola vez por conversación; no bloquea y no se repite.
@xf("E13/R2: el aviso de saldo bloquea («¿Querés que te ayude primero a pagar, o seguimos…?») en vez de ser informativo y seguir con la pregunta del playbook")
def test_e13_movil_con_saldo_aviso_una_vez_y_sigue_playbook(canal):
    t = converse(BASE_MOVIL, canal=canal, profile="movil_deuda")
    sin_violaciones(t, servicio=(1, inv.VOCAB_MOVIL, ("Imowi 5 GB",)))
    r = t[2].reply
    assert avisos(t) == 1 and DEBT_NOTICE.search(r), r
    assert PREGUNTA_LLAMADAS.search(r) and "?" in r and not BLOQUEA.search(r), r


@xf("E14a: «no sigamos con el diagnóstico» tras el aviso cae en el saludo genérico y pierde el contexto")
def test_e14a_no_sigamos_ofrece_pago_o_repregunta(canal):
    t = converse(BASE_MOVIL + ["no sigamos con el diagnóstico"], canal=canal, profile="movil_deuda")
    sin_violaciones(t)
    r = t[3].reply
    assert PAGO.search(r) or inv.VOCAB_MOVIL.search(r), r


@xf("E14b: «sí, pagar» tras el aviso responde «No encuentro servicios contratados…» (el journey de servicios captura el texto) en vez de dar los links de pago")
def test_e14b_si_pagar_da_links(canal):
    t = converse(BASE_MOVIL + ["sí, pagar"], canal=canal, profile="movil_deuda")
    sin_violaciones(t)
    assert PAGO.search(t[3].reply), t[3].reply


@xf("E14c: «seguimos con el diagnóstico» tras el aviso cae en el saludo genérico en vez de seguir el playbook móvil")
def test_e14c_seguimos_continua_playbook(canal):
    t = converse(BASE_MOVIL + ["seguimos con el diagnóstico"], canal=canal, profile="movil_deuda")
    sin_violaciones(t)
    assert inv.VOCAB_MOVIL.search(t[3].reply) and "?" in t[3].reply, t[3].reply


@xf("E14d: un texto no relacionado tras el aviso resetea la conversación al saludo genérico y se pierde el contexto móvil")
def test_e14d_texto_no_relacionado_no_pierde_contexto(canal):
    t = converse(BASE_MOVIL + ["¿hasta qué hora atienden?", "seguimos con el diagnóstico"], canal=canal, profile="movil_deuda")
    sin_violaciones(t)
    assert inv.VOCAB_MOVIL.search(t[4].reply), t[4].reply


def test_e15_el_aviso_no_se_repite_en_el_turno_siguiente(canal):
    t = converse(BASE_MOVIL + ["ya reinicié y sigue igual", "sigue sin llamar"], canal=canal, profile="movil_deuda")
    assert avisos(t) == 1, [x.reply[:60] for x in t]


@xf("E16a/R1: tras las preguntas del playbook móvil el bot escala solo (ticket sin confirmación) y textos libres caen al listado de servicios")
def test_e16a_movil_sin_resolver_ofrece_agente_y_con_si_crea_ticket(canal):
    script = BASE_MOVIL + ["sigue igual", "ya probé todo", "sigue sin andar", "nada", "sí"]
    t = converse(script, canal=canal, profile="movil")
    sin_violaciones(t)
    ofrecio = [i for i, x in enumerate(t) if inv.CONFIRM_PROMPT.search(x.reply)]
    assert ofrecio, "nunca ofreció derivar con confirmación"
    assert all(not x.ticket_created for x in t[: ofrecio[0] + 1]), "creó el ticket antes de confirmar"
    assert t[-1].ticket_created, t[-1].reply


@xf("E16b/R1: sin confirmación explícita el bot igual crea el ticket (agotamiento del playbook)")
def test_e16b_movil_sin_confirmacion_no_crea_ticket(canal):
    script = BASE_MOVIL + ["sigue igual", "ya probé todo", "sigue sin andar", "nada", "no, gracias"]
    t = converse(script, canal=canal, profile="movil")
    sin_violaciones(t)
    assert not any(x.ticket_created for x in t), [(x.user, x.ticket_created) for x in t]
