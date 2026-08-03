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


def es_intencion_diagnostico(intencion: str) -> bool:
    return (intencion or "").strip() in INTENCIONES_DIAGNOSTICO


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
        if pid not in done and preg:
            return {
                "accion": "ask",
                "mensaje": preg,
                "paso_cubierto": pid,
                "motivo": "fallback_playbook",
            }
    # Checklist agotado
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

    historial = _historial_texto(historial_mensajes)
    checklist_txt = _checklist_texto(checklist, pasos_cubiertos)
    kb = (kb_fragmento or "").strip()[:800]
    kb_block = f"\nConocimiento útil (opcional):\n{kb}\n" if kb else ""
    turnos = max(0, int(turnos_diagnostico or 0))

    system = (
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
        f"de diagnóstico (ahora vas por el turno {turnos + 1}), salvo que el cliente pida agente.\n"
        "- resolved solo si el cliente confirma explícitamente que ya funciona.\n"
        "- Si el cliente sigue con el problema, NUNCA resolved.\n"
        "- paso_cubierto: id del checklist que estás cubriendo en este turno (si aplica).\n"
        "- Si el checklist está casi agotado y el problema sigue, escalate con mensaje claro."
    )

    user = (
        f"Intención: {intencion}\n"
        f"Turnos de diagnóstico ya hechos: {turnos}\n"
        f"Pasos ya cubiertos: {', '.join(pasos_cubiertos) or '(ninguno)'}\n"
        f"Checklist guía:\n{checklist_txt}\n"
        f"{kb_block}"
        f"Historial:\n{historial}\n\n"
        f"Último mensaje del cliente: {mensaje_cliente}\n"
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

        # Guardrails
        if accion == "escalate" and turnos < MIN_TURNOS_ANTES_ESCALAR and not forzar_agente:
            accion = "ask"
            motivo = "bloqueado_min_turnos"
            if not mensaje or "?" not in mensaje:
                fb = _fallback_ask(checklist, pasos_cubiertos, mensaje_cliente)
                mensaje = fb["mensaje"]
                paso = fb.get("paso_cubierto") or paso

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
