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


def test_06_gracias_tras_resolver(canal):
    """RC-1: con la oferta de derivación pendiente, «ya funciona» la cancela (sin ticket) y el turno pasa al legacy."""
    t = converse(["no tengo internet", "ya funciona, muchas gracias"], canal=canal)
    sin_violaciones(t)
    assert not DERIVAR.search(t[1].reply), t[1].reply


def test_07_ya_se_arreglo(canal):
    t = converse(["no tengo internet", "ya se arregló"], canal=canal)
    sin_violaciones(t)
    assert ACUSE_RESUELTO.search(t[1].reply) and not DERIVAR.search(t[1].reply), t[1].reply


def test_08_consulta_de_ticket_abierto(canal):
    t = converse(["cómo va mi ticket"], canal=canal, ticket_abierto=True)
    sin_violaciones(t)
    assert re.search(r"ticket .*abierto", t[0].reply, re.I)


def test_09_corte_activo(canal):
    t = converse(["no tengo internet"], canal=canal, corte_activo=True)
    sin_violaciones(t)
    assert re.search(r"(incidencia|corte|zona)", t[0].reply, re.I), t[0].reply


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


JOURNEYS_R2 = [pytest.param(True, id="journeys_on"), pytest.param(False, id="journeys_off")]


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


def test_h7_ya_se_arreglo_tras_diagnostico(canal):
    t = converse(["no tengo internet", "ya se arregló", "gracias"], canal=canal)
    sin_violaciones(t)
    assert ACUSE_RESUELTO.search(t[1].reply) and not DERIVAR.search(t[1].reply), t[1].reply


def test_h8_elegir_sensa(canal):
    t = converse(["quiero ver el servicio de sensa tv"], canal=canal, profile="sensa")
    sin_violaciones(t)
    assert "?" in t[0].reply or "contame" in t[0].reply.lower(), t[0].reply


def test_h9_sin_fijo_y_luego_hola(canal):
    """RC-12: el mensaje «sin Internet fijo» es terminal; el «hola» siguiente ya no lo repite."""
    t = converse(["no tengo internet", "hola"], canal=canal, profile="movil")
    sin_violaciones(t)


def test_h10_problema_declarado_antes_de_elegir(canal):
    t = converse(["tengo problemas con mi línea de imowi", "1"], canal=canal, profile="movil")
    sin_violaciones(t)
    assert "?" in t[1].reply or "contame" in t[1].reply.lower() or "problema" in t[1].reply.lower(), t[1].reply
    # RC-9: el problema se guardó en eko_journey al abrir la selección, se retoma y se consume al elegir.
    assert t[0].journey_state.get("declared_problem") == "tengo problemas con mi línea de imowi", t[0].journey_state
    assert "retomo lo que me contabas" in t[1].reply.lower(), t[1].reply
    assert not t[1].journey_state.get("declared_problem"), t[1].journey_state


def test_rc9_seleccion_sin_problema_no_dice_retomo(canal):
    t = converse(["quiero ver el servicio de sensa tv"], canal=canal, profile="sensa")
    assert "retomo" not in t[0].reply.lower() and "?" in t[0].reply, t[0].reply


def test_rc9_tras_la_pregunta_siguiente_el_legacy_sigue_el_hilo(canal):
    t = converse(["tengo problemas con mi línea de imowi", "1", "no puedo hacer llamadas"], canal=canal, profile="movil")
    sin_violaciones(t)
    assert PREGUNTA_LLAMADAS.search(t[2].reply), t[2].reply


# =============================================================== comparación con journeys OFF (línea base legacy)
def test_base_off_corte_activo_avisa(canal):
    t = converse(["no tengo internet"], canal=canal, journeys=False, corte_activo=True)
    sin_violaciones(t)
    assert re.search(r"(incidencia|zona)", t[0].reply, re.I)


def test_base_off_agente_deriva_directo(canal):
    """ADR regla 5 en el legacy (sin journey): el pedido explícito ES la confirmación; el «sí» posterior no duplica."""
    t = converse(["no tengo internet", "quiero hablar con un agente", "sí"], canal=canal, journeys=False)
    sin_violaciones(t)
    assert t[1].ticket_created and HANDOFF_OK.search(t[1].reply), t[1].reply
    assert not t[2].ticket_created, t[2].reply


def test_base_off_agente_movil_deriva_directo(canal):
    t = converse(["tengo problemas con mi línea de imowi", "1", "quiero hablar con un agente"],
                 canal=canal, journeys=False, profile="movil")
    sin_violaciones(t)
    assert t[2].ticket_created and HANDOFF_OK.search(t[2].reply), t[2].reply


@pytest.mark.parametrize("texto", ["no necesito un agente", "¿necesito hablar con un agente?"])
def test_base_off_negacion_o_pregunta_no_crea_ticket(canal, texto):
    t = converse(["no tengo internet", texto], canal=canal, journeys=False)
    assert not any(x.ticket_created for x in t), (texto, t[1].reply)


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
@pytest.mark.parametrize("texto", ["no necesito un agente", "¿necesito hablar con un agente?"])
def test_f0_negacion_o_pregunta_sin_prompt_de_confirmacion(canal, journeys, texto):
    """Tanda 3 F0: nombrar al agente sin pedirlo no muestra «¿Confirmás…?» ni crea ticket."""
    t = converse(["no tengo internet", texto], canal=canal, journeys=journeys)
    assert not any(x.ticket_created for x in t), (texto, t[1].reply)
    assert t[1].reply and not inv.CONFIRM_PROMPT.search(t[1].reply), t[1].reply


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
@pytest.mark.parametrize("insiste", ["sí quiero un agente", "quiero hablar con una persona"])
def test_f0_pedido_sin_contexto_e_insistencia_deriva_directo(canal, journeys, insiste):
    """Pedido de agente sin contexto → el bot intenta ayudar → el abonado insiste → deriva sin otra vuelta."""
    t = converse(["quiero hablar con un agente", insiste], canal=canal, journeys=journeys)
    assert not t[0].ticket_created and re.search(r"ayudarte yo", t[0].reply), t[0].reply
    assert t[1].ticket_created and HANDOFF_OK.search(t[1].reply), t[1].reply
    assert not inv.CONFIRM_PROMPT.search(t[1].reply), t[1].reply


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
def test_e13_movil_con_saldo_aviso_una_vez_y_sigue_playbook(canal):
    t = converse(BASE_MOVIL, canal=canal, profile="movil_deuda")
    sin_violaciones(t, servicio=(1, inv.VOCAB_MOVIL, ("Imowi 5 GB",)))
    r = t[2].reply
    assert avisos(t) == 1 and DEBT_NOTICE.search(r), r
    assert PREGUNTA_LLAMADAS.search(r) and "?" in r and not BLOQUEA.search(r), r


def test_e14a_no_sigamos_ofrece_pago_o_repregunta(canal):
    t = converse(BASE_MOVIL + ["no sigamos con el diagnóstico"], canal=canal, profile="movil_deuda")
    sin_violaciones(t)
    r = t[3].reply
    assert PAGO.search(r) or inv.VOCAB_MOVIL.search(r), r


def test_e14b_si_pagar_da_links(canal):
    t = converse(BASE_MOVIL + ["sí, pagar"], canal=canal, profile="movil_deuda")
    sin_violaciones(t)
    assert PAGO.search(t[3].reply), t[3].reply


def test_e14c_seguimos_continua_playbook(canal):
    t = converse(BASE_MOVIL + ["seguimos con el diagnóstico"], canal=canal, profile="movil_deuda")
    sin_violaciones(t)
    assert inv.VOCAB_MOVIL.search(t[3].reply) and "?" in t[3].reply, t[3].reply


def test_e14d_texto_no_relacionado_no_pierde_contexto(canal):
    t = converse(BASE_MOVIL + ["¿hasta qué hora atienden?", "seguimos con el diagnóstico"], canal=canal, profile="movil_deuda")
    sin_violaciones(t)
    assert inv.VOCAB_MOVIL.search(t[4].reply), t[4].reply


def test_e15_el_aviso_no_se_repite_en_el_turno_siguiente(canal):
    t = converse(BASE_MOVIL + ["ya reinicié y sigue igual", "sigue sin llamar"], canal=canal, profile="movil_deuda")
    assert avisos(t) == 1, [x.reply[:60] for x in t]


def test_e16a_movil_sin_resolver_ofrece_agente_y_con_si_crea_ticket(canal):
    script = BASE_MOVIL + ["sigue igual", "ya probé todo", "sigue sin andar", "nada", "sí"]
    t = converse(script, canal=canal, profile="movil")
    sin_violaciones(t)
    ofrecio = [i for i, x in enumerate(t) if inv.CONFIRM_PROMPT.search(x.reply)]
    assert ofrecio, "nunca ofreció derivar con confirmación"
    assert all(not x.ticket_created for x in t[: ofrecio[0] + 1]), "creó el ticket antes de confirmar"
    assert t[-1].ticket_created, t[-1].reply


def test_e16b_movil_sin_confirmacion_no_crea_ticket(canal):
    script = BASE_MOVIL + ["sigue igual", "ya probé todo", "sigue sin andar", "nada", "no, gracias"]
    t = converse(script, canal=canal, profile="movil")
    sin_violaciones(t)
    assert not any(x.ticket_created for x in t), [(x.user, x.ticket_created) for x in t]


# ------------------------------------------------ RC-2: el «sí» confirma solo una oferta vigente del propio bot
def test_rc2_si_a_la_oferta_del_journey_crea_el_ticket(canal):
    t = converse(["no tengo internet", "sí"], canal=canal)
    sin_violaciones(t)
    assert inv.CONFIRM_PROMPT.search(t[0].reply) and not t[0].ticket_created, t[0].reply
    assert t[1].ticket_created and HANDOFF_OK.search(t[1].reply), t[1].reply


def test_rc2_si_tras_reofrecer_crea_el_ticket(canal):
    t = converse(["no tengo internet", "sigue igual", "sí"], canal=canal)
    assert not t[1].ticket_created
    assert t[2].ticket_created, t[2].reply


def test_rc2_no_a_la_oferta_no_crea_ticket(canal):
    t = converse(["no tengo internet", "no"], canal=canal)
    assert not any(x.ticket_created for x in t), t[1].reply


@pytest.mark.parametrize("script,perfil", [(["hola", "sí"], "int1"), (["tengo deuda?", "sí"], "deuda"),
                                           (["cómo va mi ticket", "sí"], "int1")])
def test_rc2_si_suelto_sin_oferta_no_crea_ticket(canal, script, perfil):
    t = converse(script, canal=canal, profile=perfil, ticket_abierto=script[0].startswith("cómo"))
    assert not any(x.ticket_created for x in t), [(x.user, x.reply[:80]) for x in t]


def test_rc9_tv_tras_la_pregunta_siguiente_no_se_pierde_el_servicio(canal):
    t = converse(["no me anda la tele sensa", "no me abre la app de sensa"], canal=canal, profile="sensa")
    sin_violaciones(t, servicio=(-1, inv.VOCAB_TV, ()))
    assert not any(x.ticket_created for x in t) and t[1].reply, t[1].reply


# ------------------------------------------------ RC-1: la oferta pendiente expira (repregunta una vez → PASS)
def test_rc1_repregunta_una_vez_y_a_la_segunda_suelta_el_turno(canal):
    t = converse(["no tengo internet", "sigue igual", "sigue igual"], canal=canal)
    assert inv.CONFIRM_PROMPT.search(t[1].reply) and t[1].journey_state.get("reprompts") == 1, t[1].reply
    assert t[2].reply and not inv.CONFIRM_PROMPT.search(t[2].reply), t[2].reply
    assert t[2].branch.startswith("legacy:"), t[2].branch
    js = t[2].journey_state
    assert not js.get("pending_confirmation") and not js.get("next_required_input") and js.get("step") == "done", js
    assert not any(x.ticket_created for x in t)


def test_rc1_ya_anda_cancela_la_oferta_sin_repreguntar(canal):
    """RC-1 + RC-3 fase B (§c): «ya anda» cancela la oferta; el journey acusa y pasa a done (sin ticket, sin repreguntar)."""
    t = converse(["no tengo internet", "ya anda"], canal=canal)
    sin_violaciones(t)
    assert ACUSE_RESUELTO.search(t[1].reply) and not inv.CONFIRM_PROMPT.search(t[1].reply), t[1].reply
    assert t[1].journey_state.get("step") == "done" and not t[1].journey_state.get("pending_confirmation"), t[1].journey_state
    assert not any(x.ticket_created for x in t)


def test_rc1_el_pass_no_toca_la_seleccion(canal):
    t = converse(["no tengo internet", "lemuramatiBAI", "sigue igual", "sigue igual"], canal=canal, profile="multi")
    ref = t[1].journey_state.get("selected_service_ref")
    assert ref and ref.get("login") == "lemuramatiBAI", t[1].journey_state
    assert t[3].branch.startswith("legacy:"), t[3].branch
    assert t[3].journey_state.get("selected_service_ref") == ref, t[3].journey_state


# ------------------------------------------------ RC-5: con contexto vivo el legacy no cae en el saludo genérico
@pytest.mark.parametrize("texto,esperado", [("quiero pagar", PAGO), ("seguí con el diagnóstico", inv.VOCAB_INTERNET)])
def test_rc5_off_respuesta_al_aviso_retoma_el_tema(canal, texto, esperado):
    """Journeys OFF: el 1.er turno sale por la transición de dominio; el 2.º no se toma como elección del menú inicial."""
    t = converse(["no tengo internet", texto], canal=canal, profile="deuda", journeys=False)
    sin_violaciones(t)
    assert esperado.search(t[1].reply), t[1].reply


def test_rc5_on_hold_del_journey_devuelve_la_intencion_previa(canal):
    """Journeys ON: el hold del journey resuelto es un PASS; el legacy recibe la intención que había, no la del journey."""
    t = converse(BASE_MOVIL + ["seguimos con el diagnóstico"], canal=canal, profile="movil_deuda")
    sin_violaciones(t)
    assert t[3].branch.startswith("legacy:") and PREGUNTA_LLAMADAS.search(t[3].reply), t[3].reply
    assert t[3].journey_state.get("released_reason") == "post_resolution_hold", t[3].journey_state


# ------------------------------------------------ RC-6/7: un solo emisor del aviso de saldo (R2)
@pytest.mark.parametrize("journeys", JOURNEYS_R2)
def test_rc67_aviso_va_antes_de_la_respuesta_tecnica_y_no_cambia_la_intencion(canal, journeys):
    t = converse(["no tengo internet", "sigue igual", "sigue sin andar"], canal=canal, profile="deuda", journeys=journeys)
    assert len(t[0].replies) == 2 and DEBT_NOTICE.search(t[0].replies[0]), t[0].replies
    assert not DEBT_NOTICE.search(t[0].replies[1]) and inv.VOCAB_INTERNET.search(t[0].replies[1]), t[0].replies
    assert avisos(t) == 1 and not any(BLOQUEA.search(x.reply) for x in t), [x.reply[:80] for x in t]


def test_rc67_sin_saldo_no_hay_aviso(canal):
    t = converse(["no tengo internet"], canal=canal, profile="int1")
    assert avisos(t) == 0, t[0].reply


# ------------------------------------------------ H11: el aviso de deuda no deja facturación viva
H11_SCRIPT = ["hola", "por telefonia movil", "tencnico. no puedo hacer llamadas", "no las recibo", "no te pregunte por la factura"]
FACTURACION = re.compile(r"(factura|aumento|cobro|c[oó]mo pagar|facturaci[oó]n|ov\.batan)", re.I)


def test_h11_no_las_recibo_sigue_el_playbook_movil(canal):
    t = converse(H11_SCRIPT[:4], canal=canal, profile="movil_deuda")
    sin_violaciones(t)
    assert avisos(t) == 1 and DEBT_NOTICE.search(t[2].reply) and inv.VOCAB_MOVIL.search(t[2].reply + " llamada"), t[2].reply
    assert not FACTURACION.search(t[3].reply) and PLAYBOOK_MOVIL_PREGUNTAS.search(t[3].reply), t[3].reply


def test_h11_negacion_sobre_el_tema_no_abre_facturacion(canal):
    t = converse(H11_SCRIPT, canal=canal, profile="movil_deuda")
    sin_violaciones(t)
    assert not any(x.branch.startswith("journey:billing") or FACTURACION.search(x.reply) for x in t[3:]), [(x.branch, x.reply) for x in t[3:]]
    assert t[4].reply and PLAYBOOK_MOVIL_PREGUNTAS.search(t[4].reply), t[4].reply


# ------------------------------------------------ RC-13: el playbook avanza con respuestas libres
PLAYBOOK_MOVIL_PREGUNTAS = re.compile(r"(reinici|anduvo|modo avi|mejor[oó]|zona|varios lados|sms|a2p|derive)", re.I)


def test_rc13_respuesta_libre_avanza_el_playbook(canal):
    t = converse(BASE_MOVIL + ["no las recibo"], canal=canal, profile="movil")
    sin_violaciones(t)
    assert t[3].reply != t[2].reply and PLAYBOOK_MOVIL_PREGUNTAS.search(t[3].reply), (t[2].reply, t[3].reply)
    assert not FACTURACION.search(t[3].reply), t[3].reply


def test_rc13_respuesta_no_reconocida_repregunta_una_vez_y_avanza(canal):
    t = converse(BASE_MOVIL + ["depende del día", "quizás"], canal=canal, profile="movil")
    assert t[3].reply != t[2].reply and t[3].reply.endswith(t[2].reply.split(". ", 1)[-1]), (t[2].reply, t[3].reply)
    assert t[4].reply not in (t[2].reply, t[3].reply) and PLAYBOOK_MOVIL_PREGUNTAS.search(t[4].reply), t[4].reply


# ------------------------------------------------ RC-3 fase B: lista blanca de §c para un journey resuelto
def test_rc3b_texto_libre_sin_dominio_no_reclama_el_journey_resuelto(canal):
    t = converse(["no tengo internet", "ya se arregló", "sigue igual", "gracias"], canal=canal)
    assert not any(x.ticket_created for x in t)
    assert not any(re.search(r"(servicios contratados|facturas|ov\.batan)", x.reply, re.I) for x in t[2:]), [x.reply for x in t[2:]]


def test_rc3b_gracias_tras_ya_anda_es_silencio_del_journey(canal):
    t = converse(["no tengo internet", "ya anda", "gracias"], canal=canal)
    sin_violaciones(t)
    assert t[2].branch.startswith("journey-silencio:") and not t[2].reply, (t[2].branch, t[2].reply)


def test_rc3b_acto_de_facturacion_reclama_el_journey_resuelto(canal):
    t = converse(["no tengo internet", "ya se arregló", "sí, pagar"], canal=canal, profile="deuda")
    assert PAGO.search(t[2].reply) and t[2].branch.startswith("journey:billing"), (t[2].branch, t[2].reply)


# ------------------------------------------------ Tanda 5 F0: H11 con el camino de LLM (proveedor falso «normal»)
@pytest.mark.parametrize("journeys", JOURNEYS_R2)
def test_h11_con_llm_no_las_recibo_no_cae_en_facturacion(canal, journeys):
    t = converse(["tengo problemas con mi línea de imowi", "1", "llamadas", "no las recibo"],
                 canal=canal, profile="movil", llm="normal", journeys=journeys)
    assert t[3].reply and not FACTURACION.search(t[3].reply), (t[3].branch, t[3].reply)


@pytest.mark.parametrize("texto", ["quiero pagar mi factura", "tengo una duda con la factura"])
@pytest.mark.parametrize("journeys", JOURNEYS_R2)
def test_h11_con_llm_un_pedido_real_de_facturacion_tras_la_pregunta_sigue_yendo_a_facturacion(canal, journeys, texto):
    """La guarda de «respuesta al playbook» no puede tapar un pedido real de facturación."""
    t = converse(["tengo problemas con mi línea de imowi", "1", "llamadas", texto],
                 canal=canal, profile="movil", llm="normal", journeys=journeys)
    assert re.search(r"(factura|pagar|pago|saldo|oficina virtual|ov\.batan|aumento|cobro)", t[3].reply, re.I), (t[3].branch, t[3].reply)


# ------------------------------------------------ RC-8: el corte masivo manda sobre el journey de conectividad
CORTE = re.compile(r"(incidencia|corte|zona)", re.I)


def test_rc8_corte_activo_no_ofrece_derivar_ni_crea_ticket(canal):
    t = converse(["no tengo internet", "sigue igual"], canal=canal, corte_activo=True)
    sin_violaciones(t)
    assert not any(x.ticket_created for x in t)
    assert not any(inv.CONFIRM_PROMPT.search(x.reply) or "No veo una sesión" in x.reply for x in t), [x.reply for x in t]
    assert all(CORTE.search(x.reply) for x in t), [x.reply for x in t]


def test_rc8_con_corte_activo_la_facturacion_no_queda_bloqueada(canal):
    t = converse(["cuánto debo"], canal=canal, profile="deuda", corte_activo=True)
    assert re.search(r"(15\.000|saldo|deuda)", t[0].reply, re.I), t[0].reply


def test_rc8_sin_corte_el_journey_diagnostica_como_siempre(canal):
    t = converse(["no tengo internet"], canal=canal, profile="int1")
    assert "No veo una sesión" in t[0].reply or inv.VOCAB_INTERNET.search(t[0].reply), t[0].reply
    assert not CORTE.search(t[0].reply) or "No veo una sesión" in t[0].reply, t[0].reply


# ------------------------------------------------ RC-4 / R1: el agotamiento OFRECE derivar, el «sí» crea el ticket
RELLENO_PLAYBOOK = ["sigue igual", "ya probé todo", "sigue sin andar", "nada", "nada", "nada"]  # sin repetir «sigue sin andar»: eso dispara la vía de frustración


def _hasta_la_oferta(canal, **kw):
    """Cantidad de turnos de relleno hasta que el bot ofrece derivar. Depende del playbook vigente (código o
    override de la base: 4 o 6 pasos), así que se mide en vez de fijarlo."""
    t = converse(BASE_MOVIL + RELLENO_PLAYBOOK, canal=canal, profile="movil", **kw)
    for i, x in enumerate(t[3:], start=1):
        if inv.CONFIRM_PROMPT.search(x.reply):
            return i
    raise AssertionError(f"nunca ofreció derivar: {[x.reply[:50] for x in t]}")


def test_rc4_la_oferta_no_crea_ticket_y_el_si_posterior_lo_crea(canal):
    n = _hasta_la_oferta(canal)
    t = converse(BASE_MOVIL + RELLENO_PLAYBOOK[:n] + ["sí"], canal=canal, profile="movil")
    assert inv.CONFIRM_PROMPT.search(t[2 + n].reply) and not any(x.ticket_created for x in t[: 3 + n]), t[2 + n].reply
    assert t[3 + n].ticket_created and HANDOFF_OK.search(t[3 + n].reply), t[3 + n].reply


def test_rc4_un_no_cancela_la_oferta_sin_ticket(canal):
    n = _hasta_la_oferta(canal)
    t = converse(BASE_MOVIL + RELLENO_PLAYBOOK[:n] + ["no, gracias"], canal=canal, profile="movil")
    assert not any(x.ticket_created for x in t) and t[3 + n].reply and not inv.CONFIRM_PROMPT.search(t[3 + n].reply), t[3 + n].reply


def test_rc4_un_texto_no_relacionado_cancela_la_oferta_y_un_si_posterior_no_deriva(canal):
    n = _hasta_la_oferta(canal)
    t = converse(BASE_MOVIL + RELLENO_PLAYBOOK[:n] + ["¿hasta qué hora atienden?", "sí"], canal=canal, profile="movil")
    assert not any(x.ticket_created for x in t), [(x.user, x.ticket_created) for x in t]


def test_rc4_una_respuesta_corta_confusa_repregunta_una_vez_y_luego_el_si_deriva(canal):
    n = _hasta_la_oferta(canal)
    t = converse(BASE_MOVIL + RELLENO_PLAYBOOK[:n] + ["nada", "sí"], canal=canal, profile="movil")
    assert "No te entendí" in t[3 + n].reply and not t[3 + n].ticket_created, t[3 + n].reply
    assert t[4 + n].ticket_created, t[4 + n].reply


def test_rc4_el_pedido_explicito_de_agente_sigue_derivando_directo(canal):
    """Sin journey resuelto (journeys OFF; con el journey resuelto rige la excepción H6 del ADR) el pedido ES la
    confirmación, también con una oferta de derivar vigente."""
    n = _hasta_la_oferta(canal, journeys=False)
    t = converse(BASE_MOVIL + RELLENO_PLAYBOOK[:n] + ["quiero hablar con un agente"], canal=canal, profile="movil", journeys=False)
    assert not any(x.ticket_created for x in t[: 3 + n]) and t[3 + n].ticket_created and HANDOFF_OK.search(t[3 + n].reply), t[3 + n].reply


def test_rc3b_seguimiento_de_incidente_no_lo_toma_el_journey_de_servicios(canal):
    """§c: «sigue igual» tras elegir un servicio móvil lo atiende el playbook, no el listado de servicios."""
    t = converse(BASE_MOVIL + ["sigue igual"], canal=canal, profile="movil")
    sin_violaciones(t)
    assert not re.search(r"servicios contratados", t[3].reply, re.I) and t[3].branch.startswith("legacy:"), (t[3].branch, t[3].reply)


# ------------------------------------------------ Tanda 5 F3b: un afirmativo ambiguo no resuelve el caso
@pytest.mark.parametrize("texto", ["ok si funciona", "ok, aviso si funciona"])
def test_f3b_afirmativo_ambiguo_no_resuelve_ni_cierra(canal, texto):
    t = converse(["tengo problemas con mi línea de imowi", "1", "llamadas", texto], canal=canal, profile="movil", llm="avisame")
    assert t[3].estado != "cerrado" and t[3].modo != "cerrado", (t[3].estado, t[3].reply)
    assert re.search(r"(pudiste|recibir la llamada|llamada de prueba)", t[3].reply, re.I) and "?" in t[3].reply, t[3].reply
    assert not re.search(r"(me alegra|genial|resuelto|calificaci)", t[3].reply, re.I), t[3].reply


# ------------------------------------------------ Tanda 6 F1: respuestas de una palabra a un paso del playbook
PASO_MOVIL = re.compile(r"(modo avi|reinici|datos|se[ñn]al|apn|sim|chip|zona|llam|derive|qu[eé] te pasa)", re.I)
LLM_UNA_PALABRA = [
    pytest.param("down", id="llm_down"),
    pytest.param("normal", id="llm_normal"),
    pytest.param("primer_paso", id="llm_primer_paso"),
]


@pytest.mark.parametrize("llm", LLM_UNA_PALABRA)
@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
@pytest.mark.parametrize("respuesta", ["no", "no puedo"])
def test_f1_respuesta_de_una_palabra_no_repite_el_paso(canal, journeys, llm, respuesta):
    t = converse(["tengo problemas con mi línea de imowi", "1", "se me cortan", respuesta, respuesta],
                 canal=canal, profile="movil", journeys=journeys, llm=llm)
    sin_violaciones(t)  # I5: nunca dos veces seguidas el mismo texto
    assert not any(x.ticket_created for x in t)
    if llm != "normal":  # el proveedor «normal» no pregunta pasos: solo se exige no repetir ni derivar
        assert t[3].reply != t[2].reply and PASO_MOVIL.search(t[3].reply), (t[2].reply, t[3].reply)
        assert t[4].reply != t[3].reply, (t[3].reply, t[4].reply)


# ------------------------------------------------ Tanda 7 F1: la frustración OFRECE derivar (R1), no crea ticket
BASE_FRUSTRACION = ["tengo problemas con mi línea de imowi", "1", "tecnico"]
FRUSTRACION = ["sin señal", "sin señal", "sin señal"]  # la misma queja repetida con el playbook ya avanzado (paso_idx ≥ 2)


_FRUS = BASE_FRUSTRACION + FRUSTRACION[:2]  # el 2.º «sin señal» (índice 4) es el que dispara la frustración


@pytest.mark.parametrize("llm", ["down", "normal"])
@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_t7f1_frustracion_ofrece_derivar_y_no_crea_ticket(canal, journeys, llm):
    t = converse(_FRUS, canal=canal, profile="movil", journeys=journeys, llm=llm)
    assert not any(x.ticket_created for x in t), [(x.user, x.ticket_created) for x in t]
    assert inv.CONFIRM_PROMPT.search(t[-1].reply) and t[-1].reply.rstrip().endswith("?"), t[-1].reply


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_t7f1_el_si_a_la_oferta_por_frustracion_crea_el_ticket(canal, journeys):
    t = converse(_FRUS + ["sí"], canal=canal, profile="movil", journeys=journeys)
    assert not any(x.ticket_created for x in t[:5]) and t[5].ticket_created and HANDOFF_OK.search(t[5].reply), [x.reply for x in t[4:]]


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_t7f1_el_no_cancela_la_oferta_sin_ticket(canal, journeys):
    t = converse(_FRUS + ["no, gracias"], canal=canal, profile="movil", journeys=journeys)
    assert not any(x.ticket_created for x in t) and inv.CONFIRM_PROMPT.search(t[4].reply) and not inv.CONFIRM_PROMPT.search(t[5].reply), [x.reply for x in t[4:]]


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_t7f1_texto_ajeno_cancela_la_oferta_y_un_si_posterior_no_deriva(canal, journeys):
    t = converse(_FRUS + ["¿hasta qué hora atienden?", "sí"], canal=canal, profile="movil", journeys=journeys)
    assert inv.CONFIRM_PROMPT.search(t[4].reply) and not any(x.ticket_created for x in t), [(x.user, x.ticket_created) for x in t]


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_t7f1_respuesta_confusa_repregunta_una_vez_y_luego_el_si_deriva(canal, journeys):
    t = converse(_FRUS + ["nada", "sí"], canal=canal, profile="movil", journeys=journeys)
    assert inv.CONFIRM_PROMPT.search(t[4].reply) and "No te entendí" in t[5].reply and not t[5].ticket_created, [x.reply for x in t[4:]]
    assert t[6].ticket_created, t[6].reply


# ------------------------------------------------ Tanda 7 F2: derivado a un agente no se califica en el cierre del bot
DERIVACIONES = {
    "oferta_confirmada": (_FRUS + ["sí"], "movil", 5),
    "pedido_de_agente": (["no tengo internet", "quiero hablar con un agente"], "int1", 1),
}


@pytest.mark.parametrize("cierre", ["gracias", "ya funciona"])
@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
@pytest.mark.parametrize("via", list(DERIVACIONES))
def test_t7f2_derivado_a_un_agente_no_pide_calificacion(canal, via, journeys, cierre):
    script, profile, idx = DERIVACIONES[via]
    t = converse(script + [cierre], canal=canal, profile=profile, journeys=journeys)
    assert t[idx].ticket_created, [(x.user, x.reply) for x in t]
    assert not any(x.encuesta for x in t), [(x.user, x.estado, x.encuesta) for x in t]


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_t7f2_resuelto_por_el_bot_sigue_pidiendo_la_calificacion(canal, journeys):
    t = converse(["no tengo internet", "ya funciona", "no, nada más"], canal=canal, profile="int1", journeys=journeys)
    assert not any(x.ticket_created for x in t), [(x.user, x.ticket_created) for x in t]
    assert any(x.encuesta for x in t), [(x.user, x.estado, x.encuesta) for x in t]


# ------------------------------------------------ H12 (a): la secuencia de prod. NO reproduce con el harness (ver informe de la fase 1)
H12 = ["tengo problemas con mi línea de imowi", "1", "tecnico, no puedo hacer llamadas", "se me cortan", "no", "que tiene que ver el wifi"]


@pytest.mark.parametrize("llm", ["down", "normal", "primer_paso"])
@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_h12_conversacion_movil_no_habla_de_internet_fijo(canal, journeys, llm):
    """I8 sobre la secuencia de prod con los playbooks de prod. Pasa hoy: el texto de Wi-Fi sale de la rama del LLM real
    (ver tests/test_h12_movil_sin_heuristica_wifi.py), que el harness no puede imitar sin conocer su respuesta."""
    t = converse(H12, canal=canal, profile="movil_deuda", journeys=journeys, llm=llm, playbooks_prod=True)
    sin_violaciones(t, servicio_sin_internet_fijo=True)


# ------------------------------------------------ H12 (e): un paso de derivación del playbook no deriva solo, se confirma
# Textos reales del editor de playbooks de prod. El código fuerza la confirmación sin importar cómo lo redactó el admin.
_PROD_LLAMADAS = ["tengo problemas con mi línea de imowi", "1", "tecnico, no puedo hacer llamadas", "se me cortan", "no"]  # → derivar_llamadas
_PROD_MOVIL = ["tengo problemas con mi línea de imowi", "1", "tecnico, no tengo señal", "no", "no", "no", "no"]  # → otra_ubicacion


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
@pytest.mark.parametrize("script,perfil", [(_PROD_LLAMADAS, "movil_deuda"), (_PROD_MOVIL, "movil")], ids=["derivar_llamadas", "otra_ubicacion"])
def test_h12e_paso_de_derivacion_no_crea_ticket_por_si_solo(canal, journeys, script, perfil):
    t = converse(script, canal=canal, profile=perfil, journeys=journeys, playbooks_prod=True)
    assert not any(x.ticket_created for x in t), [(x.user, x.ticket_created) for x in t]


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_h12e_paso_de_derivacion_sin_pregunta_fuerza_la_confirmacion(canal, journeys):
    t = converse(_PROD_MOVIL, canal=canal, profile="movil", journeys=journeys, playbooks_prod=True)
    assert t[-1].reply.rstrip().endswith("?") and t[-1].pending_offer, (t[-1].reply, t[-1].pending_offer)
    assert inv.CONFIRM_PROMPT.search(t[-1].reply), t[-1].reply
    t = converse(_PROD_MOVIL + ["sí"], canal=canal, profile="movil", journeys=journeys, playbooks_prod=True)
    assert t[-1].ticket_created, t[-1].reply


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_h12e_paso_de_derivacion_con_pregunta_deja_la_oferta_y_el_si_deriva(canal, journeys):
    t = converse(_PROD_LLAMADAS, canal=canal, profile="movil_deuda", journeys=journeys, playbooks_prod=True)
    assert t[-1].reply.rstrip().endswith("?") and t[-1].pending_offer, (t[-1].reply, t[-1].pending_offer)
    t = converse(_PROD_LLAMADAS + ["sí"], canal=canal, profile="movil_deuda", journeys=journeys, playbooks_prod=True)
    assert t[-1].ticket_created, t[-1].reply


# ------------------------------------------------ H12 (fase 2): una pregunta de aclaración no cancela la oferta pendiente
ACLARACIONES = ["que tiene que ver el wifi", "por qué", "para qué", "no entiendo", "qué significa"]


@pytest.mark.parametrize("pregunta", ACLARACIONES)
@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_h12_aclaracion_repite_la_oferta_y_no_la_cancela(canal, journeys, pregunta):
    t = converse(_PROD_LLAMADAS + [pregunta], canal=canal, profile="movil_deuda", journeys=journeys, playbooks_prod=True)
    assert not any(x.ticket_created for x in t)
    assert inv.CONFIRM_PROMPT.search(t[-1].reply) and t[-1].reply.rstrip().endswith("?") and t[-1].pending_offer, t[-1].reply
    assert t[-1].reply != t[-2].reply and not inv.OTRO_DOMINIO_FIJO.search(t[-1].reply), (t[-2].reply, t[-1].reply)
    t = converse(_PROD_LLAMADAS + [pregunta, "sí"], canal=canal, profile="movil_deuda", journeys=journeys, playbooks_prod=True)
    assert t[-1].ticket_created, t[-1].reply


@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_h12_pregunta_de_otro_tema_sigue_cancelando_la_oferta(canal, journeys):
    t = converse(_PROD_LLAMADAS + ["cuánto debo", "sí"], canal=canal, profile="movil_deuda", journeys=journeys, playbooks_prod=True)
    assert not any(x.ticket_created for x in t), [(x.user, x.reply[:60]) for x in t[-2:]]
    assert re.search(r"(15\.000|saldo|deuda|factura)", t[-2].reply, re.I) and not inv.CONFIRM_PROMPT.search(t[-2].reply), t[-2].reply


# ------------------------------------------------ H13: la cortesía pura con derivación pendiente no cierra el hilo

@pytest.mark.parametrize("cortesia", ["gracias", "ok gracias", "listo"])
@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
@pytest.mark.parametrize("via", list(DERIVACIONES))
def test_h13_cortesia_tras_derivar_no_cierra(canal, via, journeys, cortesia):
    script, profile, idx = DERIVACIONES[via]
    t = converse(script + [cortesia], canal=canal, profile=profile, journeys=journeys)
    assert t[idx].ticket_created and t[idx].estado in ("espera_agente", "con_agente"), (t[idx].estado, t[idx].reply)
    u = t[-1]
    assert u.estado in ("espera_agente", "con_agente"), (u.estado, u.reply)
    assert re.search(r"agente", u.reply, re.I) and not re.search(r"(lindo d[ií]a|cualquier otra consulta)", u.reply, re.I), u.reply
    assert not any(x.encuesta for x in t), [(x.user, x.estado, x.encuesta) for x in t]


# ------------------------------------------------ H14: el paso de reinicio se prueba SIEMPRE antes de ofrecer derivar en móvil
REINICIO_LLAMADAS = [("reinicio_llamadas", re.compile(r"Reinici[aá] y prob[aá] una llamada", re.I))]
H14_BASE = ["tengo problemas con mi línea de imowi", "1", "tecnico, no puedo recibir llamadas", "se me cortan"]


# Reproducía solo con el proveedor «sms_red» (un LLM que pregunta por SMS fuera del playbook y responde a una pregunta
# propia): el «no» cubría reinicio_llamadas sin que nadie lo hubiera preguntado.
H14_CASOS = [(llm, j, r) for llm in ("down", "normal", "sms_red") for j in (True, False) for r in ("no, solo las llamadas", "no", "solo llamadas")]


@pytest.mark.parametrize(("llm", "journeys", "respuesta"), H14_CASOS)
def test_h14_el_reinicio_va_antes_de_ofrecer_derivar(canal, llm, journeys, respuesta):
    t = converse(H14_BASE + [respuesta], canal=canal, profile="movil_deuda", journeys=journeys, llm=llm, playbooks_prod=True)
    sin_violaciones(t, pasos_antes_de_derivar=REINICIO_LLAMADAS)
    assert not any(x.ticket_created for x in t)


# ------------------------------------------------ H15: «ya funciona» con un ticket derivado abierto no cierra ni califica

@pytest.mark.parametrize("resuelto", ["ya funciona", "ya anda", "ya se arregló"])
@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
@pytest.mark.parametrize("via", list(DERIVACIONES))
def test_h15_resuelto_con_ticket_derivado_no_cierra_ni_califica(canal, via, journeys, resuelto):
    script, profile, idx = DERIVACIONES[via]
    t = converse(script + [resuelto], canal=canal, profile=profile, journeys=journeys)
    assert t[idx].ticket_created and t[idx].estado in ("espera_agente", "con_agente"), (t[idx].estado, t[idx].reply)
    u = t[-1]
    assert u.estado in ("espera_agente", "con_agente"), (u.estado, u.reply)
    assert t[idx].ticket_id in u.reply and re.search(r"agente", u.reply, re.I), (t[idx].ticket_id, u.reply)
    assert not u.reply.rstrip().endswith("?") and not re.search(r"(lindo d[ií]a|cualquier otra consulta)", u.reply, re.I), u.reply
    assert not any(x.encuesta for x in t), [(x.user, x.estado, x.encuesta) for x in t]


# ------------------------------------------------ H16: Internet fibra con deuda (evidencia de prod): tres bucles
H16 = [
    "internet",
    "ya lo hice. la potencia de la fibra es buena?",
    "me anda lento. tengo buena potencia?",
    "si esta en verde pero me anda lento. que potencia tengo en la fibra",
    "me anda lento",
    "100",
    "ok y la potencia de la fibra esta bien?",
]
H16_POTENCIA = (1, 3, 6)  # turnos en que el abonado pregunta por la potencia de la fibra
RESPUESTA_POTENCIA = re.compile(r"(potencia|dbm|no puedo (leer|ver|consultar)|no tengo (el )?dato|lectura)", re.I)
_H16_LLMS = ("down", "normal", "primer_paso")
H16_CASOS = [(llm, j) for llm in _H16_LLMS for j in (True, False)]


def _h16(canal, llm, journeys):
    return converse(H16, canal=canal, profile="fibra_deuda", journeys=journeys, llm=llm)


@pytest.mark.parametrize(("llm", "journeys"), H16_CASOS)
def test_h16_a_la_pregunta_de_potencia_se_le_responde(canal, llm, journeys):
    t = _h16(canal, llm, journeys)
    sin_respuesta = [i for i in H16_POTENCIA if not RESPUESTA_POTENCIA.search(t[i].reply)]
    assert not sin_respuesta, [(i, t[i].user, t[i].reply[:80]) for i in sin_respuesta]


@pytest.mark.parametrize(("llm", "journeys"), H16_CASOS)
def test_h16_no_repite_el_paso_de_la_ont_ya_hecho(canal, llm, journeys):
    t = _h16(canal, llm, journeys)
    paso_ont = t[0].replies[-1]  # el paso de la ONT del primer turno; «ya lo hice» lo cubre
    repetidos = [
        i for i in range(2, len(t)) if t[i].reply and (t[i].reply == paso_ont or re.search(r"(cajita (blanca )?tiene luces|ONT .{0,30}tiene luces)", t[i].reply, re.I))
    ]
    assert not repetidos, [(i, t[i].user, t[i].reply[:80]) for i in repetidos]


@pytest.mark.parametrize(("llm", "journeys"), H16_CASOS)
def test_h16_no_vuelve_a_preguntar_que_le_pasa_con_el_problema_declarado(canal, llm, journeys):
    t = _h16(canal, llm, journeys)
    vuelve = [i for i in range(2, len(t)) if re.search(r"(contame qu[eé] te pasa|qu[eé] te pasa con ese internet)", t[i].reply, re.I)]
    assert not vuelve, [(i, t[i].user, t[i].reply[:80]) for i in vuelve]


@pytest.mark.parametrize(("llm", "journeys"), H16_CASOS)
def test_h16_la_conversacion_de_internet_no_habla_de_telefonia_movil(canal, llm, journeys):
    t = _h16(canal, llm, journeys)
    sin_violaciones(t, solo=("I8i",), servicio_solo_internet=True)
