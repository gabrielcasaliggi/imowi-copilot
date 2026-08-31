"""Velocidad contratada (BillTrack) vs test del abonado."""

from __future__ import annotations

import re
from typing import Any, Literal

ClaseVelocidad = Literal["ok", "aceptable", "bajo", ""]

# ≥70% del plan = normal (KB N1). <50% por cable = candidato a N2.
UMBRAL_OK = 0.70
UMBRAL_ACEPTABLE = 0.50

# Planes fijos típicos (Mb) si el producto dice «Fibra 100» sin unidad.
_PLANES_TIPICOS = frozenset(
    {3, 5, 6, 8, 10, 12, 15, 20, 25, 30, 50, 60, 80, 100, 150, 200, 300, 500, 600, 1000}
)

_RE_MBPS_EXPLICITO = re.compile(
    r"(?<!\d)(\d+(?:[.,]\d+)?)\s*"
    r"(?:mbps|mbit/s|mb/s|mbits?|megas?\b|megabits?\b|mb\b)",
    re.IGNORECASE,
)
_RE_M_CORTO = re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*[Mm]\b")
_RE_NUMERO_SUELTO = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*$")
_RE_GB = re.compile(r"\b\d+(?:[.,]\d+)?\s*gb\b|\bgiga", re.IGNORECASE)

_HINT_TEST_BOT = (
    "fast.com",
    "speedtest",
    "test de velocidad",
    "test por cable",
    "cuánto da",
    "cuanto da",
    "cuánto te dio",
    "cuanto te dio",
    "cuánto te da",
    "medidor de velocidad",
)


def _to_float(raw: str) -> float | None:
    try:
        n = float((raw or "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
    if n != n or n <= 0:
        return None
    return n


def extraer_mbps_plan(*textos: str) -> float | None:
    """Mbps contratados desde product/label/plan de BillTrack. None si no hay dato."""
    blob = " ".join(str(t or "").strip() for t in textos if str(t or "").strip())
    if not blob:
        return None
    m = _RE_MBPS_EXPLICITO.search(blob)
    if m:
        n = _to_float(m.group(1))
        if n is not None and n <= 2500:
            return n
    m = _RE_M_CORTO.search(blob)
    if m:
        n = _to_float(m.group(1))
        if n is not None and n <= 2500:
            return n
    # «Móvil 5GB» no es plan de internet fijo
    if _RE_GB.search(blob) and not _RE_MBPS_EXPLICITO.search(blob):
        return None
    enteros = [int(x) for x in re.findall(r"(?<!\d)(\d{1,4})(?!\d)", blob)]
    for n in enteros:
        if n in _PLANES_TIPICOS:
            return float(n)
    return None


def extraer_mbps_medido(
    texto: str,
    *,
    historial: list[Any] | None = None,
) -> float | None:
    """Resultado de speedtest dicho por el abonado (10M, 10Mb, 10 mbps)."""
    t = (texto or "").strip()
    if not t or len(t) > 80:
        return None
    m = _RE_MBPS_EXPLICITO.search(t)
    if m:
        n = _to_float(m.group(1))
        if n is not None and n <= 2500:
            return n
    m = _RE_M_CORTO.search(t)
    if m:
        n = _to_float(m.group(1))
        if n is not None and n <= 2500:
            return n
    # «10» / «10 de bajada» solo si el bot acaba de pedir el test
    if _bot_pidio_speedtest(historial):
        m = re.search(
            r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:de\s+bajada|bajada|de\s+descarga)?\s*$",
            t,
            re.IGNORECASE,
        )
        if m:
            n = _to_float(m.group(1))
            if n is not None and 0.5 <= n <= 2500:
                return n
        m = _RE_NUMERO_SUELTO.match(t)
        if m:
            n = _to_float(m.group(1))
            if n is not None and 0.5 <= n <= 2500:
                return n
    return None


def _bot_pidio_speedtest(historial: list[Any] | None) -> bool:
    if not historial:
        return False
    for m in reversed(list(historial)[-6:]):
        autor = getattr(m, "autor", None) or (m.get("autor") if isinstance(m, dict) else "")
        texto = getattr(m, "texto", None) or (m.get("texto") if isinstance(m, dict) else "")
        if str(autor or "").strip().lower() not in ("bot", "asistente", "eko", "assistant"):
            continue
        tl = str(texto or "").lower()
        if any(h in tl for h in _HINT_TEST_BOT):
            return True
        break
    return False


def clasificar_vs_plan(medido: float, plan: float) -> ClaseVelocidad:
    if plan <= 0 or medido <= 0:
        return ""
    ratio = medido / plan
    if ratio >= UMBRAL_OK:
        return "ok"
    if ratio >= UMBRAL_ACEPTABLE:
        return "aceptable"
    return "bajo"


def formatear_mbps(n: float) -> str:
    if n >= 10 or n == int(n):
        return str(int(round(n)))
    return f"{n:.1f}".replace(".", ",")


def plan_mbps_desde_contexto(contexto: str) -> float | None:
    ctx = contexto or ""
    m = re.search(r"plan_mbps:\s*(\d+(?:[.,]\d+)?)", ctx, re.IGNORECASE)
    if m:
        return _to_float(m.group(1))
    m = re.search(r"plan_contratado:\s*(\d+(?:[.,]\d+)?)\s*mbps", ctx, re.IGNORECASE)
    if m:
        return _to_float(m.group(1))
    m = re.search(r"producto=([^;\n]+)", ctx, re.IGNORECASE)
    if m:
        n = extraer_mbps_plan(m.group(1))
        if n:
            return n
    m = re.search(r"^- plan:\s*(.+)$", ctx, re.IGNORECASE | re.MULTILINE)
    if m:
        return extraer_mbps_plan(m.group(1))
    return None


def mensaje_velocidad_ok(medido: float, plan: float) -> str:
    m = formatear_mbps(medido)
    p = formatear_mbps(plan)
    return (
        f"Tu plan contratado es de {p} Mb; {m} Mb está dentro de lo esperado, "
        "no es una falla de la línea. Si se siente lento suele ser el Wi‑Fi o varios "
        "equipos a la vez. ¿Te anda mejor cerca del router o por cable?"
    )


def mensaje_velocidad_aceptable(medido: float, plan: float) -> str:
    m = formatear_mbps(medido)
    p = formatear_mbps(plan)
    return (
        f"Tu plan es de {p} Mb y el test dio {m} Mb: un poco abajo, pero no es un corte. "
        "Reiniciá módem y router 30 segundos y repetí el test por cable. ¿Mejoró?"
    )


def evaluar_speedtest_vs_plan(
    mensaje_cliente: str,
    historial_mensajes: list[Any] | None,
    contexto_abonado: str,
    *,
    intencion: str = "",
) -> dict[str, str] | None:
    """Si hay plan + test, corta el diagnóstico: no derivar cuando la velocidad es la del plan."""
    intent = (intencion or "").strip()
    if intent.startswith("facturacion") or intent in (
        "movil",
        "movil_datos",
        "movil_llamadas",
        "alta_plan",
        "tv_sensa",
    ):
        return None
    plan = plan_mbps_desde_contexto(contexto_abonado)
    medido = extraer_mbps_medido(mensaje_cliente, historial=historial_mensajes)
    if plan is None or medido is None:
        return None
    clase = clasificar_vs_plan(medido, plan)
    if clase == "ok":
        return {
            "accion": "ask",
            "mensaje": mensaje_velocidad_ok(medido, plan),
            "paso_cubierto": "test_velocidad",
            "motivo": "velocidad_dentro_del_plan",
        }
    if clase == "aceptable":
        return {
            "accion": "ask",
            "mensaje": mensaje_velocidad_aceptable(medido, plan),
            "paso_cubierto": "test_velocidad",
            "motivo": "velocidad_aceptable_vs_plan",
        }
    return None
