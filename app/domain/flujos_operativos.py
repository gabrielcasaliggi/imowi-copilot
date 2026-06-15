"""Flujos operativos N1 por categoría — pasos explícitos y auditables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PasoFlujo:
    id: str
    mensaje: str


CategoriaFlujo = str  # roaming | datos | senal | sim | general

CATEGORIA_LABELS: dict[str, str] = {
    "roaming": "Roaming internacional",
    "datos": "Datos móviles",
    "senal": "Señal y cobertura",
    "sim": "SIM / chip",
    "general": "General",
}

PASO_LABELS: dict[str, str] = {
    "roaming_datos_moviles": "1. Datos e itinerancia en equipo",
    "roaming_apn": "2. APN de roaming",
    "roaming_jsc": "3. Roaming en JSC",
    "roaming_activar_jsc": "4. Activar roaming en JSC",
    "roaming_reinicio": "5. Reinicio / modo avión",
    "roaming_llamada_prueba": "6. Prueba de llamada",
    "roaming_cerrar_seguimiento": "7. Seguimiento NOC",
    "datos_moviles": "1. Datos móviles activos",
    "datos_apn": "2. Configurar APN",
    "datos_reinicio": "3. Reinicio de red",
    "datos_llamada_prueba": "4. Prueba de llamadas",
    "datos_sim_descarte": "5. Descarte SIM",
    "datos_cerrar_seguimiento": "6. Seguimiento NOC",
    "senal_zona": "1. Alcance geográfico",
    "senal_llamadas": "2. Prueba de llamadas",
    "senal_reinicio": "3. Reinicio / modo avión",
    "senal_ticket_noc": "4. Escalar a NOC",
    "senal_cerrar_seguimiento": "5. Seguimiento NOC",
    "general_triaje": "1. Confirmar alcance",
    "sim_evaluar": "1. Evaluar SIM",
}

HECHOS_RESUMEN = (
    "datos_moviles_activos",
    "apn_configurado",
    "roaming_verificado",
    "roaming_jsc_inactivo",
    "roaming_activado_jsc",
    "reinicio_o_modo_avion",
    "llamadas_ok",
    "datos_ok",
    "zona_unica",
    "multiples_zonas",
    "sim_cambiada",
)


def detectar_categoria_flujo(sintoma: str, hechos: dict | None = None) -> CategoriaFlujo:
    h = hechos or {}
    if h.get("categoria_flujo") in ("roaming", "datos", "senal", "sim"):
        return h["categoria_flujo"]
    sint = (sintoma or "").lower()
    _paises_roaming = (
        "roaming",
        "brasil",
        "uruguay",
        "paraguay",
        "chile",
        "bolivia",
        "peru",
        "perú",
        "extranjero",
        "itinerancia",
        "argentina",
        "exterior",
        "fuera del pais",
        "fuera del país",
        "otro pais",
        "otro país",
        "saliendo de",
        "en el exterior",
    )
    if any(p in sint for p in _paises_roaming):
        return "roaming"
    if any(p in sint for p in ("datos", "navegar", "internet", "apn")):
        return "datos"
    if any(
        p in sint
        for p in (
            "señal",
            "senal",
            "cobertura",
            "servicio",
            "registra en la red",
            "registro en la red",
            "no se registra",
            "no registra",
            "sin red",
            "registra red",
            "registro de red",
            "no registra en",
        )
    ):
        return "senal"
    if any(p in sint for p in ("sim", "chip", "iccid", "esim", "e-sim")):
        return "sim"
    return "general"


def sintoma_cambio_categoria(sintoma_prev: str, sintoma_nuevo: str) -> bool:
    if not (sintoma_prev or "").strip() or not (sintoma_nuevo or "").strip():
        return False
    return detectar_categoria_flujo(sintoma_prev) != detectar_categoria_flujo(sintoma_nuevo)


def _pendiente_roaming(hechos: dict) -> PasoFlujo | None:
    if not hechos.get("datos_moviles_activos"):
        return PasoFlujo(
            "roaming_datos_moviles",
            "Verificar que datos móviles e itinerancia de datos estén activos en el equipo.",
        )
    if not hechos.get("apn_configurado"):
        return PasoFlujo(
            "roaming_apn",
            'Revisar el APN de datos para roaming (ej. "internet.coopbatan.ar") y probar navegación.',
        )
    if not hechos.get("roaming_verificado"):
        return PasoFlujo(
            "roaming_jsc",
            "Verificar en JSC que la línea tenga roaming internacional y datos roaming habilitados.",
        )
    if hechos.get("roaming_jsc_inactivo") and not hechos.get("roaming_activado_jsc"):
        return PasoFlujo(
            "roaming_activar_jsc",
            "Activar roaming internacional y datos roaming en JSC para la línea; "
            "después reiniciar el equipo y volver a probar navegación.",
        )
    if not hechos.get("reinicio_o_modo_avion"):
        return PasoFlujo(
            "roaming_reinicio",
            "Reiniciar el equipo o activar modo avión 10 segundos para forzar nuevo registro en red visitada.",
        )
    if hechos.get("llamadas_ok") is None:
        return PasoFlujo(
            "roaming_llamada_prueba",
            "Verificar si el equipo registra red visitada y puede cursar una llamada de prueba.",
        )
    return PasoFlujo(
        "roaming_cerrar_seguimiento",
        "Actualizar el ticket con las pruebas realizadas y mantener seguimiento NOC; "
        "no sumar más pruebas al cliente por ahora.",
    )


def _pendiente_datos(hechos: dict) -> PasoFlujo | None:
    if not hechos.get("datos_moviles_activos"):
        return PasoFlujo(
            "datos_moviles",
            "Verificar que los datos móviles estén activos y que el equipo no esté usando solo WiFi.",
        )
    if not hechos.get("apn_configurado"):
        return PasoFlujo(
            "datos_apn",
            'Revisar y configurar el APN de datos móviles (ej. "internet.coopbatan.ar").',
        )
    if not hechos.get("reinicio_o_modo_avion"):
        return PasoFlujo(
            "datos_reinicio",
            "Activar modo avión 10 segundos o reiniciar el equipo para renovar el registro de red.",
        )
    if hechos.get("llamadas_ok") is None:
        return PasoFlujo(
            "datos_llamada_prueba",
            "Verificar si la línea puede hacer y recibir llamadas; eso ayuda a separar voz de datos.",
        )
    if hechos.get("datos_ok") is False:
        return PasoFlujo(
            "datos_sim_descarte",
            "Recién como último descarte, evaluar probar otra SIM si las verificaciones simples no resolvieron.",
        )
    return PasoFlujo(
        "datos_cerrar_seguimiento",
        "Actualizar el ticket con las pruebas realizadas y mantener seguimiento NOC.",
    )


def _pendiente_senal(hechos: dict) -> PasoFlujo | None:
    if hechos.get("zona_unica") is None and hechos.get("multiples_zonas") is None:
        return PasoFlujo(
            "senal_zona",
            "Confirmar si el problema de señal ocurre en una sola zona o en varias ubicaciones.",
        )
    if hechos.get("llamadas_ok") is None:
        return PasoFlujo(
            "senal_llamadas",
            "Verificar si el cliente puede hacer y recibir llamadas de prueba.",
        )
    if not hechos.get("reinicio_o_modo_avion"):
        return PasoFlujo(
            "senal_reinicio",
            "Activar modo avión 10 segundos o reiniciar el equipo para forzar nuevo registro en la red.",
        )
    if hechos.get("multiples_zonas") or hechos.get("llamadas_ok") is False:
        return PasoFlujo(
            "senal_ticket_noc",
            "Escalar a NOC con línea, zonas afectadas, resultado de llamadas y hora aproximada del incidente.",
        )
    return PasoFlujo(
        "senal_cerrar_seguimiento",
        "Registrar pruebas realizadas y mantener seguimiento si el cliente vuelve a reportar pérdida de señal.",
    )


def _pendiente_general(hechos: dict) -> PasoFlujo | None:
    if hechos.get("alcance_confirmado"):
        return None
    return PasoFlujo(
        "general_triaje",
        "Confirmar zona, alcance del problema y si afecta señal, datos o solo llamadas.",
    )


def _pendiente_sim(hechos: dict) -> PasoFlujo | None:
    if not hechos.get("sim_cambiada"):
        return PasoFlujo(
            "sim_evaluar",
            "Verificar estado de la SIM en el equipo y, si corresponde, probar otra SIM como descarte.",
        )
    return None


_RESOLVERS: dict[CategoriaFlujo, Callable[[dict], PasoFlujo | None]] = {
    "roaming": _pendiente_roaming,
    "datos": _pendiente_datos,
    "senal": _pendiente_senal,
    "sim": _pendiente_sim,
    "general": _pendiente_general,
}


def resolver_paso_flujo(hechos: dict, sintoma: str = "") -> PasoFlujo | None:
    """Devuelve el paso operativo pendiente para la categoría detectada."""
    cat = detectar_categoria_flujo(sintoma, hechos)
    resolver = _RESOLVERS.get(cat)
    if resolver:
        paso = resolver(hechos)
        if paso is not None:
            return paso
    if (
        hechos.get("apn_configurado")
        and hechos.get("reinicio_o_modo_avion")
        and hechos.get("datos_moviles_activos")
        and hechos.get("datos_ok") is False
    ):
        return _pendiente_sim(hechos) or PasoFlujo(
            "datos_sim_descarte",
            "Recién como último descarte, evaluar probar otra SIM si las verificaciones simples no resolvieron.",
        )
    return None


def siguiente_paso_mensaje(hechos: dict, sintoma: str = "") -> str | None:
    paso = resolver_paso_flujo(hechos, sintoma)
    return paso.mensaje if paso else None


def _formato_hecho(clave: str, valor: Any) -> str:
    etiquetas = {
        "datos_moviles_activos": "datos_móviles",
        "apn_configurado": "apn",
        "roaming_verificado": "roaming_jsc",
        "roaming_jsc_inactivo": "roaming_off",
        "roaming_activado_jsc": "roaming_on",
        "reinicio_o_modo_avion": "reinicio",
        "llamadas_ok": "llamadas",
        "datos_ok": "navegación",
        "zona_unica": "zona_unica",
        "multiples_zonas": "varias_zonas",
        "sim_cambiada": "sim",
    }
    nombre = etiquetas.get(clave, clave)
    if valor is True:
        return f"{nombre}=ok"
    if valor is False:
        return f"{nombre}=falla"
    if valor is None:
        return f"{nombre}=?"
    return f"{nombre}={valor}"


def evaluar_flujo(hechos: dict, sintoma: str = "") -> dict:
    """Estado auditable del flujo para trazas y API."""
    cat = detectar_categoria_flujo(sintoma, hechos)
    paso = resolver_paso_flujo(hechos, sintoma)
    hechos_resumen = [
        _formato_hecho(k, hechos.get(k))
        for k in HECHOS_RESUMEN
        if k in hechos
    ]
    completado = paso is not None and paso.id.endswith("_cerrar_seguimiento")
    paso_id = paso.id if paso else None
    return {
        "categoria": cat,
        "categoria_label": CATEGORIA_LABELS.get(cat, cat.title()),
        "paso_id": paso_id,
        "paso_label": PASO_LABELS.get(paso_id, paso_id) if paso_id else None,
        "paso_mensaje": paso.mensaje if paso else None,
        "completado": completado,
        "hechos_resumen": hechos_resumen,
    }


def traza_flujo(hechos: dict, sintoma: str = "") -> str:
    ev = evaluar_flujo(hechos, sintoma)
    hechos_txt = ", ".join(ev["hechos_resumen"]) if ev["hechos_resumen"] else "sin hechos aún"
    paso = ev["paso_id"] or "completo"
    return f"📋 [Flujo Operativo]: {ev['categoria']} | paso={paso} | {hechos_txt}"
