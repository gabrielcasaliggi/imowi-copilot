"""Voz Eco N1: system prompts humanizados + contexto de abonado (listo para DB/APIs)."""

from __future__ import annotations

from typing import Any

from app.config import BOT_DISPLAY_NAME, PRODUCT_DISPLAY_NAME

# Parámetros de conversación N1 (canal abonado)
TEMPERATURE_N1 = 0.4
HISTORIAL_CHAT_MAX_MSGS = 14  # ~10–15 turnos


def _mask_dni(dni: str) -> str:
    d = "".join(c for c in (dni or "") if c.isdigit())
    if len(d) < 5:
        return d or ""
    return f"{d[:2]}***{d[-3:]}"


# Oficina virtual Batán — links oficiales (no inventar otras URLs).
OV_BATAN_URL = "https://ov.batan.coop"
OV_BATAN_PAGAR_URL = "https://ov.batan.coop/#/pagar"
OV_BATAN_AVISO_PAGO_URL = "https://ov.batan.coop/#/aviso-de-pago"

# Una URL por línea para que el portal las muestre como links claros.
TEXTO_OV_GESTIONES = (
    f"Pagos y gestiones:\n{OV_BATAN_URL}\n"
    f"Para pagar con DNI:\n{OV_BATAN_PAGAR_URL}"
)

# Plantilla fija N1 pagos — no depende del LLM (evita inventar CBU/adjuntos).
PLANTILLA_PAGO_QR = (
    f"Podés abonar acá:\n{OV_BATAN_PAGAR_URL}\n"
    f"Oficina virtual:\n{OV_BATAN_URL}\n"
    "También con el QR Fiserv de la factura (Mercado Pago, MODO, etc.). "
    "Cuando se acredita, el servicio se reactiva solo. "
    "Si no tenés el QR, identificáte con DNI en el portal o pedí a un agente que te ubique la cuenta. "
    "¿Pudiste pagar o necesitás que te ubique la cuenta?"
)

# Demora de acreditación (pago ≠ refleja al instante en padrón/BillTrack).
TEXTO_DEMORA_ACREDITACION = (
    "El pago puede demorar entre 24 y 48 hs en reflejarse en el sistema, "
    "según la entidad donde lo hayas abonado."
)

# Aviso de pago OV: reactiva automáticamente solo si el servicio estaba cortado por deuda.
TEXTO_OV_AVISO_PAGO = (
    f"{TEXTO_DEMORA_ACREDITACION}\n\n"
    "Si el servicio está cortado por deuda, cargá el aviso de pago acá "
    f"para habilitarlo automáticamente:\n{OV_BATAN_AVISO_PAGO_URL}\n"
    "Ingresá tu DNI, el monto abonado y dónde pagaste."
)


def texto_ov_aviso_pago(*, cortado: bool = False) -> str:
    """Texto N1 según si el padrón figura con corte/suspensión por deuda."""
    if cortado:
        return (
            f"{TEXTO_DEMORA_ACREDITACION}\n\n"
            "Como el servicio figura cortado por deuda, con el aviso se habilita solo. "
            f"Entrá acá:\n{OV_BATAN_AVISO_PAGO_URL}\n"
            "Completá DNI, monto abonado y dónde pagaste."
        )
    return TEXTO_OV_AVISO_PAGO


def servicio_cortado_desde_contexto(contexto_abonado: str | None) -> bool:
    """True si CONTEXTO_ABONADO indica corte/suspensión (no baja)."""
    import re

    m = re.search(
        r"estado_servicio:\s*([^\n]+)", contexto_abonado or "", flags=re.I
    )
    if not m:
        return False
    e = (m.group(1) or "").strip().lower()
    return e in ("corte", "cortado", "suspendido", "suspendida")


def parse_monto(raw: str | float | int | None) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().replace("$", "").replace(" ", "")
    # Guiones unicode (BillTrack / Excel a veces manda − U+2212)
    s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
    if not s:
        return None
    # 1.234,56 → 1234.56 ; 1234.56 queda
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def formatear_monto_ars(valor: float) -> str:
    """Formato legible AR: 3248.04 → 3.248,04"""
    neg = valor < 0
    v = abs(valor)
    entero = int(v)
    dec = int(round((v - entero) * 100))
    if dec == 100:
        entero += 1
        dec = 0
    entero_txt = f"{entero:,}".replace(",", ".")
    return f"{'-' if neg else ''}{entero_txt},{dec:02d}"


def texto_monto_ars(raw: str | float | int | None) -> str:
    """Monto listo para mostrar/hablar: siempre pesos argentinos (nunca USD)."""
    monto = parse_monto(raw)
    if monto is None:
        s = str(raw or "0").strip().lstrip("$").strip() or "0"
        return f"{s} pesos"
    return f"{formatear_monto_ars(monto)} pesos"


def mensaje_saldo_padron(
    deuda_raw: str | float | int | None,
    *,
    incluir_ov: bool = True,
    nota_extra: str = "",
) -> str:
    """Texto claro de saldo + links OV.

    Convención BillTrack / Batán (padrón):
      - positivo → debe ese monto
      - negativo → saldo a favor del cliente
      - 0 → sin deuda
    Montos siempre en pesos argentinos (ARS).
    """
    monto = parse_monto(deuda_raw)
    debe = False
    if monto is None:
        body = (
            f"El saldo / última factura que figura es {texto_monto_ars(deuda_raw)}."
        )
    elif monto > 0:
        debe = True
        body = f"El saldo / última factura pendiente es {texto_monto_ars(monto)}."
    elif monto == 0:
        body = "No figuran deudas pendientes (saldo 0 pesos)."
    else:
        body = (
            f"Tenés un saldo a favor de {texto_monto_ars(abs(monto))} "
            "(no figuran deudas pendientes)."
        )

    partes = [body]
    if (nota_extra or "").strip():
        partes.append(nota_extra.strip())
    if incluir_ov:
        partes.append(TEXTO_OV_GESTIONES)
        if debe:
            partes.append("¿Necesitás abonar o algo más?")
        else:
            partes.append("¿Necesitás algo más?")
    return "\n".join(partes)


def _etiqueta_servicios(servicio: str) -> str:
    s = (servicio or "").strip().lower()
    if s == "movil":
        return "móvil IMOWI (sin internet fijo)"
    if s == "internet":
        return "internet fijo (sin móvil IMOWI)"
    if s == "ambos":
        return "internet fijo y móvil IMOWI"
    return "(sin dato de productos en padrón)"


def enrich_contexto_desde_integraciones(
    abonado: Any | None,
    *,
    org_id: str = "",
) -> dict[str, str]:
    """Hook para ONT/OLT Huawei, pagos Fiserv, cortes de zona y PPPoE/Radius.

    Claves:
      - nro_asociado, ont_estado, olt_huawei, pago_qr_reciente, cortes_zona
      - pppoe_estado, pppoe_login, pppoe_tipo, pppoe_ip, pppoe_uptime, pppoe_nas, pppoe_resumen
    """
    _ = org_id
    out = {
        "nro_asociado": "",
        "ont_estado": "",
        "olt_huawei": "",
        "pago_qr_reciente": "",
        "cortes_zona": "",
        "pppoe_estado": "",
        "pppoe_login": "",
        "pppoe_tipo": "",
        "pppoe_ip": "",
        "pppoe_uptime": "",
        "pppoe_nas": "",
        "pppoe_resumen": "",
        "pppoe_triage": "",
    }
    if abonado is None:
        return out
    try:
        from app.services.conexion_pppoe import contexto_pppoe_para_abonado

        pppoe = contexto_pppoe_para_abonado(abonado)
        for k, v in pppoe.items():
            if str(v or "").strip():
                out[k] = str(v).strip()
    except Exception:
        # Nunca tumbar el prompt del bot por fallas de Radius/BillTrack
        pass
    return out


def build_contexto_abonado(
    abonado: Any | None,
    *,
    org_id: str = "",
    extras: dict[str, str] | None = None,
) -> str:
    """Bloque de ficha para el system prompt. No inventa: solo datos reales o 'sin dato'."""
    integ = enrich_contexto_desde_integraciones(abonado, org_id=org_id)
    if extras:
        for k, v in extras.items():
            if str(v or "").strip():
                integ[k] = str(v).strip()

    pppoe_line = integ.get("pppoe_resumen") or "(sin dato — integrar Radius/NAS)"
    triage = (integ.get("pppoe_triage") or "").strip()

    if not abonado:
        lines = [
            "CONTEXTO_ABONADO:",
            "- modo: invitado (sin cuenta identificada)",
            "- nombre: (sin dato)",
            "- nro_asociado: (sin dato)",
            "- estado_servicio: (sin dato)",
            "- deuda: (sin dato)",
            f"- ont_estado: {integ.get('ont_estado') or '(sin dato — integrar NMS)'}",
            f"- olt_huawei: {integ.get('olt_huawei') or '(sin dato — integrar NMS)'}",
            f"- pago_qr_reciente: {integ.get('pago_qr_reciente') or '(sin dato — integrar Fiserv)'}",
            f"- cortes_zona: {integ.get('cortes_zona') or '(sin dato — integrar operaciones)'}",
            f"- pppoe: {pppoe_line}",
            "- Regla: no inventes saldos, ONT/OLT, PPPoE ni pagos. Pedí DNI/N.º de socio si hace falta la cuenta.",
        ]
        return "\n".join(lines)

    nombre = str(getattr(abonado, "nombre", "") or "").strip()
    dni = str(getattr(abonado, "dni", "") or "").strip()
    nro = (integ.get("nro_asociado") or "").strip() or "(sin dato — integrar asociados)"
    servicio = str(getattr(abonado, "servicio", "") or "").strip() or "(sin dato)"
    plan = str(getattr(abonado, "plan", "") or "").strip() or "(sin dato)"
    estado = str(getattr(abonado, "estado", "") or "").strip() or "(sin dato)"
    deuda = str(getattr(abonado, "deuda_monto", "") or "").strip() or "0"
    linea = str(getattr(abonado, "linea_msisdn", "") or "").strip() or "(sin dato)"

    lines = [
        "CONTEXTO_ABONADO (datos reales del sistema; usalos solo si aportan):",
        "- modo: identificado",
        f"- nombre: {nombre or '(sin dato)'}",
        f"- dni_enmascarado: {_mask_dni(dni) or '(sin dato)'}",
        f"- nro_asociado: {nro}",
        f"- servicio: {servicio}",
        f"- servicios_contratados: {_etiqueta_servicios(servicio)}",
        f"- plan: {plan}",
        f"- estado_servicio: {estado}",
        f"- deuda_monto: {deuda} (pesos argentinos / ARS — NUNCA dólares ni USD)",
        f"- linea: {linea}",
        f"- ont_estado: {integ.get('ont_estado') or '(sin dato — integrar NMS)'}",
        f"- olt_huawei: {integ.get('olt_huawei') or '(sin dato — integrar NMS)'}",
        f"- pago_qr_reciente: {integ.get('pago_qr_reciente') or '(sin dato — integrar Fiserv)'}",
        f"- cortes_zona: {integ.get('cortes_zona') or '(sin dato — integrar operaciones)'}",
        f"- pppoe: {pppoe_line}",
    ]
    if triage:
        lines.append(f"- pppoe_triage: {triage}")
    lines.extend(
        [
            "- Regla: si un campo dice '(sin dato)', no lo completes de memoria.",
            "- Los montos de deuda/factura/saldo son SIEMPRE pesos argentinos (ARS). "
            "Nunca digas dólares, USD ni 'dollar'. Preferí «pesos» o «$ … pesos».",
            "- Ofrecé SOLO los servicios_contratados. No preguntes por internet/fibra/Wi‑Fi "
            "si no figura internet fijo, ni por móvil IMOWI si no figura móvil.",
            "- Si no tiene internet fijo y dice 'no tengo internet', NO es un corte: "
            "no tiene ese producto contratado. No inicies diagnóstico de Wi‑Fi ni ONT.",
            "- Si pppoe indica conectado/desconectado, usá pppoe_triage: no contradigas "
            "el dato real ni pidas reinicio de ONT si triage dice linea_ok.",
        ]
    )
    return "\n".join(lines)


def system_prompt_eco_n1(
    *,
    intencion: str,
    turnos: int,
    min_turnos_antes_escalar: int,
    reglas_extra: str = "",
    contexto_abonado: str = "",
) -> str:
    """System prompt unificado: operador N1 empático (Eco)."""
    ctx = (contexto_abonado or "").strip()
    ctx_block = f"\n{ctx}\n" if ctx else ""
    intent = (intencion or "").strip()
    optica = intent in ("internet_ftth", "internet")
    linea_ok = "linea_ok" in ctx or "NO pedir reinicio de ONT" in ctx
    reglas_optica = ""
    if linea_ok or intent == "wifi":
        reglas_optica = (
            "- La línea de acceso/PPPoE ya está OK (o el caso es solo Wi‑Fi). "
            "NUNCA preguntes por luces ONT, PON, LOS, cajita blanca ni cable amarillo.\n"
            "- accion=ask: diagnóstico Wi‑Fi (zona, dispositivos, reinicio router Wi‑Fi, "
            "banda 2.4/5, cable vs Wi‑Fi si aún no se aclaró).\n"
            "- Si por cable anda y Wi‑Fi no: enfocá radio/router inalámbrico; escalate si "
            "persiste tras 2–3 chequeos útiles.\n"
            "- Excepciones escalate YA: pide agente/técnico.\n"
        )
    elif optica:
        reglas_optica = (
            "- accion=ask: autodiagnóstico (reinicio 30s, luces ONT/PON/LOS, WiFi vs cable).\n"
            "- Excepciones para escalate YA: pide agente/técnico/visita; luz LOS confirmada o "
            "fibra dañada; o checklist casi agotado con el problema persistente.\n"
            "- NUNCA preguntes por WiFi/saturación de canal después de LOS o daño de fibra.\n"
            "- Tras confirmar LOS, como máximo chequeá el cable amarillo; luego escalate.\n"
            "- Si confirma PON en verde fijo (y sin LOS roja), el enlace óptico está OK: "
            "NO preguntes por el cable amarillo. Preguntá si ya anda internet o, si sigue mal, "
            "si falla también por cable al router vs solo WiFi.\n"
            "- Si el cliente ya dijo que solo falla el Wi‑Fi (y la línea/PPPoE está OK), "
            "NO preguntes luces ONT: seguí triage Wi‑Fi.\n"
        )
    else:
        reglas_optica = (
            "- accion=ask: seguí el checklist de ESTA intención; no mezcles con otros servicios.\n"
            "- Excepciones para escalate YA: pide agente/técnico; o checklist casi agotado "
            "con el problema persistente.\n"
            "- NUNCA hables de luz LOS, PON, ONT, cable amarillo, cajita blanca ni visita "
            "por fibra salvo que la intención sea internet/FTTH.\n"
            "- NUNCA inventes una falla óptica ni uses plantillas de fibra en móvil, "
            "Sensa/TV, factura u otros temas.\n"
        )
    return (
        f"Sos {BOT_DISPLAY_NAME}, operador técnico N1 de {PRODUCT_DISPLAY_NAME} "
        "(Cooperativa Batán / Ecolan + móvil IMOWI). "
        "Hablás como en WhatsApp: cercano, empático y resolutivo. "
        "Usás español rioplatense (voseo). No sos un contestador ni Copilot NOC.\n"
        f"{ctx_block}\n"
        "Estilo:\n"
        "- Frases cortas: máximo 2 o 3 oraciones.\n"
        "- UNA sola pregunta o UNA sola instrucción por mensaje.\n"
        "- Si el cliente está frustrado ('siempre lo mismo', 'nunca anda'), validá en pocas "
        "palabras y seguí con el próximo paso útil.\n"
        "- Evitá menús rígidos, listas largas, viñetas y tonos de contestador automático.\n"
        "- No inventes datos (OLT, ONT, potencias, saldos, pagos, CBU, adjuntos QR, turnos, cortes de zona).\n"
        "- Montos de deuda/factura: siempre pesos argentinos (ARS). Nunca dólares/USD.\n"
        "- No uses jerga interna del NOC.\n\n"
        "Respondé SOLO JSON válido:\n"
        '{"accion":"ask"|"resolved"|"escalate","mensaje":"...","paso_cubierto":"id_o_vacio","motivo":"..."}\n\n'
        "Triaje N1 (sin tickets prematuros):\n"
        f"{reglas_optica}"
        f"- NO uses escalate hasta completar al menos {min_turnos_antes_escalar} turnos de "
        f"diagnóstico (ahora vas por el turno {turnos + 1}), salvo excepciones.\n"
        "- Si el cliente dice que NO tiene internet fijo / solo tiene móvil IMOWI, "
        "NO preguntes por fibra, radio ni ADSL: pasá a diagnóstico de móvil.\n"
        "- resolved solo si el cliente confirma explícitamente que ya funciona "
        "(anda / funciona / se solucionó). "
        "«me contestó», «me llamaron» o «si me contestó» NO es resolved: "
        "preguntá si ya le anda el servicio.\n"
        "- Si el problema sigue, NUNCA resolved.\n"
        "- Elegí el próximo chequeo según lo ya dicho; no repitas lo respondido.\n"
        "- El checklist es guía, no guión literal.\n"
        f"- Intención actual: {intent or 'general'}.\n"
        f"{reglas_extra}"
    )


def system_prompt_eco_rewrite() -> str:
    """Prompt corto para reescribir un borrador de playbook."""
    return (
        f"Sos {BOT_DISPLAY_NAME}, operador N1 de {PRODUCT_DISPLAY_NAME} "
        "(Cooperativa Batán / Ecolan + móvil IMOWI). "
        "Escribí como en WhatsApp: natural, breve, cálido y resolutivo (voseo). "
        "No sos contestador ni Copilot NOC; si derivás, decilo claro.\n"
        "REGLAS:\n"
        "- Máximo 2 o 3 oraciones cortas.\n"
        "- UNA sola pregunta o instrucción por mensaje.\n"
        "- Si hay frustración, validala en pocas palabras.\n"
        "- Sin listas, viñetas ni menús.\n"
        "- No inventes datos (OLT, ONT, saldos, turnos, potencias).\n"
        "- Montos de deuda/factura: siempre pesos argentinos (ARS). Nunca dólares/USD.\n"
        "- Conservá la intención del borrador; no agregues pasos extra.\n"
        "- Si el borrador menciona QR Fiserv / Mercado Pago / MODO, conservalo.\n"
        "- No digas que quedó resuelto si el cliente aún tiene el problema.\n"
        "- No ofrezcas ticket ni agente en los primeros pasos de autodiagnóstico.\n"
        "- Si el cliente no contestó la pregunta anterior, reiterá ESA pregunta."
    )


def historial_canal_a_mensajes_chat(
    historial_mensajes: list[Any] | None,
    *,
    max_msgs: int = HISTORIAL_CHAT_MAX_MSGS,
    max_chars_por_msg: int = 500,
) -> list[dict[str, str]]:
    """Convierte mensajes del canal a roles OpenAI (user/assistant)."""
    from app.services.prompt_safety import looks_like_jailbreak, sanitize_user_text

    out: list[dict[str, str]] = []
    for m in (historial_mensajes or [])[-max(1, max_msgs) :]:
        autor = getattr(m, "autor", None) or (m.get("autor") if isinstance(m, dict) else "")
        texto = getattr(m, "texto", None) or (m.get("texto") if isinstance(m, dict) else "")
        if not texto and isinstance(m, dict):
            texto = m.get("contenido") or m.get("mensaje") or ""
        t = sanitize_user_text(str(texto or ""), max_chars=max_chars_por_msg)
        if not t:
            continue
        autor_l = str(autor or "").strip().lower()
        if autor_l == "cliente":
            if looks_like_jailbreak(t):
                t = "[mensaje omitido por seguridad]"
            out.append({"role": "user", "content": t})
        elif autor_l in ("bot", "agente"):
            out.append({"role": "assistant", "content": t})
        else:
            # desconocido → no privilegiar como assistant
            out.append({"role": "user", "content": t})
    return out
