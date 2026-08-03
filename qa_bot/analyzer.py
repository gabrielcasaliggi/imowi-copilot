"""Análisis de respuestas del bot según criterios QA N1."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

TICKET_PATTERNS = [
    r"\bticket\b",
    r"\breclamo\b",
    r"abr[oí].{0,20}(ticket|reclamo|caso)",
    r"abri[oó].{0,20}(ticket|reclamo)",
    r"deriv(o|arte|arte|amos|arte)",
    r"te (paso|paso|paso) con",
    r"operador(a|es)?\b",
    r"agente(s)?\b",
    r"visita t[eé]cnica",
    r"turno de (t[eé]cnico|campo)",
    r"\bN2\b",
    r"escal(o|ar|amiento)",
    r"humano",
]

AUTODIAG_PATTERNS = [
    r"reinici",
    r"desenchuf",
    r"apag[aá]",
    r"prend[eé]",
    r"luces?",
    r"\bPON\b",
    r"\bLOS\b",
    r"\bPoE\b",
    r"router",
    r"\bONT\b",
    r"antena",
    r"m[oó]dem",
    r"modo avi[oó]n",
    r"\bAPN\b",
    r"datos m[oó]viles",
    r"\bQR\b",
    r"Fiserv",
    r"Mercado Pago",
    r"\bMODO\b",
    r"cable amarillo",
    r"fibra",
    r"test",
    r"fast\.com",
    r"2\.4",
    r"5\s*GHz",
    r"microfiltro",
    r"splitter",
]

RESOLUCION_DIRECTA_PATTERNS = [
    r"pod[eé]s pagar",
    r"QR",
    r"batan\.coop",
    r"se reactiva",
    r"APN",
    r"internet\.coopbatan",
    r"instrucci",
    r"paso a paso",
    r"para ver (saldo|factura)",
    r"DNI",
    r"n[uú]mero de socio",
]

IDENT_PATTERNS = [
    r"\bDNI\b",
    r"identific",
    r"modo invitado",
    r"n[uú]mero de socio",
    r"padr[oó]n",
]

MENU_PATTERNS = [
    r"internet",
    r"m[oó]vil",
    r"factura",
    r"en qu[eé] (te |podemos )?ayud",
    r"contame",
    r"qu[eé] tipo",
    r"fibra|antena|ADSL",
]


def _match_any(text: str, patterns: list[str]) -> list[str]:
    hits: list[str] = []
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            hits.append(p)
    return hits


@dataclass
class AnalisisTurno:
    usuario: str
    respuesta: str
    resolvio_en_chat: bool
    instruyo_autodiagnostico: bool
    derivo_ticket: bool
    ticket_prematuro: bool
    falla_comprension: bool
    posible_bucle: bool
    pidio_identificacion: bool
    latency_ms: int | None = None
    hallazgos: list[str] = field(default_factory=list)
    score_n1: float = 0.0  # 0..1


@dataclass
class AnalisisEscenario:
    escenario_id: str
    nombre: str
    categoria: str
    turnos: list[AnalisisTurno]
    resolutivo_autonomo: bool
    ticket_creado_o_ofrecido: bool
    ticket_prematuro: bool
    bucle_detectado: bool
    falla_comprension: bool
    score_n1: float
    resumen_fallas: list[str] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)


def analizar_turno(
    usuario: str,
    respuesta: str,
    *,
    espera_autodiagnostico: bool = False,
    espera_resolucion_directa: bool = False,
    no_debe_ticket_prematuro: bool = True,
    ticket_aceptable: bool = False,
    respuestas_previas: list[str] | None = None,
    latency_ms: int | None = None,
) -> AnalisisTurno:
    resp = (respuesta or "").strip()
    prev = respuestas_previas or []

    ticket_hits = _match_any(resp, TICKET_PATTERNS)
    autodiag_hits = _match_any(resp, AUTODIAG_PATTERNS)
    resol_hits = _match_any(resp, RESOLUCION_DIRECTA_PATTERNS)
    ident_hits = _match_any(resp, IDENT_PATTERNS)
    menu_hits = _match_any(resp, MENU_PATTERNS)

    derivo = bool(ticket_hits)
    autodiag = bool(autodiag_hits)
    resolvio = bool(resol_hits) or (autodiag and not derivo) or (
        bool(menu_hits) and not derivo and len(resp) > 40
    )
    pidio_id = bool(ident_hits)

    # Bucle: respuesta casi idéntica a la anterior
    bucle = False
    if prev:
        last = prev[-1].strip().lower()
        cur = resp.lower()
        if last and cur:
            if last == cur:
                bucle = True
            elif len(cur) > 40 and (cur in last or last in cur):
                bucle = True
            # misma pregunta clave repetida 2+ veces
            q = re.findall(r"[¿?]([^¿?]{12,80})[¿?]?", cur)
            if q and any(q[0].lower() in p.lower() for p in prev[-2:]):
                bucle = True

    # Comprensión: respuesta vacía, genérica corta, o "no entiendo" + nada útil
    falla = False
    low = resp.lower()
    if not resp or len(resp) < 15:
        falla = True
    if re.search(r"no (te )?entend[ií]|no comprendo|no s[eé] a qu[eé]", low) and not autodiag:
        falla = True
    if re.search(r"error|fall[oó] interno|timeout|intentalo m[aá]s tarde", low):
        falla = True

    prematuro = bool(derivo and no_debe_ticket_prematuro and not ticket_aceptable)

    hallazgos: list[str] = []
    if prematuro:
        hallazgos.append("Derivación/ticket prematuro sin agotar N1")
    if espera_autodiagnostico and not autodiag and not derivo:
        # menú/triaje también cuenta como avance N1
        if not menu_hits:
            hallazgos.append("No ofreció pasos de autodiagnóstico esperados")
    if espera_resolucion_directa and not resolvio and not autodiag:
        hallazgos.append("No resolvió/instruyó de forma directa")
    if bucle:
        hallazgos.append("Posible bucle o respuesta repetida")
    if falla:
        hallazgos.append("Posible falla de comprensión o respuesta inválida")
    if ticket_aceptable and not derivo and "ticket" not in low and "deriv" not in low:
        # no es falla dura: a veces sigue N1 un paso más
        pass

    # Score N1 del turno
    score = 1.0
    if prematuro:
        score -= 0.6
    if falla:
        score -= 0.4
    if bucle:
        score -= 0.3
    if espera_autodiagnostico and not (autodiag or menu_hits):
        score -= 0.25
    if derivo and ticket_aceptable:
        score = max(score, 0.85)  # handoff legítimo
    score = max(0.0, min(1.0, score))

    return AnalisisTurno(
        usuario=usuario,
        respuesta=resp,
        resolvio_en_chat=resolvio and not prematuro,
        instruyo_autodiagnostico=autodiag or bool(menu_hits and espera_autodiagnostico),
        derivo_ticket=derivo,
        ticket_prematuro=prematuro,
        falla_comprension=falla,
        posible_bucle=bucle,
        pidio_identificacion=pidio_id,
        latency_ms=latency_ms,
        hallazgos=hallazgos,
        score_n1=score,
    )


def analizar_escenario(
    escenario_id: str,
    nombre: str,
    categoria: str,
    analisis_turnos: list[AnalisisTurno],
    *,
    resolucion_n1_esperada: bool,
) -> AnalisisEscenario:
    ticket_any = any(t.derivo_ticket for t in analisis_turnos)
    prematuro = any(t.ticket_prematuro for t in analisis_turnos)
    bucle = any(t.posible_bucle for t in analisis_turnos)
    falla = any(t.falla_comprension for t in analisis_turnos)
    scores = [t.score_n1 for t in analisis_turnos] or [0.0]
    score = sum(scores) / len(scores)

    # Resolutivo autónomo: avanzó N1 sin ticket prematuro; si no se esperaba resolución,
    # cuenta como OK si el handoff no fue prematuro.
    if resolucion_n1_esperada:
        resolutivo = (not prematuro) and (not falla) and score >= 0.55 and (
            any(t.instruyo_autodiagnostico or t.resolvio_en_chat for t in analisis_turnos)
        )
    else:
        resolutivo = (not prematuro) and (not falla) and score >= 0.5

    fallas: list[str] = []
    for i, t in enumerate(analisis_turnos, 1):
        for h in t.hallazgos:
            fallas.append(f"T{i}: {h}")

    transcript = [
        {"rol": "usuario", "texto": t.usuario}
        if False
        else None
        for t in analisis_turnos
    ]
    # build proper transcript
    transcript = []
    for t in analisis_turnos:
        transcript.append({"rol": "usuario", "texto": t.usuario})
        transcript.append({"rol": "bot", "texto": t.respuesta})

    return AnalisisEscenario(
        escenario_id=escenario_id,
        nombre=nombre,
        categoria=categoria,
        turnos=analisis_turnos,
        resolutivo_autonomo=resolutivo,
        ticket_creado_o_ofrecido=ticket_any,
        ticket_prematuro=prematuro,
        bucle_detectado=bucle,
        falla_comprension=falla,
        score_n1=round(score, 3),
        resumen_fallas=fallas,
        transcript=transcript,
    )
