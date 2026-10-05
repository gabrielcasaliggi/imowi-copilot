"""Invariantes conversacionales verificables turno a turno (I1–I9)."""

from __future__ import annotations

import re

from tests.e2e_conv.harness import Turn

COURTESY = re.compile(
    r"^\s*(muchas\s+)?gracias[!. ]*$|^\s*(ok|oka|dale|listo|perfecto|genial|de nada)[!. ]*$", re.I
)
USER_GREETS = re.compile(r"^\s*(hola|buen[ao]s?(\s+(d[ií]as|tardes|noches))?|hey|holi)\b", re.I)
GENERIC_WELCOME = re.compile(
    r"(soy (eko|eco)\b|asistente virtual|te identifiqué correctamente|en qué te (ayudo|puedo ayudar)|"
    r"tu consulta es por)",
    re.I,
)
USER_ASKS_AGENT = re.compile(
    r"(hablar con (un |una )?(agente|persona|operador|humano|alguien)|quiero (un|una) (agente|persona|operador)|"
    r"pasame con (un )?(agente|operador))",
    re.I,
)
HANDOFF_REPLY = re.compile(
    r"(te derivo|derivar con un agente|derive el caso|confirmame con un|confirmás que querés continuar con esta acción|"
    r"ticket [a-z]+-\d+|ya está derivado|te paso con un agente)",
    re.I,
)
AFFIRM = re.compile(r"^\s*(s[ií]|dale|ok|confirmo|sí,? por favor|si por favor)\b", re.I)
CONFIRM_PROMPT = re.compile(
    r"(confirmame con un|querés que te derive|¿te derivo|¿confirmás|¿abro el ticket|derive el caso|continuar con esta acción)", re.I
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def i1_sin_respuesta_vacia(turns: list[Turn]) -> list[str]:
    return [
        f"I1 turno {i} ({t.user!r}): respuesta vacía [{t.branch}]"
        for i, t in enumerate(turns)
        if not t.reply and not COURTESY.match(t.user)
    ]


def i2_sin_saludo_generico(turns: list[Turn]) -> list[str]:
    out = []
    for i, t in enumerate(turns):
        if i == 0 or USER_GREETS.match(t.user):
            continue
        if GENERIC_WELCOME.search(t.reply):
            out.append(f"I2 turno {i} ({t.user!r}): saludo/menú genérico a mitad de conversación: {t.reply[:80]!r}")
    return out


def i3_agente_deriva(turns: list[Turn]) -> list[str]:
    return [
        f"I3 turno {i} ({t.user!r}): pidió agente y no se derivó ni se pidió confirmación: {t.reply[:80]!r} [{t.branch}]"
        for i, t in enumerate(turns)
        if USER_ASKS_AGENT.search(t.user) and not HANDOFF_REPLY.search(t.reply)
    ]


def i4_habla_del_servicio(
    turns: list[Turn], *, despues_de: int, vocab: re.Pattern[str], etiquetas: tuple[str, ...] = ()
) -> list[str]:
    out = []
    for i, t in enumerate(turns):
        if i <= despues_de or COURTESY.match(t.user) or USER_ASKS_AGENT.search(t.user) or AFFIRM.match(t.user):
            continue
        r = t.reply
        if not (vocab.search(r) or any(e.lower() in r.lower() for e in etiquetas)):
            out.append(f"I4 turno {i} ({t.user!r}): no habla del servicio elegido: {r[:90]!r} [{t.branch}]")
    return out


def i5_sin_respuestas_repetidas(turns: list[Turn]) -> list[str]:
    out = []
    for i in range(1, len(turns)):
        a, b = turns[i - 1], turns[i]
        if b.reply and _norm(a.reply) == _norm(b.reply) and _norm(a.user) != _norm(b.user):
            out.append(f"I5 turno {i} ({b.user!r}): repite la respuesta anterior: {b.reply[:80]!r}")
    return out


def i6_ticket_con_confirmacion(turns: list[Turn]) -> list[str]:
    out = []
    for i, t in enumerate(turns):
        if not t.ticket_created:
            continue
        prev_bot = turns[i - 1].reply if i else ""
        explicito = bool(USER_ASKS_AGENT.search(t.user))
        confirma = bool(AFFIRM.match(t.user)) and bool(CONFIRM_PROMPT.search(prev_bot))
        if not (explicito or confirma):
            out.append(f"I6 turno {i} ({t.user!r}): ticket creado sin pedido ni confirmación explícita [{t.branch}]")
    return out


def i7_oferta_termina_en_pregunta(turns: list[Turn]) -> list[str]:
    """Toda respuesta que deja una oferta pendiente de confirmación (derivar, ticket) termina con una pregunta."""
    out = []
    for i, t in enumerate(turns):
        if not t.pending_offer:
            continue
        ultimo = (t.replies[-1] if t.replies else "").strip()
        if not ultimo.endswith("?"):
            out.append(f"I7 turno {i} ({t.user!r}): oferta pendiente ({t.pending_offer}) sin pregunta final: {ultimo[-90:]!r} [{t.branch}]")
    return out


OTRO_DOMINIO_FIJO = re.compile(r"(wi-?\s?fi|router|equipos|\bont\b|fibra|acceso a la red)", re.I)


def i8_sin_vocabulario_de_internet_fijo(turns: list[Turn]) -> list[str]:
    """En una conversación de servicio móvil/Sensa/TV ninguna respuesta habla de Internet fijo (Wi-Fi, router, equipos, ONT, fibra,
    «acceso a la red»). Solo se evalúa cuando el escenario declara el foco con ``servicio_sin_internet_fijo=True``."""
    return [
        f"I8 turno {i} ({t.user!r}): vocabulario de Internet fijo en un servicio móvil/Sensa/TV: {m.group(0)!r} en {r[:90]!r} [{t.branch}]"
        for i, t in enumerate(turns)
        for r in t.replies
        if (m := OTRO_DOMINIO_FIJO.search(r))
    ]


OFERTA_DERIVAR = re.compile(r"(te derivo|que te derive|derivar con|te paso con un agente|derive el caso)", re.I)


def i9_no_ofrece_derivar_con_pasos_sin_preguntar(turns: list[Turn], pasos: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    """En servicios con playbook propio no se ofrece derivar mientras quede un paso sin preguntar (``pasos``: id y patrón de
    su pregunta). Excepciones: pedido explícito de agente del abonado, planta/óptica y pack_acreditado_sin_datos (esos
    escenarios no pasan ``pasos``)."""
    out = []
    for i, t in enumerate(turns):
        if not (CONFIRM_PROMPT.search(t.reply) or OFERTA_DERIVAR.search(t.reply)) or any(USER_ASKS_AGENT.search(x.user) for x in turns[: i + 1]):
            continue
        antes = " ".join(r for x in turns[:i] for r in x.replies)
        faltan = [pid for pid, rx in pasos if not rx.search(antes)]
        if faltan:
            out.append(f"I9 turno {i} ({t.user!r}): ofrece derivar sin haber preguntado {faltan}: {t.reply[:80]!r} [{t.branch}]")
    return out


def violaciones(
    turns: list[Turn], *, servicio: tuple[int, re.Pattern[str], tuple[str, ...]] | None = None,
    solo: tuple[str, ...] | None = None, servicio_sin_internet_fijo: bool = False,
    pasos_antes_de_derivar: list[tuple[str, re.Pattern[str]]] | None = None,
) -> list[str]:
    checks = {
        "I1": i1_sin_respuesta_vacia(turns),
        "I2": i2_sin_saludo_generico(turns),
        "I3": i3_agente_deriva(turns),
        "I5": i5_sin_respuestas_repetidas(turns),
        "I6": i6_ticket_con_confirmacion(turns),
        "I7": i7_oferta_termina_en_pregunta(turns),
    }
    if servicio is not None:
        checks["I4"] = i4_habla_del_servicio(turns, despues_de=servicio[0], vocab=servicio[1], etiquetas=servicio[2])
    if servicio_sin_internet_fijo:
        checks["I8"] = i8_sin_vocabulario_de_internet_fijo(turns)
    if pasos_antes_de_derivar:
        checks["I9"] = i9_no_ofrece_derivar_con_pasos_sin_preguntar(turns, pasos_antes_de_derivar)
    out: list[str] = []
    for k, v in checks.items():
        if solo is None or k in solo:
            out += v
    errs = [f"ERROR turno {i}: {t.error}" for i, t in enumerate(turns) if t.error]
    return errs + out


VOCAB_MOVIL = re.compile(r"(llam|datos|señal|línea|linea|móvil|movil|imowi|apn|modo avión|reinici|chip|sim\b)", re.I)
VOCAB_INTERNET = re.compile(
    r"(internet|wi-?fi|router|módem|modem|conexión|conexion|fibra|antena|luz|cable|dispositivo|poe|equipo|ont|sesión|cuenta)",
    re.I,
)
VOCAB_TV = re.compile(r"(sensa|tele|\btv\b|decodificador|canales)", re.I)
