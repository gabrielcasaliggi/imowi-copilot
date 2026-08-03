"""Diagnóstico N1 dirigido por IA — el playbook es checklist, no guión rígido."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.config import BOT_DISPLAY_NAME, PRODUCT_DISPLAY_NAME
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
})

MIN_TURNOS_ANTES_ESCALAR = 3

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
        )
    )

    if dano and (bot_pregunto_fibra or bot_hablo_los or cliente_confirmo_los):
        return "fibra_danada"
    if cliente_confirmo_los and bot_pregunto_fibra and last:
        return "los_con_chequeo_fibra"
    if cliente_dice_los and dano:
        return "los_y_fibra_danada"
    if cliente_confirmo_los and dano:
        return "los_y_fibra_danada"
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
        return {
            "accion": "escalate",
            "mensaje": (
                "Con luz LOS y el estado del cable de fibra ya no lo resolvemos "
                "a distancia: hace falta visita técnica. ¿Te derivo con un agente "
                "para coordinar?"
            ),
            "paso_cubierto": "",
            "motivo": motivo_optico,
        }

    from app.services.prompt_safety import (
        format_historial_seguro,
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

    historial = format_historial_seguro(
        [
            {
                "rol": getattr(m, "rol", None) or (m.get("rol") if isinstance(m, dict) else "usuario"),
                "contenido": getattr(m, "contenido", None)
                or (m.get("contenido") if isinstance(m, dict) else str(m)),
            }
            for m in (historial_mensajes or [])
        ]
    )
    checklist_txt = _checklist_texto(checklist, pasos_cubiertos)
    kb = strip_instruction_phrases((kb_fragmento or "").strip()[:800])
    kb_block = f"\nConocimiento útil (opcional):\n{wrap_untrusted('KB', kb, max_chars=800)}\n" if kb else ""
    turnos = max(0, int(turnos_diagnostico or 0))
    msg_safe = sanitize_user_text(mensaje_cliente)

    system = with_anti_injection(
        f"Sos {BOT_DISPLAY_NAME}, técnico N1 de {PRODUCT_DISPLAY_NAME} "
        "(Cooperativa Batán / Ecolan + móvil IMOWI). "
        "Diagnosticás como un profesional de soporte: escuchás, pedís un dato útil, "
        "y avanzás. El checklist es una GUÍA de temas a cubrir, no un guión literal.\n\n"
        "Respondé SOLO JSON válido:\n"
        '{"accion":"ask"|"resolved"|"escalate","mensaje":"...","paso_cubierto":"id_o_vacio","motivo":"..."}\n\n'
        "Reglas:\n"
        "- accion=ask: una sola pregunta corta (máx 2 oraciones). Español argentino (vos).\n"
        "- Elegí el próximo chequeo según lo que YA dijo el cliente; no repitas lo respondido.\n"
        "- Podés reformular las preguntas del checklist o adaptarlas al caso.\n"
        "- No inventes datos (OLT, potencias, saldos, turnos, lecturas de red).\n"
        "- No uses jerga interna del NOC ni listas/viñetas.\n"
        f"- NO uses escalate hasta haber hecho al menos {MIN_TURNOS_ANTES_ESCALAR} turnos "
        f"de diagnóstico (ahora vas por el turno {turnos + 1}), salvo excepciones abajo.\n"
        "- Si pide técnico/visita/agente, escalate ya (no sigas el checklist).\n"
        "- Si hay luz LOS en rojo / confirmada, o cable de fibra dañado/malo: escalate YA. "
        "NUNCA preguntes por WiFi, cable al router ni saturación de canal después de LOS "
        "o daño de fibra: es falla óptica, no de WiFi.\n"
        "- Tras confirmar LOS, como máximo preguntá por el cable amarillo/fibra; "
        "con la respuesta (dañado o no), escalate.\n"
        "- resolved solo si el cliente confirma explícitamente que ya funciona.\n"
        "- Si el cliente sigue con el problema, NUNCA resolved.\n"
        "- paso_cubierto: id del checklist que estás cubriendo en este turno (si aplica).\n"
        "- Si el checklist está casi agotado y el problema sigue, escalate con mensaje claro."
    )

    user = (
        f"Intención: {sanitize_user_text(intencion, max_chars=80)}\n"
        f"Turnos de diagnóstico ya hechos: {turnos}\n"
        f"Pasos ya cubiertos: {', '.join(pasos_cubiertos) or '(ninguno)'}\n"
        f"Checklist guía:\n{checklist_txt}\n"
        f"{kb_block}"
        f"{wrap_untrusted('HISTORIAL', historial, max_chars=6000)}\n\n"
        f"{wrap_untrusted('ULTIMO_MENSAJE_CLIENTE', msg_safe)}\n"
        "Decidí el próximo acto."
    )

    try:
        from app.llm import chat_completion

        try:
            raw = chat_completion(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                json_mode=True,
            )
        except Exception:
            raw = chat_completion(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
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
                "Con la luz LOS en rojo ya es un tema de fibra/señal óptica; "
                "no se arregla mirando el WiFi. Te derivo para visita técnica."
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
            if len(restantes) > 1 and turnos < max(MIN_TURNOS_ANTES_ESCALAR + 2, 5):
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
                "Con luz LOS y el estado del cable de fibra ya no lo resolvemos "
                "a distancia: hace falta visita técnica. Te derivo con un agente."
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
