"""Los invariantes detectan lo que dicen detectar (sin DB ni journeys)."""

from __future__ import annotations

from tests.e2e_conv import invariants as inv
from tests.e2e_conv.harness import Turn


def T(user, reply="", **kw):
    return Turn(user=user, replies=[reply] if reply else [], **kw)


def test_i1_respuesta_vacia_salvo_cortesia():
    assert inv.i1_sin_respuesta_vacia([T("no anda internet")])
    assert not inv.i1_sin_respuesta_vacia([T("gracias")])
    assert not inv.i1_sin_respuesta_vacia([T("no anda", "Probá reiniciar")])


def test_i2_saludo_generico_a_mitad():
    bien = [T("hola", "Hola, soy Eko"), T("no anda", "¿Luces del módem?")]
    mal = [T("hola", "Hola"), T("no anda internet", "Hola, soy Eco, de Soporte Batán. ¿En qué te ayudo?")]
    assert not inv.i2_sin_saludo_generico(bien)
    assert inv.i2_sin_saludo_generico(mal)
    # si el usuario vuelve a saludar, es válido
    assert not inv.i2_sin_saludo_generico([T("x", "y"), T("hola", "Hola, soy Eko")])


def test_i3_agente():
    assert inv.i3_agente_deriva([T("quiero hablar con un agente", "Ya revisé tu conexión")])
    assert not inv.i3_agente_deriva([T("quiero hablar con un agente", "Para derivar con un agente, confirmame con un «sí».")])
    assert not inv.i3_agente_deriva([T("quiero hablar con un agente", "Dale, te derivo. Ticket IBOT-1.")])
    assert not inv.i3_agente_deriva([T("quiero hablar con un agente", "¿Querés que te derive con un agente?")])


def test_i4_habla_del_servicio():
    turns = [T("a", "x"), T("1", "Listo"), T("no puedo hacer llamadas", "Dale, ¿qué hora es?")]
    assert inv.i4_habla_del_servicio(turns, despues_de=1, vocab=inv.VOCAB_MOVIL)
    turns[2] = T("no puedo hacer llamadas", "¿No podés llamar o no te entran?")
    assert not inv.i4_habla_del_servicio(turns, despues_de=1, vocab=inv.VOCAB_MOVIL)
    # cortesía y pedido de agente se excluyen
    assert not inv.i4_habla_del_servicio([T("a"), T("1"), T("gracias", "De nada")], despues_de=1, vocab=inv.VOCAB_MOVIL)


def test_i5_repeticion():
    assert inv.i5_sin_respuestas_repetidas([T("a", "igual"), T("b", "igual")])
    assert not inv.i5_sin_respuestas_repetidas([T("a", "uno"), T("b", "dos")])
    assert not inv.i5_sin_respuestas_repetidas([T("a", "igual"), T("a", "igual")])  # mismo mensaje


def test_i6_ticket_sin_confirmacion():
    solo_diag = [T("no tengo internet", "x", ticket_created=True)]
    assert inv.i6_ticket_con_confirmacion(solo_diag)
    pide = [T("quiero hablar con un agente", "Ticket IBOT-1", ticket_created=True)]
    assert not inv.i6_ticket_con_confirmacion(pide)
    confirma = [T("x", "Para derivar, confirmame con un «sí»."), T("sí", "Ticket", ticket_created=True)]
    assert not inv.i6_ticket_con_confirmacion(confirma)
    sin_prompt = [T("x", "Hola"), T("sí", "Ticket", ticket_created=True)]
    assert inv.i6_ticket_con_confirmacion(sin_prompt)


def test_i11_el_ticket_creado_sigue_ligado_hasta_el_cierre():
    ok = [T("agente", "Ticket", ticket_created=True, ticket_id="IBOT-1", estado="espera_agente", conv_id="c1"),
          T("y?", "ok", ticket_id="IBOT-1", estado="con_agente", conv_id="c1")]
    assert not inv.i11_ticket_ligado_hasta_el_cierre(ok)
    perdido = [ok[0], T("y?", "ok", ticket_id="", estado="bot", conv_id="c1")]
    assert inv.i11_ticket_ligado_hasta_el_cierre(perdido)
    solo_estado = [ok[0], T("y?", "ok", ticket_id="IBOT-1", estado="bot", conv_id="c1")]
    assert inv.i11_ticket_ligado_hasta_el_cierre(solo_estado)
    # otra conversación (reapertura tras el cierre) corta el seguimiento
    reabre = [ok[0], T("internet", "ok", ticket_id="", estado="bot", conv_id="c2")]
    assert not inv.i11_ticket_ligado_hasta_el_cierre(reabre)
    # sin ticket creado en el escenario no hay nada que exigir
    assert not inv.i11_ticket_ligado_hasta_el_cierre([T("x", "y", ticket_id="", estado="bot", conv_id="c1")])


def test_i12_quedate_en_este_chat_solo_con_ticket_ligado():
    assert not inv.i12_quedate_solo_con_ticket_ligado([T("a", "Ticket IBOT-1. Quedate en este chat.", ticket_id="IBOT-1")])
    assert inv.i12_quedate_solo_con_ticket_ligado([T("a", "Ticket IBOT-1. Quedate en este chat.", ticket_id="")])
    assert not inv.i12_quedate_solo_con_ticket_ligado([T("a", "Contame más", ticket_id="")])
