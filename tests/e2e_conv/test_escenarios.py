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


@xf("S9: con journeys ON el corte masivo activo se ignora («No veo una sesión…»); el aviso de corte solo existe en el legacy")
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


@xf("H7 (tras RC-1): «ya se arregló» se acusa, pero el legacy cierra la conversación y el «gracias» siguiente abre una nueva con el saludo que pide DNI")
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


@xf("E14b: «sí, pagar» tras el aviso responde «No encuentro servicios contratados…» (el journey de servicios captura el texto) en vez de dar los links de pago")
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
    t = converse(["no tengo internet", "ya anda"], canal=canal)
    sin_violaciones(t)
    assert t[1].branch.startswith("legacy:") and not inv.CONFIRM_PROMPT.search(t[1].reply), t[1].reply
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
    assert not FACTURACION.search(t[3].reply) and re.search(r"(llam|señal|reinici|anduvo|pantalla|sim)", t[3].reply, re.I), t[3].reply


def test_h11_negacion_sobre_el_tema_no_abre_facturacion(canal):
    t = converse(H11_SCRIPT, canal=canal, profile="movil_deuda")
    # Sin I5: el bot repite la pregunta del playbook («¿Anduvo?») en los turnos 3 y 4 (hallazgo aparte de H11).
    v = [x for x in inv.violaciones(t) if not x.startswith("I5")]
    assert not v, v
    assert not any(x.branch.startswith("journey:billing") or FACTURACION.search(x.reply) for x in t[3:]), [(x.branch, x.reply) for x in t[3:]]
    assert t[4].reply and re.search(r"(llam|anduvo|reinici)", t[4].reply, re.I), t[4].reply
