"""H27g: copy de confirmaciones que nombran la acción y consulta de ticket con ID y estado real (Fix 4 de H22 ampliado).

Solo copy y reconocimiento de frases: no cambia cuándo se crea un ticket (R1) ni la lógica de decisión.
"""

from __future__ import annotations

import re

import pytest

from tests.e2e_conv import agente
from tests.e2e_conv import invariants as inv
from tests.e2e_conv.harness import converse

CANALES = ["whatsapp", "web"]
DERIVAR_ACCION = "¿Querés que te derive con un agente?"
CONSULTAS = ["y el ticket?", "el ticket", "mi ticket", "qué pasó con el ticket", "qué pasó con mi ticket", "cómo va el ticket",
             "cómo va mi ticket", "número de ticket", "cuál es mi ticket", "y el ticket anterior?", "ticket?"]
NO_CONSULTAS = ["quiero abrir un ticket", "no quiero ticket", "abrime un ticket", "necesito un ticket", "ticket pls"]
ESTADO = re.compile(r"(abierto|en curso|en espera|derivado|asignado|cerrado)", re.I)
OFRECE_DERIVAR = re.compile(r"(querés que te derive|te derivo|derivar con|confirmame con un|abro el ticket)", re.I)
PLAYBOOK = re.compile(r"(router|reinici|dispositivos|wi-?fi|cable|luces|ONT)", re.I)
SIN_TICKET = "No tenés ningún ticket abierto"
COPY_ACTIVO = "un agente lo va a atender. Te responde por este mismo chat."


def _dump(t) -> str:
    return "\n".join(f"  [{x.branch}] {x.user!r} -> {x.reply[:120]!r}" for x in t)


# ------------------------------------------------ pieza 1: la confirmación de create_ticket nombra la acción
@pytest.mark.parametrize("canal", CANALES)
def test_h27g_pedido_de_agente_confirma_nombrando_la_accion(canal):
    t = converse(["internet", "¿me pasás con un agente?"], canal=canal, planta="valida")
    assert t[1].reply == DERIVAR_ACCION and not t[1].ticket_created, _dump(t)
    v = inv.violaciones(t, solo=("I1", "I3", "I6", "I7"))
    assert not v, "\n".join(v) + "\n" + _dump(t)


@pytest.mark.parametrize("canal", CANALES)
def test_h27g_el_si_a_la_confirmacion_crea_el_ticket(canal):
    t = converse(["internet", "¿me pasás con un agente?", "sí"], canal=canal, planta="valida")
    assert t[1].reply == DERIVAR_ACCION and t[2].ticket_created, _dump(t)
    assert sum(x.ticket_created for x in t) == 1, _dump(t)


@pytest.mark.parametrize("canal", CANALES)
def test_h27g_el_no_a_la_confirmacion_no_crea_ticket(canal):
    t = converse(["internet", "¿me pasás con un agente?", "no"], canal=canal, planta="valida")
    assert t[1].reply == DERIVAR_ACCION, _dump(t)
    assert not any(x.ticket_created for x in t), _dump(t)


# ------------------------------------------------ pieza 2: consulta de ticket
def test_h27g_detector_reconoce_las_consultas():
    from app.services.canal_abonado import _es_consulta_de_ticket

    assert [c for c in CONSULTAS if not _es_consulta_de_ticket(c)] == []


def test_h27g_detector_no_toma_pedidos_de_ticket():
    from app.services.canal_abonado import _es_consulta_de_ticket

    assert [c for c in NO_CONSULTAS if _es_consulta_de_ticket(c)] == []


@pytest.mark.parametrize("consulta", CONSULTAS)
@pytest.mark.parametrize("canal", CANALES)
def test_h27g_consulta_con_ticket_abierto_responde_id_y_estado(canal, consulta):
    t = converse(["no tengo internet", "quiero hablar con un agente", consulta], canal=canal, profile="int1")
    tid = t[1].ticket_id
    assert tid and t[1].ticket_created, _dump(t)
    r = t[2].reply
    assert tid in r and ESTADO.search(r) and not OFRECE_DERIVAR.search(r) and not PLAYBOOK.search(r), _dump(t)
    assert not t[2].ticket_created and t[2].ticket_id == tid, _dump(t)


@pytest.mark.parametrize("consulta", CONSULTAS)
def test_h27g_consulta_con_ticket_previo_cerrado_y_uno_nuevo(consulta):
    t = converse(["internet", "me pasas con un agente", agente.cierra_el_ticket_desde_el_panel, "internet", "me pasas con un agente",
                  consulta], canal="whatsapp", profile="int1", reconocer_telefono=True)
    viejo, nuevo = t[1].ticket_id, t[3].ticket_id
    assert viejo and nuevo and viejo != nuevo, _dump(t)
    r = t[4].reply
    assert viejo in r and re.search(r"ya fue cerrado", r) and nuevo in r and not OFRECE_DERIVAR.search(r), _dump(t)
    assert not t[4].ticket_created, _dump(t)


@pytest.mark.parametrize("consulta", CONSULTAS)
def test_h27g_consulta_con_ticket_previo_cerrado_sin_nuevo(consulta):
    t = converse(["internet", "me pasas con un agente", agente.cierra_el_ticket_desde_el_panel, "internet", consulta],
                 canal="whatsapp", profile="int1", reconocer_telefono=True)
    viejo = t[1].ticket_id
    r = t[3].reply
    assert viejo in r and "ya fue cerrado" in r and SIN_TICKET in r and r.rstrip().endswith("?"), _dump(t)
    assert not any(x.ticket_created for x in t[2:]), _dump(t)


@pytest.mark.parametrize("consulta", CONSULTAS)
@pytest.mark.parametrize("journeys", [True, False], ids=["journeys_on", "journeys_off"])
def test_h27g_consulta_sin_ticket_responde_honesto(consulta, journeys):
    t = converse(["internet", consulta], canal="web", profile="int1", journeys=journeys)
    r = t[1].reply
    assert r.startswith(SIN_TICKET) and r.rstrip().endswith("?") and not re.search(r"IBOT-\d+", r), _dump(t)
    assert not any(x.ticket_created for x in t), _dump(t)
    assert not inv.violaciones(t, solo=("I1", "I6", "I7")), inv.violaciones(t, solo=("I1", "I6", "I7"))


@pytest.mark.parametrize("texto", NO_CONSULTAS)
def test_h27g_un_pedido_de_ticket_no_se_responde_como_consulta(texto):
    t = converse(["internet", texto], canal="web", profile="int1")
    assert SIN_TICKET not in t[1].reply and COPY_ACTIVO not in t[1].reply, _dump(t)
    t = converse(["no tengo internet", "quiero hablar con un agente", texto], canal="web", profile="int1")
    assert COPY_ACTIVO not in t[2].reply and not t[2].ticket_created, _dump(t)
