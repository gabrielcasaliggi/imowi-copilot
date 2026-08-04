"""Diagnóstico N1 dirigido por IA — el playbook es checklist, no guión rígido."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.domain.flujos_abonado import PasoPlaybook

logger = logging.getLogger("operations_hub")

# Intenciones donde la IA diagnostica como técnico (playbook = guía).
INTENCIONES_DIAGNOSTICO = frozenset({
    "internet",
    "internet_ftth",
    "internet_adsl",
    "internet_radio",
    "internet_lento",
    "wifi",
    "movil",
    "movil_datos",
    "movil_llamadas",
    "telefono_fija",
    "no_tecnico",
    "ecolan_b2b",
    "facturacion",
})

MIN_TURNOS_ANTES_ESCALAR = 4

_AFIRMACIONES = (
    "si",
    "sí",
    "sip",
    "correcto",
    "exacto",
    "afirmativo",
    "tal cual",
    "claro",
    "eso",
    "asi es",
    "así es",
    "confirmo",
)

_DANO_FIBRA = (
    "daño",
    "dano",
    "dañado",
    "danado",
    "roto",
    "rota",
    "partido",
    "cortado",
    "quebrado",
    "doblado",
    "quemado",
    "rajado",
    "fisura",
    "roto el cable",
    "cable roto",
)

_WIFI_MARKERS = (
    "wifi",
    "wi-fi",
    "wi fi",
    "por cable",
    "cable directo",
    "saturación",
    "saturacion",
    "canal",
    "solo wifi",
)


def es_intencion_diagnostico(intencion: str) -> bool:
    return (intencion or "").strip() in INTENCIONES_DIAGNOSTICO


def _autor_texto(m: Any) -> tuple[str, str]:
    autor = getattr(m, "autor", None) or (m.get("autor") if isinstance(m, dict) else "")
    texto = getattr(m, "texto", None) or (m.get("texto") if isinstance(m, dict) else "")
    if not texto and isinstance(m, dict):
        texto = m.get("contenido") or m.get("mensaje") or ""
    return str(autor or ""), str(texto or "")


def _es_afirmacion(texto: str) -> bool:
    t = (texto or "").lower().strip()
    if not t:
        return False
    if any(k in t for k in ("luz roja", "roja", "encendida", "prendida", "sigue")):
        # "tengo una luz roja" / "sigue en rojo" cuenta como evidencia óptica
        if any(k in t for k in ("roja", "rojo", "los", "pon")):
            return True
    if t in _AFIRMACIONES:
        return True
    return any(t == a or t.startswith(a + " ") or t.startswith(a + ",") for a in _AFIRMACIONES)


def _bot_menciona_los(texto: str) -> bool:
    t = texto or ""
    tl = t.lower()
    if "LOS" in t:
        return True
    return any(
        k in tl
        for k in (
            "luz los",
            "la los",
            "led los",
            "los'",
            "'los",
            "los en",
            "los apagada",
            "los prendida",
            "pon está",
            "pon esta",
        )
    )


def _bot_pregunta_fibra(texto: str) -> bool:
    tl = (texto or "").lower()
    return any(
        k in tl
        for k in (
            "fibra",
            "cable amarillo",
            "dobleces",
            "daños visibles",
            "danos visibles",
            "enchufado en la ont",
            "cable de fibra",
        )
    )


def _tiene_dano_fibra(texto: str) -> bool:
    tl = (texto or "").lower()
    return any(k in tl for k in _DANO_FIBRA)


def detectar_falla_optica_escalar(
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None,
) -> str | None:
    """Si hay LOS confirmada + chequeo de fibra (o fibra dañada), hay que escalar.

    No seguir con WiFi / saturación de canal: es capa óptica.
    """
    parts = [_autor_texto(m) for m in (historial_mensajes or [])]
    last = (mensaje_cliente or "").strip()
    if last and (not parts or parts[-1][1].strip() != last):
        parts.append(("cliente", last))
    recent = parts[-14:]
    if not recent:
        return None

    bot_hablo_los = False
    cliente_confirmo_los = False
    bot_pregunto_fibra = False
    for i, (autor, texto) in enumerate(recent):
        if autor == "bot" and _bot_menciona_los(texto):
            bot_hablo_los = True
            for autor2, texto2 in recent[i + 1 :]:
                if autor2 == "cliente":
                    if _es_afirmacion(texto2) or _bot_menciona_los(texto2) or "roja" in texto2.lower():
                        cliente_confirmo_los = True
                    break
        if autor == "bot" and _bot_pregunta_fibra(texto):
            bot_pregunto_fibra = True

    last_l = last.lower()
    dano = _tiene_dano_fibra(last_l)
    cliente_dice_los = any(
        k in last_l
        for k in (
            "luz los",
            "los roja",
            "los en rojo",
            "tengo los",
            "led los",
            "la los",
            "roja de los",
            "rojo de los",
            "luz de los",
        )
    ) or (
        "los" in last_l
        and any(k in last_l for k in ("roja", "rojo", "luz"))
    )

    if dano and (bot_pregunto_fibra or bot_hablo_los or cliente_confirmo_los):
        return "fibra_danada"
    if cliente_confirmo_los and bot_pregunto_fibra and last:
        return "los_con_chequeo_fibra"
    if cliente_dice_los and dano:
        return "los_y_fibra_danada"
    if cliente_confirmo_los and dano:
        return "los_y_fibra_danada"
    if cliente_dice_los:
        # Declaró LOS en rojo: visita técnica (no seguir a WiFi)
        return "los_confirmada"
    return None


def los_confirmada_en_historial(
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None,
) -> bool:
    """True si el cliente ya confirmó LOS / luz óptica en rojo."""
    if detectar_falla_optica_escalar(mensaje_cliente, historial_mensajes):
        return True
    parts = [_autor_texto(m) for m in (historial_mensajes or [])]
    last = (mensaje_cliente or "").strip()
    if last and (not parts or parts[-1][1].strip() != last):
        parts.append(("cliente", last))
    recent = parts[-14:]
    for i, (autor, texto) in enumerate(recent):
        if autor == "bot" and _bot_menciona_los(texto):
            for autor2, texto2 in recent[i + 1 :]:
                if autor2 == "cliente":
                    if _es_afirmacion(texto2) or "roja" in (texto2 or "").lower():
                        return True
                    break
    last_l = last.lower()
    return any(
        k in last_l
        for k in ("luz los", "los roja", "los en rojo", "tengo los", "led los")
    )


def _extract_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Respuesta vacía")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("JSON inválido")
        data = json.loads(raw[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON raíz debe ser objeto")
    return data


def _historial_texto(mensajes: list[Any], *, limit: int = 16) -> str:
    lines: list[str] = []
    for m in (mensajes or [])[-limit:]:
        autor = getattr(m, "autor", None) or (m.get("autor") if isinstance(m, dict) else "x")
        texto = getattr(m, "texto", None) or (m.get("texto") if isinstance(m, dict) else "")
        rol = "Cliente" if autor == "cliente" else ("Eco" if autor == "bot" else str(autor))
        t = (texto or "").strip()
        if t:
            lines.append(f"{rol}: {t[:400]}")
    return "\n".join(lines) if lines else "(sin historial)"


def _checklist_texto(pasos: list[PasoPlaybook] | list[dict], cubiertos: list[str]) -> str:
    done = set(cubiertos or [])
    rows: list[str] = []
    for p in pasos or []:
        if isinstance(p, PasoPlaybook):
            pid, preg = p.id, p.pregunta
        elif isinstance(p, dict):
            pid = str(p.get("id") or "")
            preg = str(p.get("pregunta") or "")
        else:
            continue
        mark = "x" if pid in done else " "
        rows.append(f"- [{mark}] {pid}: {preg}")
    return "\n".join(rows) if rows else "(sin checklist)"


def _fallback_ask(
    pasos: list[PasoPlaybook] | list[dict],
    cubiertos: list[str],
    mensaje_cliente: str,
    *,
    saltar_wifi: bool = False,
) -> dict[str, str]:
    done = set(cubiertos or [])
    for p in pasos or []:
        if isinstance(p, PasoPlaybook):
            pid, preg = p.id, p.pregunta
        elif isinstance(p, dict):
            pid = str(p.get("id") or "paso")
            preg = str(p.get("pregunta") or "")
        else:
            continue
        if pid in done or not preg:
            continue
        if saltar_wifi and (
            "wifi" in pid.lower()
            or any(k in preg.lower() for k in _WIFI_MARKERS)
        ):
            continue
        if _parece_dump_pagos(preg) and not _cliente_pide_pagar(mensaje_cliente):
            continue
        return {
            "accion": "ask",
            "mensaje": preg,
            "paso_cubierto": pid,
            "motivo": "fallback_playbook",
        }
    # Checklist agotado (o solo quedaban pasos WiFi irrelevantes)
    return {
        "accion": "escalate",
        "mensaje": (
            "Con lo que me contaste ya no lo resolvemos a distancia. "
            "¿Querés que te derive con un agente?"
        ),
        "paso_cubierto": "",
        "motivo": "fallback_checklist_agotado",
    }


def _cliente_pide_pagar(texto: str) -> bool:
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "como pago",
            "cómo pago",
            "quiero pagar",
            "necesito pagar",
            "para abonar",
            "quiero abonar",
            "para pagar",
            "pagar la",
            "abonar",
            "medio de pago",
            "qr",
            "fiserv",
            "mercado pago",
            "modo",
            "saldo pendiente",
            "me cortaron",
            "sin servicio por",
            "datos de la cuenta",
            "cuenta bancaria",
            "cbu",
            "transferencia",
        )
    )


def _cliente_consulta_saldo(texto: str) -> bool:
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "cuanto me vino",
            "cuánto me vino",
            "cuanto debo",
            "cuánto debo",
            "ultima factura",
            "última factura",
            "ultimo monto",
            "último monto",
            "importe de la factura",
            "monto de la factura",
            "saldo de la factura",
            "saldo de mi",
            "qué me vino",
            "que me vino",
            "cuanto me cobraron",
            "cuánto me cobraron",
            "cuanto es la factura",
            "cuánto es la factura",
        )
    )


def _pide_cbu_o_adjunto(texto: str) -> bool:
    t = (texto or "").lower()
    return any(
        k in t
        for k in (
            "cbu",
            "cuenta bancaria",
            "transferencia",
            "alias bancario",
            "adjunt",
            "mandame el qr",
            "pasame el qr",
            "enviame el qr",
            "pegame el qr",
        )
    )


def _cierra_consulta_facturacion(texto: str) -> bool:
    """El abonado ya obtuvo el dato (saldo/pago) y cierra la consulta."""
    t = (texto or "").lower().strip()
    if not t:
        return False
    if any(
        k in t
        for k in (
            "no anda",
            "problema",
            "sigue",
            "falla",
            "aument",
            "reclamo",
        )
    ):
        return False
    return any(
        k in t
        for k in (
            "gracias",
            "graciass",
            "listo",
            "perfecto",
            "solo queria",
            "solo quería",
            "ya me lo dijiste",
            "no hace falta",
            "eso era todo",
            "nada mas",
            "nada más",
        )
    )


def _parece_invento_pago(mensaje: str) -> bool:
    """Respuestas que inventan CBU, adjuntos o pasos web inexistentes."""
    t = (mensaje or "").lower()
    return any(
        k in t
        for k in (
            "cbu",
            "insertar cbu",
            "te adjunto",
            "te paso el código qr",
            "te paso el codigo qr",
            "adjunto el código",
            "adjunto el codigo",
            "cuenta bancaria es",
            "número de cbu",
            "numero de cbu",
            "sección de 'pagos'",
            'seccion de "pagos"',
            "generarlo desde nuestra web",
            "ingresá tu número de asociado",
            "ingresa tu numero de asociado",
        )
    )


def _parece_desvio_tecnico(mensaje: str) -> bool:
    t = (mensaje or "").lower()
    return any(
        k in t
        for k in (
            "fibra óptica",
            "fibra optica",
            "cable amarillo",
            "cajita blanca",
            "antena en el techo",
            "línea telefónica",
            "linea telefonica",
            "luces del ont",
            "reiniciá el módem",
            "reinicia el modem",
        )
    )


def _saldo_desde_contexto(contexto_abonado: str) -> str | None:
    import re

    m = re.search(r"deuda_monto:\s*([^\n]+)", contexto_abonado or "", flags=re.I)
    if not m:
        return None
    val = (m.group(1) or "").strip()
    if not val or "sin dato" in val.lower():
        return None
    return val.strip().lstrip("$").strip()


def _facturacion_deterministica(
    mensaje_cliente: str,
    *,
    contexto_abonado: str,
    historial_mensajes: list | None,
) -> dict | None:
    """Respuestas fijas con saldo real; sin inventar CBU/QR adjunto/web."""
    from app.services.eco_voice import PLANTILLA_PAGO_QR

    identificado = "modo: identificado" in (contexto_abonado or "")
    saldo = _saldo_desde_contexto(contexto_abonado) if identificado else None
    t = (mensaje_cliente or "").lower().strip()

    # Invitado: sin cuenta no hay saldo; pedir DNI (no llamar al LLM).
    if not identificado and (
        _cliente_consulta_saldo(mensaje_cliente)
        or any(k in t for k in ("deuda", "saldo", "factura", "cuanto debo", "cuánto debo"))
    ):
        return {
            "accion": "ask",
            "mensaje": (
                "En modo invitado no veo tu cuenta. "
                "Pasame tu DNI (solo el número) y te digo el saldo de la última factura."
            ),
            "paso_cubierto": "pedir_dni_saldo",
            "motivo": "facturacion_invitado_pide_dni",
        }

    if identificado and _cierra_consulta_facturacion(mensaje_cliente):
        return {
            "accion": "resolved",
            "mensaje": "De nada. Cualquier otra consulta, escribime. ¡Buen día!",
            "paso_cubierto": "cierre_facturacion",
            "motivo": "facturacion_cierre_cliente",
        }

    if identificado and saldo is not None and _cliente_consulta_saldo(mensaje_cliente):
        return {
            "accion": "ask",
            "mensaje": (
                f"El saldo / última factura que figura es ${saldo}. "
                "¿Necesitás abonar o algo más de la factura?"
            ),
            "paso_cubierto": "informar_saldo",
            "motivo": "facturacion_saldo_real",
        }

    hist_txt = " ".join(
        _autor_texto(m)[1] for m in (historial_mensajes or [])[-8:]
    ).lower()
    oferta_pago_previa = any(
        k in hist_txt for k in ("qr", "fiserv", "pagar", "abonar", "mercado pago")
    )

    if identificado and (
        _pide_cbu_o_adjunto(mensaje_cliente)
        or (
            t in ("ambas", "los dos", "las dos", "si", "sí")
            and oferta_pago_previa
            and any(k in hist_txt for k in ("cbu", "bancaria", "qr", "cuenta"))
        )
    ):
        extra = f" Saldo pendiente ${saldo}." if saldo is not None else ""
        return {
            "accion": "ask",
            "mensaje": (
                f"Por este chat no te puedo pasar CBU ni adjuntar un QR.{extra} "
                f"{PLANTILLA_PAGO_QR}"
            ),
            "paso_cubierto": "guia_pago_fiserv",
            "motivo": "facturacion_sin_invento_cbu",
        }

    if identificado and (
        _cliente_pide_pagar(mensaje_cliente)
        or (t in ("ambas", "si", "sí", "dale") and oferta_pago_previa)
    ):
        pref = f"Saldo pendiente ${saldo}. " if saldo is not None else ""
        return {
            "accion": "ask",
            "mensaje": f"{pref}{PLANTILLA_PAGO_QR}",
            "paso_cubierto": "guia_pago_fiserv",
            "motivo": "facturacion_pago_plantilla",
        }

    return None


def _parece_dump_pagos(mensaje: str) -> bool:
    """Detecta respuestas tipo manual (QR + varios medios) en vez de indagar."""
    t = (mensaje or "").lower()
    hits = sum(
        1
        for k in (
            "fiserv",
            "mercado pago",
            "modo",
            "qr",
            "copia de factura",
            "identific",
            "portal",
        )
        if k in t
    )
    return hits >= 3 or (hits >= 2 and len(t) > 280)


def _ofrece_handoff_prematuro(mensaje: str) -> bool:
    """True si el mensaje invita a asesor/llamada/ticket en vez de seguir N1."""
    t = (mensaje or "").lower()
    return any(
        k in t
        for k in (
            "asesor",
            "te contacte",
            "te contactemos",
            "preferís que te llam",
            "preferis que te llam",
            "que te llamen",
            "te llame",
            "área de cuentas",
            "area de cuentas",
            "abra un ticket",
            "abro un ticket",
            "generé el ticket",
            "genere el ticket",
            "te derive",
            "un agente te",
        )
    )


def _pregunta_pago_fuera_de_lugar(mensaje: str, mensaje_cliente: str) -> bool:
    """Preguntas de medio/fecha de pago cuando el cliente no dijo que pagó."""
    if _cliente_pide_pagar(mensaje_cliente):
        return False
    t = (mensaje or "").lower()
    return any(
        k in t
        for k in (
            "medio de pago",
            "fecha realizó",
            "fecha realizo",
            "fecha del pago",
            "qué fecha",
            "que fecha",
            "realizó el movimiento",
            "realizo el movimiento",
        )
    )


def diagnosticar_turno(
    *,
    intencion: str,
    checklist: list[PasoPlaybook] | list[dict],
    historial_mensajes: list[Any],
    mensaje_cliente: str,
    turnos_diagnostico: int,
    pasos_cubiertos: list[str],
    kb_fragmento: str = "",
    forzar_agente: bool = False,
    contexto_abonado: str = "",
) -> dict[str, str]:
    """Pide a la IA el próximo acto de diagnóstico. Fallback = siguiente paso del playbook."""
    if forzar_agente:
        return {
            "accion": "escalate",
            "mensaje": (
                "Dale, te derivo con un agente y le paso el historial. "
                "Quedate en este chat."
            ),
            "paso_cubierto": "",
            "motivo": "pedido_humano",
        }

    motivo_optico = detectar_falla_optica_escalar(mensaje_cliente, historial_mensajes)
    if motivo_optico:
        if motivo_optico == "fibra_danada" and "los" not in (mensaje_cliente or "").lower():
            msg_optico = (
                "Con daño visible en el cable de fibra ya no lo resolvemos a distancia: "
                "hace falta una visita técnica. Te derivo con un agente para coordinarla."
            )
        else:
            msg_optico = (
                "La luz LOS en rojo indica que la fibra no está llegando bien a la cajita. "
                "Eso ya no lo resolvemos reiniciando: hace falta una visita técnica. "
                "Te derivo con un agente para coordinarla."
            )
        return {
            "accion": "escalate",
            "mensaje": msg_optico,
            "paso_cubierto": "",
            "motivo": motivo_optico,
        }

    from app.services.eco_voice import (
        HISTORIAL_CHAT_MAX_MSGS,
        TEMPERATURE_N1,
        historial_canal_a_mensajes_chat,
        system_prompt_eco_n1,
    )
    from app.services.prompt_safety import (
        looks_like_jailbreak,
        sanitize_user_text,
        strip_instruction_phrases,
        with_anti_injection,
        wrap_untrusted,
    )

    # Inyección / jailbreak: no dejar que el LLM elija escalate/resolved
    if looks_like_jailbreak(mensaje_cliente):
        fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
        return {**fb, "motivo": "bloqueado_prompt_injection"}

    checklist_txt = _checklist_texto(checklist, pasos_cubiertos)
    kb = strip_instruction_phrases((kb_fragmento or "").strip()[:800])
    kb_block = f"\nConocimiento útil (opcional):\n{wrap_untrusted('KB', kb, max_chars=800)}\n" if kb else ""
    turnos = max(0, int(turnos_diagnostico or 0))
    msg_safe = sanitize_user_text(mensaje_cliente)
    es_facturacion = (intencion or "").strip() == "facturacion"

    if es_facturacion:
        det = _facturacion_deterministica(
            mensaje_cliente,
            contexto_abonado=contexto_abonado,
            historial_mensajes=historial_mensajes,
        )
        if det:
            return det

    reglas_facturacion = ""
    if es_facturacion:
        reglas_facturacion = (
            "\nReglas EXTRA — facturación/cuenta (prioridad alta):\n"
            "- Primero INDAGÁ el problema real con UNA pregunta. No sueltes un manual de pagos.\n"
            "- Si habla de aumento, tarifa más cara o factura distinta: preguntá mes, montos "
            "(antes vs ahora) o si hubo cambio de plan/servicios. NUNCA preguntes medio de pago "
            "ni fecha de un pago salvo que diga que pagó y no figura.\n"
            "- Si no reconoce un cobro: pedí mes/importe/concepto; no asumas que es un pago fallido.\n"
            "- Solo explicá cómo pagar (QR Fiserv / Mercado Pago / MODO) si pide pagar, QR, "
            "saldo a abonar, o tiene corte. En ese caso, una o dos oraciones + una pregunta.\n"
            "- NUNCA inventes CBU, alias, cuenta bancaria, adjuntos de QR ni pasos de una web "
            "de pagos que no existan. Si no hay integración de QR en el chat, pedí el QR Fiserv "
            "de la factura o derivá a agente.\n"
            "- Si CONTEXTO_ABONADO trae deuda_monto, usá SOLO ese valor; no inventes montos.\n"
            "- En consulta de saldo/pago NO preguntes por fibra, antena, módem ni tipode conexión.\n"
            "- En modo invitado (sin cuenta): pedí DNI/N.º de socio; no inventes saldos.\n"
            "- Si el cliente agradece y dice que solo quería el saldo: accion=resolved.\n"
            "- No ofrezcas asesor/ticket hasta indagar al menos "
            f"{MIN_TURNOS_ANTES_ESCALAR} turnos, salvo que pida agente.\n"
            "- escalate cuando ya pediste el detalle y hace falta sistema interno, o si pide agente.\n"
        )

    system = with_anti_injection(
        system_prompt_eco_n1(
            intencion=intencion,
            turnos=turnos,
            min_turnos_antes_escalar=MIN_TURNOS_ANTES_ESCALAR,
            reglas_extra=reglas_facturacion,
            contexto_abonado=contexto_abonado,
        )
    )

    chat_hist = historial_canal_a_mensajes_chat(
        historial_mensajes,
        max_msgs=HISTORIAL_CHAT_MAX_MSGS,
    )
    # Instrucción estructurada al final (el historial ya trae el último mensaje del cliente)
    task = (
        f"Estado del diagnóstico (interno):\n"
        f"- Intención: {sanitize_user_text(intencion, max_chars=80)}\n"
        f"- Turnos de diagnóstico ya hechos: {turnos}\n"
        f"- Pasos ya cubiertos: {', '.join(pasos_cubiertos) or '(ninguno)'}\n"
        f"- Checklist guía:\n{checklist_txt}\n"
        f"{kb_block}"
        f"Último mensaje del cliente (referencia):\n"
        f"{wrap_untrusted('ULTIMO_MENSAJE_CLIENTE', msg_safe)}\n"
        "Decidí el próximo acto y respondé SOLO el JSON pedido."
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(chat_hist)
    messages.append({"role": "user", "content": task})

    try:
        from app.llm import chat_completion

        try:
            raw = chat_completion(
                messages,
                temperature=TEMPERATURE_N1,
                json_mode=True,
            )
        except Exception:
            raw = chat_completion(
                messages,
                temperature=TEMPERATURE_N1,
                json_mode=False,
            )
        data = _extract_json(raw)
        accion = str(data.get("accion") or "ask").strip().lower()
        if accion not in ("ask", "resolved", "escalate"):
            accion = "ask"
        mensaje = str(data.get("mensaje") or "").strip()
        paso = str(data.get("paso_cubierto") or "").strip()
        motivo = str(data.get("motivo") or "ia").strip()[:200]
        forzar_optico = bool(
            detectar_falla_optica_escalar(mensaje_cliente, historial_mensajes)
            or (
                los_confirmada_en_historial(mensaje_cliente, historial_mensajes)
                and any(k in mensaje.lower() for k in _WIFI_MARKERS)
            )
        )

        # Si la IA pregunta WiFi con LOS ya confirmada → forzar escalate óptico
        if (
            accion == "ask"
            and los_confirmada_en_historial(mensaje_cliente, historial_mensajes)
            and any(k in mensaje.lower() for k in _WIFI_MARKERS)
        ):
            accion = "escalate"
            motivo = "bloqueado_wifi_post_los"
            mensaje = (
                "La luz LOS en rojo indica un problema de fibra/señal óptica; "
                "no se arregla mirando el WiFi. Te derivo para coordinar una visita técnica."
            )

        # Guardrails
        if (
            accion == "escalate"
            and turnos < MIN_TURNOS_ANTES_ESCALAR
            and not forzar_agente
            and not forzar_optico
            and motivo not in (
                "fibra_danada",
                "los_con_chequeo_fibra",
                "los_y_fibra_danada",
                "los_confirmada",
                "bloqueado_wifi_post_los",
            )
        ):
            accion = "ask"
            motivo = "bloqueado_min_turnos"
            if not mensaje or "?" not in mensaje:
                fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                mensaje = fb["mensaje"]
                paso = fb.get("paso_cubierto") or paso

        # Escalate por IA solo si el checklist está casi agotado (evita inyección → ticket)
        if (
            accion == "escalate"
            and not forzar_agente
            and not forzar_optico
            and motivo not in (
                "fibra_danada",
                "los_con_chequeo_fibra",
                "los_y_fibra_danada",
                "los_confirmada",
                "bloqueado_wifi_post_los",
            )
        ):
            ids = []
            for p in checklist or []:
                pid = p.get("id") if isinstance(p, dict) else getattr(p, "id", "")
                if pid:
                    ids.append(str(pid))
            cubiertos = {str(x) for x in (pasos_cubiertos or [])}
            restantes = [i for i in ids if i not in cubiertos]
            if len(restantes) > 1 and turnos < max(MIN_TURNOS_ANTES_ESCALAR + 1, 5):
                accion = "ask"
                motivo = "bloqueado_escalate_sin_agotamiento"
                if not mensaje or "?" not in mensaje:
                    fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                    mensaje = fb["mensaje"]
                    paso = fb.get("paso_cubierto") or paso

        # Re-chequeo óptico por si la IA ignoró evidencia
        opt2 = detectar_falla_optica_escalar(mensaje_cliente, historial_mensajes)
        if opt2 and accion != "escalate":
            accion = "escalate"
            motivo = opt2
            mensaje = (
                "La luz LOS en rojo indica que la fibra no está llegando bien a la cajita. "
                "Eso ya no lo resolvemos reiniciando: hace falta una visita técnica. "
                "Te derivo con un agente para coordinarla."
            )

        if accion == "resolved":
            t = (mensaje_cliente or "").lower()
            if any(
                k in t
                for k in (
                    "no anda", "no funciona", "sigue", "problema", "falla",
                    "sin internet", "no me", "quisiera", "consultar",
                )
            ):
                accion = "ask"
                motivo = "bloqueado_resolved_con_sintoma"
                if not mensaje or "¿" not in mensaje:
                    fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                    mensaje = fb["mensaje"]
                    paso = fb.get("paso_cubierto") or paso

        # Facturación: no soltar manual de pagos si el cliente no pidió pagar
        if (
            es_facturacion
            and accion == "ask"
            and _parece_dump_pagos(mensaje)
            and not _cliente_pide_pagar(mensaje_cliente)
            and not _cliente_pide_pagar(
                " ".join(_autor_texto(m)[1] for m in (historial_mensajes or [])[-6:])
            )
        ):
            mensaje = (
                "Dale, contame un poco más: ¿es por un aumento respecto al mes anterior, "
                "un cobro que no reconocés, o necesitás copia/saldo o cómo pagar?"
            )
            paso = "triaje_motivo"
            motivo = "bloqueado_dump_pagos"

        # Facturación: bloquear inventos (CBU, adjunto QR falso, web inventada) y desvío técnico
        if es_facturacion and accion in ("ask", "resolved") and (
            _parece_invento_pago(mensaje) or _parece_desvio_tecnico(mensaje)
        ):
            saldo = _saldo_desde_contexto(contexto_abonado)
            from app.services.eco_voice import PLANTILLA_PAGO_QR

            pref = f"Saldo pendiente ${saldo}. " if saldo else ""
            if _cliente_pide_pagar(mensaje_cliente) or _pide_cbu_o_adjunto(mensaje_cliente):
                mensaje = (
                    f"{pref}Por este chat no te paso CBU ni adjunto QR. "
                    f"{PLANTILLA_PAGO_QR}"
                )
                paso = "guia_pago_fiserv"
            elif saldo and _cliente_consulta_saldo(mensaje_cliente):
                mensaje = (
                    f"El saldo / última factura que figura es ${saldo}. "
                    "¿Necesitás abonar o algo más de la factura?"
                )
                paso = "informar_saldo"
            else:
                mensaje = (
                    "Para la factura puedo decirte el saldo del padrón o guiarte con el "
                    "QR Fiserv de la factura. ¿Qué necesitás exactamente?"
                )
                paso = "triaje_motivo"
            motivo = "bloqueado_invento_pago_o_desvio"
            if accion == "resolved":
                accion = "ask"

        # No ofrecer asesor/llamada antes del mínimo de turnos N1
        if (
            accion == "ask"
            and turnos < MIN_TURNOS_ANTES_ESCALAR
            and _ofrece_handoff_prematuro(mensaje)
            and not forzar_agente
        ):
            if es_facturacion:
                mensaje = (
                    "Para confirmar si hubo ajuste de tarifa o cambio de plan necesito "
                    "mirar tu cuenta. ¿Me pasás el DNI del titular o N.º de socio?"
                )
                paso = "identificar_cuenta"
            else:
                fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                mensaje = fb["mensaje"]
                paso = fb.get("paso_cubierto") or paso
            motivo = "bloqueado_handoff_prematuro"

        # No preguntar medio/fecha de pago si no dijo que pagó
        if accion == "ask" and _pregunta_pago_fuera_de_lugar(mensaje, mensaje_cliente):
            if es_facturacion:
                mensaje = (
                    "Perfecto. Para ver si hubo un ajuste necesito ubicarte: "
                    "¿me pasás DNI del titular o N.º de socio?"
                )
                paso = "identificar_cuenta"
            else:
                fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                mensaje = fb["mensaje"]
                paso = fb.get("paso_cubierto") or paso
            motivo = "bloqueado_pregunta_pago"

        if not mensaje:
            fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
            return {**fb, "motivo": f"ia_sin_mensaje:{motivo}"}

        # Una sola pregunta
        if accion == "ask" and mensaje.count("?") > 1:
            # quedarse con hasta la primera pregunta
            idx = mensaje.find("?")
            mensaje = mensaje[: idx + 1].strip()
            if len(mensaje) < 8:
                fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                mensaje = fb["mensaje"]

        if len(mensaje) > 420:
            mensaje = mensaje[:417] + "…"

        return {
            "accion": accion,
            "mensaje": mensaje,
            "paso_cubierto": paso,
            "motivo": motivo,
        }
    except Exception:
        logger.warning("diagnostico_n1 IA falló; fallback playbook", exc_info=True)
        return _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
