"""Barrita didáctica de potencia/señal para WhatsApp y chat N1.

WhatsApp no pinta gráficos: cuadraditos = escala, círculo = dónde está el valor
(verde ideal, naranja regular, rojo fuera de rango). El portal reemplaza este
bloque por un medidor CSS si ve el prefijo 📊.
"""

from __future__ import annotations

_RED_SQ = "🟥"
_ORANGE_SQ = "🟧"
_GREEN_SQ = "🟩"
_RED_DOT = "🔴"
_ORANGE_DOT = "🟠"
_GREEN_DOT = "🟢"

# GPON RX (dBm): histograma TR-069 Batán (verde ≈ -24…-16).
_OPTICA_MIN = -33.0
_OPTICA_MAX = -8.0
_OPTICA_CELLS = 13

# Radio UISP RSSI (dBm).
_RADIO_MIN = -90.0
_RADIO_MAX = -40.0
_RADIO_CELLS = 11


def _clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


def _idx(valor: float, vmin: float, vmax: float, n: int) -> int:
    if vmax <= vmin or n <= 1:
        return 0
    t = (_clamp(valor, vmin, vmax) - vmin) / (vmax - vmin)
    return int(round(t * (n - 1)))


def color_optica_didactica(dbm: float) -> str:
    """red | orange | green según umbrales TR-069 (no cambia el triage de visita)."""
    if dbm <= -27.0 or dbm >= -12.0:
        return "red"
    if dbm <= -25.0 or dbm >= -15.0:
        return "orange"
    return "green"


def color_radio_didactica(dbm: float) -> str:
    if dbm < -75.0:
        return "red"
    if dbm < -65.0:
        return "orange"
    return "green"


def _cuadrado(color: str) -> str:
    if color == "green":
        return _GREEN_SQ
    if color == "orange":
        return _ORANGE_SQ
    return _RED_SQ


def _circulo(color: str) -> str:
    if color == "green":
        return _GREEN_DOT
    if color == "orange":
        return _ORANGE_DOT
    return _RED_DOT


def etiqueta_zona_optica(dbm: float) -> str:
    color = color_optica_didactica(dbm)
    if color == "green":
        return "zona verde (ideal)"
    if color == "orange":
        return "zona naranja (regular, al límite)"
    if dbm >= -12.0:
        return "zona roja (muy fuerte / saturada)"
    return "zona roja (muy floja)"


def etiqueta_zona_radio(dbm: float) -> str:
    color = color_radio_didactica(dbm)
    if color == "green":
        return "zona verde (buena)"
    if color == "orange":
        return "zona naranja (regular, al límite)"
    return "zona roja (floja)"


def veredicto_optica(dbm: float | None) -> str:
    """Frase corta para el cuerpo del mensaje (bien / regular / mal)."""
    if dbm is None:
        return ""
    color = color_optica_didactica(dbm)
    if color == "green":
        return "se ve bien"
    if color == "orange":
        return "está regular (al límite)"
    if dbm >= -12.0:
        return "está muy fuerte (saturada)"
    return "está baja"


def veredicto_radio(dbm: float | None) -> str:
    if dbm is None:
        return ""
    color = color_radio_didactica(dbm)
    if color == "green":
        return "se ve bien"
    if color == "orange":
        return "está regular (al límite)"
    return "está baja"


def _pintar_barra(
    valor: float,
    *,
    vmin: float,
    vmax: float,
    n: int,
    color_fn,
) -> str:
    here = _idx(valor, vmin, vmax, n)
    step = (vmax - vmin) / n
    yo = color_fn(valor)
    cells: list[str] = []
    for i in range(n):
        mid = vmin + step * (i + 0.5)
        if i == here:
            cells.append(_circulo(yo))
        else:
            cells.append(_cuadrado(color_fn(mid)))
    return "".join(cells)


def bloque_potencia_onu(rx_dbm: float | None) -> str:
    """Bloque para pegar en el mensaje N1 (fibra). Vacío si no hay RX."""
    if rx_dbm is None:
        return ""
    color = color_optica_didactica(rx_dbm)
    barra = _pintar_barra(
        rx_dbm,
        vmin=_OPTICA_MIN,
        vmax=_OPTICA_MAX,
        n=_OPTICA_CELLS,
        color_fn=color_optica_didactica,
    )
    return (
        f"📊 Potencia de tu cajita: {rx_dbm:.1f} dBm  {_circulo(color)} {etiqueta_zona_optica(rx_dbm)}\n"
        f"{barra}\n"
        "floja ←—— ideal ——→ fuerte"
    )


def bloque_senal_antena(signal_dbm: float | None) -> str:
    """Bloque para pegar en el mensaje N1 (radio). Vacío si no hay RSSI."""
    if signal_dbm is None:
        return ""
    color = color_radio_didactica(signal_dbm)
    barra = _pintar_barra(
        signal_dbm,
        vmin=_RADIO_MIN,
        vmax=_RADIO_MAX,
        n=_RADIO_CELLS,
        color_fn=color_radio_didactica,
    )
    return (
        f"📊 Señal de tu antena: {signal_dbm:.0f} dBm  {_circulo(color)} {etiqueta_zona_radio(signal_dbm)}\n"
        f"{barra}\n"
        "floja ←——————→ buena"
    )


def anexar_antes_de_preguntas(mensaje: str, bloque: str) -> str:
    """Inserta la barrita antes del primer ¿…? para no tapar las preguntas."""
    msg = (mensaje or "").strip()
    extra = (bloque or "").strip()
    if not msg:
        return extra
    if not extra:
        return msg
    idx = msg.find("¿")
    if idx < 0:
        return f"{msg}\n{extra}"
    cabeza = msg[:idx].rstrip()
    cola = msg[idx:].lstrip()
    return f"{cabeza}\n{extra}\n{cola}"
