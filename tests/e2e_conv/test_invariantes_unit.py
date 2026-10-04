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
    assert not inv.i3_agente_deriva([T("quiero hablar con un agente", "¿Confirmás que querés continuar con esta acción?")])


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
