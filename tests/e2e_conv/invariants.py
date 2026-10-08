"""Invariantes conversacionales verificables turno a turno (I1–I12)."""

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
    r"(te derivo|derivar con un agente|derive el caso|confirmame con un|querés que te (derive|pase) con un agente|"
    r"ticket [a-z]+-\d+|ya está derivado|te paso con un agente)",
    re.I,
)
AFFIRM = re.compile(r"^\s*(s[ií]|dale|ok|confirmo|sí,? por favor|si por favor)\b", re.I)
CONFIRM_PROMPT = re.compile(
    r"(confirmame con un|querés que te derive|¿te derivo|¿confirmás|¿abro el ticket|querés que abra (un|el) ticket|derive el caso|"
    r"continuar con esta acción)", re.I
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


OTRO_DOMINIO_MOVIL = re.compile(r"(\bsms\b|llamadas?|\bapn\b|modo avi[oó]n|l[ií]nea m[oó]vil|\bsim\b|datos m[oó]viles)", re.I)


def i8_sin_vocabulario_movil_en_internet(turns: list[Turn]) -> list[str]:
    """Espejo de I8: en una conversación de Internet fijo no aparecen SMS, llamadas, APN, modo avión ni línea móvil.
    Solo se evalúa cuando el escenario declara ``servicio_solo_internet=True``."""
    return [
        f"I8i turno {i} ({t.user!r}): vocabulario móvil en una conversación de Internet: {m.group(0)!r} en {r[:90]!r} [{t.branch}]"
        for i, t in enumerate(turns)
        for r in t.replies
        if (m := OTRO_DOMINIO_MOVIL.search(r))
    ]


REPREGUNTA_EXPLICITA = re.compile(r"(repet[ií]|no entend|qu[eé]\s*\?|c[oó]mo\??$|otra vez|de nuevo)", re.I)


def i10_no_repite_paso_ya_preguntado(turns: list[Turn], ventana: int = 6) -> list[str]:
    """I10: el bot no repite una pregunta de paso ya hecha en los últimos ``ventana`` turnos (I5 cubre el turno consecutivo),
    salvo repregunta explícita del abonado o una repregunta por respuesta no reconocida («No te entendí…»)."""
    out = []
    for i, t in enumerate(turns):
        r = _norm(t.reply)
        if not r or not r.endswith("?") or r.startswith("no te entend") or REPREGUNTA_EXPLICITA.search(t.user):
            continue
        for j in range(max(0, i - ventana), i - 1):  # i-1 lo cubre I5
            if _norm(turns[j].reply) == r and _norm(turns[j].user) != _norm(t.user):
                out.append(f"I10 turno {i} ({t.user!r}): repite la pregunta del turno {j}: {t.reply[:80]!r} [{t.branch}]")
                break
    return out


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


def i11_ticket_ligado_hasta_el_cierre(turns: list[Turn]) -> list[str]:
    """I11: en cada turno posterior a la creación de un ticket, la conversación que lo creó mantiene el ``ticket_id`` y sigue en
    ``espera_agente`` o ``con_agente``. El seguimiento termina cuando el abonado vuelve en otra conversación (el hilo se cerró
    con el ticket, ver ``cierra_el_ticket_desde_el_panel``) y se reinicia si esa conversación crea otro ticket."""
    out = []
    ligado: tuple[str, str] | None = None  # (conv_id, ticket_id) del último ticket creado
    for i, t in enumerate(turns):
        if t.ticket_created:
            ligado = (t.conv_id, t.ticket_id)
            continue
        if ligado is None or t.conv_id != ligado[0]:
            ligado = None
            continue
        if t.ticket_id != ligado[1] or t.estado not in ("espera_agente", "con_agente"):
            out.append(
                f"I11 turno {i} ({t.user!r}): la conversación perdió el ticket {ligado[1]} "
                f"(ticket_id={t.ticket_id!r}, estado={t.estado!r}) [{t.branch}]"
            )
    return out


QUEDATE_EN_EL_CHAT = re.compile(r"quedate en este chat", re.I)


def i12_quedate_solo_con_ticket_ligado(turns: list[Turn]) -> list[str]:
    """I12: «Quedate en este chat» solo si el ticket quedó ligado a la conversación (``ticket_id`` no vacío tras el turno)."""
    return [
        f"I12 turno {i} ({t.user!r}): promete «Quedate en este chat» sin ticket ligado a la conversación: {t.reply[-90:]!r} [{t.branch}]"
        for i, t in enumerate(turns)
        if QUEDATE_EN_EL_CHAT.search(t.reply) and not t.ticket_id
    ]


def violaciones(
    turns: list[Turn], *, servicio: tuple[int, re.Pattern[str], tuple[str, ...]] | None = None,
    solo: tuple[str, ...] | None = None, servicio_sin_internet_fijo: bool = False,
    pasos_antes_de_derivar: list[tuple[str, re.Pattern[str]]] | None = None,
    servicio_solo_internet: bool = False,
    i10: bool = False,
) -> list[str]:
    checks = {
        "I1": i1_sin_respuesta_vacia(turns),
        "I2": i2_sin_saludo_generico(turns),
        "I3": i3_agente_deriva(turns),
        "I5": i5_sin_respuestas_repetidas(turns),
        "I6": i6_ticket_con_confirmacion(turns),
        "I7": i7_oferta_termina_en_pregunta(turns),
        "I11": i11_ticket_ligado_hasta_el_cierre(turns),
        "I12": i12_quedate_solo_con_ticket_ligado(turns),
    }
    if servicio is not None:
        checks["I4"] = i4_habla_del_servicio(turns, despues_de=servicio[0], vocab=servicio[1], etiquetas=servicio[2])
    if servicio_sin_internet_fijo:
        checks["I8"] = i8_sin_vocabulario_de_internet_fijo(turns)
    if i10:
        checks["I10"] = i10_no_repite_paso_ya_preguntado(turns)
    if servicio_solo_internet:
        checks["I8i"] = i8_sin_vocabulario_movil_en_internet(turns)
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
