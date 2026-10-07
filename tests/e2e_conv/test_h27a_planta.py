"""H27a: el journey de conectividad con planta válida, vacía, en excepción o sin Radius (secuencia de prod, canal web y app).

Prod (portal): «internet» → la ruta legacy informa la planta (``pppoe_informado``); «no tengo internet» → el journey cortaba en
``canal_pppoe`` sin consultar y decía «No pude obtener el estado de conexión»; después «Ya revisé tu conexión…» ×3 aunque la
revisión no había salido, y el «si» chocaba con «No tengo una acción pendiente de confirmar».

Esperado: el journey reutiliza el resultado del primer sondeo o consulta de verdad («volvé a chequear»); sin estado de planta lo
dice UNA vez y sigue con el playbook de la tecnología (I9); «Ya revisé…» solo tras una revisión exitosa y una sola vez; la oferta de
agente llega al agotar el playbook, termina en «?» y el ticket sale solo con el «sí» (R1).
"""

from __future__ import annotations

import re
from collections import Counter

import pytest

from tests.e2e_conv import invariants as inv
from tests.e2e_conv.harness import PLANTAS, converse

PROD = ["internet", "no tengo internet", "no tengo internet", "si", "internet", "sigue igual", "volve a chequear"]
NO_PUDE_SIN_INTENTAR = "No pude obtener el estado de conexión"
YA_REVISE = "Ya revisé tu conexión en este chat"
SIN_ACCION = "No tengo una acción pendiente de confirmar"
AVISO_PLANTA = "No pude ver el estado de tu conexión desde acá, sigamos con unos chequeos:"
OFERTA = re.compile(r"(querés que te derive|querés que abra (un|el) ticket|¿abro el ticket|derive el caso)", re.I)

H27A = "H27a: el journey corta en canal_pppoe sin consultar («No pude obtener el estado de conexión»), dice «Ya revisé…» sin revisión exitosa y el «si» choca con «No tengo una acción pendiente»"
H27K = "H27k: sesión PPPoE desconocida (None) se informa como caída y se ofrece derivar de entrada"
L_ESPERA = "H27-L1 (fuera de H27a): tras el ticket, espera_agente deja sin respuesta «volvé a chequear» / «ya lo hice» (I1)"
L_ALCANCE = "H27-L2 (fuera de H27a): el legacy repregunta el paso de alcance («¿Te pasa en todos los dispositivos…?») dentro de la ventana de I10"
L_TIPO_ACCESO = "H27-L3 (fuera de H27a): sin journeys y sin tecnología (Radius en excepción) el legacy repite el tipo de acceso (I5/I10)"
L_OFF_VALIDA = "H27-L4 (fuera de H27a): sin journeys y con sesión válida el legacy ofrece la visita técnica de entrada y, tras el «no», cierra y pierde la identificación"


def _casos(xfails: dict[tuple[bool, str], str]):
    return [
        pytest.param(canal, j, planta, marks=[pytest.mark.xfail(strict=True, reason=xfails[(j, planta)])] if (j, planta) in xfails else [],
                     id=f"{canal}-{'on' if j else 'off'}-{planta}")
        for canal in ("web", "app")
        for j in (True, False)
        for planta in PLANTAS
    ]


def _prod(canal, journeys, planta, consultas=None):
    return converse(PROD, canal=canal, profile="fibra_deuda", journeys=journeys, llm="down", planta=planta,
                    consultas_planta=consultas, tecnologia_en_cuenta=True)


def _dump(t) -> str:
    return "\n".join(f"  [{x.branch}] {x.user!r} -> {x.reply[:110]!r}" for x in t)


def tres_identicos(turns) -> list[str]:
    """Ninguna respuesta (no vacía) se repite tres veces en la conversación."""
    c = Counter(x.reply.strip() for x in turns if x.reply.strip())
    return [f"respuesta repetida {n} veces: {r[:90]!r}" for r, n in c.items() if n >= 3]


# ------------------------------------------------ lo que es del journey (H27a)
@pytest.mark.parametrize(("canal", "journeys", "planta"), _casos({
    (True, "valida"): H27A,
    (True, "excepcion"): H27A,
    (True, "vacia"): H27K,
    (True, "sin_radius"): H27K,
    (False, "valida"): L_OFF_VALIDA,
    (False, "excepcion"): L_TIPO_ACCESO,
}))
def test_h27a_sin_cortes_falsos_ni_ya_revise_sin_revision(canal, journeys, planta):
    t = _prod(canal, journeys, planta)
    replies = [x.reply for x in t]
    assert not any(NO_PUDE_SIN_INTENTAR in r for r in replies), _dump(t)
    assert not any(SIN_ACCION in r for r in replies), _dump(t)  # el «si» responde al paso/oferta vigente
    assert sum(YA_REVISE in r for r in replies) <= 1, _dump(t)
    assert sum(AVISO_PLANTA in r for r in replies) <= 1, _dump(t)
    if any(YA_REVISE in r for r in replies):  # solo tras una revisión exitosa
        assert planta == "valida", _dump(t)
    assert not tres_identicos(t), tres_identicos(t) + [_dump(t)]
    v = inv.violaciones(t, solo=("I1", "I5", "I6", "I7", "I11", "I12"))
    assert not v, "\n".join(v) + "\n" + _dump(t)


@pytest.mark.xfail(strict=True, reason=H27A)
@pytest.mark.parametrize(("canal", "planta"), [(c, p) for c in ("web", "app") for p in ("valida", "excepcion")])
def test_h27a_volve_a_chequear_consulta_de_verdad(canal, planta):
    consultas: list[str] = []
    t = converse(PROD[:-1], canal=canal, profile="fibra_deuda", journeys=True, llm="down", planta=planta,
                 consultas_planta=consultas, tecnologia_en_cuenta=True)
    antes = consultas.count("_talvez_mensaje_pppoe")
    consultas.clear()
    t = converse(PROD, canal=canal, profile="fibra_deuda", journeys=True, llm="down", planta=planta,
                 consultas_planta=consultas, tecnologia_en_cuenta=True)
    assert consultas.count("_talvez_mensaje_pppoe") == antes + 1, (antes, consultas, _dump(t))
    assert t[-1].reply and t[-1].reply.strip() != t[1].reply.strip(), _dump(t)


@pytest.mark.xfail(strict=True, reason=H27A)
@pytest.mark.parametrize("canal", ["web", "app"])
def test_h27a_planta_caida_aviso_una_vez_y_sigue_el_playbook(canal):
    t = _prod(canal, True, "excepcion")
    assert t[1].reply.startswith(AVISO_PLANTA) and t[1].reply.rstrip().endswith("?"), _dump(t)  # aviso + próximo paso
    assert not OFERTA.search(t[1].reply), _dump(t)  # I9: quedan pasos, no se ofrece derivar


# ------------------------------------------------ invariantes completos (incluye I10)
@pytest.mark.parametrize(("canal", "journeys", "planta"), _casos({
    (True, "valida"): L_ALCANCE,
    (True, "excepcion"): H27A,
    (True, "vacia"): H27K,
    (True, "sin_radius"): H27K,
    (False, "valida"): L_OFF_VALIDA,
    (False, "excepcion"): L_TIPO_ACCESO,
}))
def test_h27a_secuencia_prod_sin_violaciones(canal, journeys, planta):
    t = _prod(canal, journeys, planta)
    v = inv.violaciones(t, i10=True) + tres_identicos(t)
    assert not v, "\n".join(v) + "\n" + _dump(t)


# ------------------------------------------------ playbook agotado con planta caída: oferta con «?» y ticket solo con «sí»
RELLENO = ["no tengo internet"] + ["sigue igual", "no"] * 8


@pytest.mark.parametrize("perfil", ["fibra_deuda", "int1"])
@pytest.mark.parametrize("canal", ["web", "app"])
def test_h27a_playbook_agotado_ofrece_agente_y_el_si_crea_el_ticket(canal, perfil):
    kw = dict(canal=canal, profile=perfil, journeys=True, llm="down", planta="excepcion", tecnologia_en_cuenta=True)
    t = converse(RELLENO, **kw)
    k = next((i for i, x in enumerate(t) if OFERTA.search(x.reply)), None)
    assert k is not None and k >= 3, _dump(t)  # la oferta llega tras varios pasos, no de entrada (I9)
    assert t[k].reply.rstrip().endswith("?"), _dump(t)  # I7
    assert not any(x.ticket_created for x in t[: k + 1]), _dump(t)  # R1: sin «sí» no hay ticket
    t = converse(RELLENO[: k + 1] + ["sí"], **kw)
    assert OFERTA.search(t[k].reply) and t[-1].ticket_created, _dump(t)
    assert sum(x.ticket_created for x in t) == 1, _dump(t)
    assert not tres_identicos(t[: k + 1]), tres_identicos(t) + [_dump(t)]
    v = inv.violaciones(t, solo=("I1", "I5", "I6", "I7", "I11", "I12"))
    assert not v, "\n".join(v) + "\n" + _dump(t)
