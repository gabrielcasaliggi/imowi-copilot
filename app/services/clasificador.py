"""Motor de decisión N1 / N2 / Proveedor — reglas determinísticas antes de IA."""

from __future__ import annotations

from app.domain.escalamiento import detectar_escalamiento
from app.domain.taxonomia import (
    AccionClasificacion,
    CARRIER_KEYWORDS,
    CategoriaIncidente,
    DestinoTicket,
    NivelTicket,
    PROVEEDORES,
    ResultadoClasificacion,
    inferir_categoria,
)


def _datos_faltantes(datos_triaje: dict) -> list[str]:
    faltan = []
    if not datos_triaje.get("linea"):
        faltan.append("linea")
    if not datos_triaje.get("sintoma"):
        faltan.append("sintoma")
    return faltan


def _pasos_kb(kb_resultado: dict) -> list[str]:
    pasos = []
    for art in kb_resultado.get("articulos", [])[:3]:
        contenido = art.get("contenido", "")
        for linea in contenido.split("\n"):
            l = linea.strip()
            if l.startswith(("-", "*", "1.", "2.", "3.")) or l.lower().startswith("paso"):
                pasos.append(l[:200])
            if len(pasos) >= 5:
                break
    if not pasos and kb_resultado.get("modo") == "resolucion":
        pasos.append("Seguir procedimiento de la KB antes de escalar.")
    return pasos


def clasificar_caso(
    datos_triaje: dict,
    diagnostico: dict,
    kb_resultado: dict,
    historial: list[dict],
    *,
    forzar_escalamiento: bool = False,
) -> ResultadoClasificacion:
    """Clasifica el caso operativo. Retorna decisión auditable."""
    faltantes = _datos_faltantes(datos_triaje)
    sintoma = (datos_triaje.get("sintoma") or "").lower()
    texto_completo = f"{sintoma} {diagnostico.get('diagnostico', '')}".lower()
    ficha = diagnostico.get("ficha_jsc") or {}
    categoria_diag = diagnostico.get("categoria", "General")
    cat = inferir_categoria(texto_completo, categoria_diag)
    categoria_nombre = cat.nombre if cat else categoria_diag

    evidencia: list[str] = []
    if diagnostico.get("anomalia_red"):
        evidencia.append(f"Anomalía en {diagnostico.get('elemento_afectado', 'red')}")
    if ficha.get("estado_linea") == "Suspendida":
        evidencia.append("Línea suspendida en JSC")
    if ficha.get("estado_cuenta") not in ("Al día", "OK", ""):
        evidencia.append(f"Cuenta: {ficha.get('estado_cuenta')}")
    if kb_resultado.get("encontrado"):
        evidencia.append(f"KB: {kb_resultado.get('titulo_principal', 'artículo aplicable')}")

    # Regla 1: datos mínimos
    if faltantes and not forzar_escalamiento:
        return ResultadoClasificacion(
            accion=AccionClasificacion.PEDIR_DATOS,
            nivel=NivelTicket.N1,
            destino=DestinoTicket.COOPERATIVA,
            categoria=categoria_nombre,
            regla_aplicada="datos_minimos",
            datos_faltantes=faltantes,
            evidencia=evidencia,
        )

    # Regla 2: cuenta suspendida / deuda → N1, no proveedor
    if ficha.get("estado_linea") == "Suspendida" or (
        ficha.get("estado_cuenta") and ficha.get("estado_cuenta") not in ("Al día", "OK")
    ):
        if not forzar_escalamiento and not detectar_escalamiento(historial):
            return ResultadoClasificacion(
                accion=AccionClasificacion.RESOLVER_N1,
                nivel=NivelTicket.N1,
                destino=DestinoTicket.COOPERATIVA,
                categoria="Facturación / Cuenta",
                regla_aplicada="cuenta_suspendida",
                motivo_escalamiento="Verificar estado de cuenta antes de escalar a red o proveedor",
                pasos_n1=[
                    "Confirmar estado de cuenta en JSC",
                    "Informar al abonado si hay deuda o suspensión administrativa",
                    "Reactivar línea si corresponde antes de troubleshooting técnico",
                ],
                evidencia=evidencia,
            )

    # Regla 3: anomalía de red → N2
    if diagnostico.get("anomalia_red_correlacionada") or diagnostico.get("anomalia_red"):
        return ResultadoClasificacion(
            accion=AccionClasificacion.CREAR_TICKET_N2,
            nivel=NivelTicket.N2,
            destino=DestinoTicket.IMOWI_NOC,
            proveedor=PROVEEDORES["imowi_noc"],
            categoria="Red / Core",
            regla_aplicada="anomalia_red_correlacionada",
            motivo_escalamiento=f"Incidencia regional en {diagnostico.get('elemento_afectado', 'infraestructura')}",
            evidencia=evidencia,
            confianza=0.95,
        )

    kb_modo = kb_resultado.get("modo", "escalamiento")
    kb_encontrado = kb_resultado.get("encontrado", False)
    escalado = forzar_escalamiento or detectar_escalamiento(historial)
    triaje_completo = datos_triaje.get("completo", False)

    # Regla 4: KB con resolución y sin escalamiento → N1
    if kb_encontrado and kb_modo == "resolucion" and not escalado:
        return ResultadoClasificacion(
            accion=AccionClasificacion.RESOLVER_N1,
            nivel=NivelTicket.N1,
            destino=DestinoTicket.COOPERATIVA,
            categoria=categoria_nombre,
            regla_aplicada="kb_resolucion",
            pasos_n1=_pasos_kb(kb_resultado),
            evidencia=evidencia,
        )

    # Regla 5: categoría proveedor con datos completos. En demo no se integra
    # con terceros: se registra como ticket N2 con proveedor sugerido.
    if cat and cat.nivel_default == NivelTicket.PROVEEDOR and (triaje_completo or escalado):
        proveedor = _resolver_proveedor(cat, texto_completo, ficha)
        return ResultadoClasificacion(
            accion=AccionClasificacion.CREAR_TICKET_N2,
            nivel=NivelTicket.N2,
            destino=cat.destino_default,
            proveedor=proveedor,
            categoria=cat.nombre,
            regla_aplicada="categoria_proveedor" if not escalado else "escalamiento_explicito",
            motivo_escalamiento="Caso técnico que requiere gestión N2 y posible proveedor externo",
            evidencia=evidencia,
        )

    # Regla 6: escalamiento explícito o triaje completo sin KB resolución.
    # La demo debe decidir N1/N2 sin depender de una ticketera externa.
    if escalado or (triaje_completo and not kb_encontrado):
        regla = "escalamiento_explicito" if escalado else "triaje_completo_n2"
        if cat and cat.nivel_default == NivelTicket.N2:
            accion = AccionClasificacion.CREAR_TICKET_N2
            destino = cat.destino_default
            nivel = NivelTicket.N2
            proveedor = PROVEEDORES["imowi_noc"]
        elif escalado:
            accion = AccionClasificacion.CREAR_TICKET_N2
            destino = DestinoTicket.IMOWI_NOC
            nivel = NivelTicket.N2
            proveedor = PROVEEDORES["imowi_noc"]
        else:
            accion = AccionClasificacion.CREAR_TICKET_N1
            destino = DestinoTicket.COOPERATIVA
            nivel = NivelTicket.N1
            proveedor = ""
            regla = "ticket_n1_demo"

        return ResultadoClasificacion(
            accion=accion,
            nivel=nivel,
            destino=destino,
            proveedor=proveedor,
            categoria=categoria_nombre,
            regla_aplicada=regla,
            motivo_escalamiento=(
                "Escalamiento solicitado o caso técnico N2"
                if nivel == NivelTicket.N2
                else "Caso completo no resuelto por KB; registrar seguimiento N1"
            ),
            evidencia=evidencia,
        )

    # Regla 7: default N1
    return ResultadoClasificacion(
        accion=AccionClasificacion.RESOLVER_N1,
        nivel=NivelTicket.N1,
        destino=DestinoTicket.COOPERATIVA,
        categoria=categoria_nombre,
        regla_aplicada="default_n1",
        pasos_n1=_pasos_kb(kb_resultado) or ["Continuar relevamiento según manual de la cooperativa"],
        evidencia=evidencia,
    )


def _resolver_proveedor(cat: CategoriaIncidente, texto: str, ficha: dict) -> str:
    if cat.destino_default == DestinoTicket.CARRIER:
        for kw in CARRIER_KEYWORDS:
            if kw in texto:
                return f"Carrier ({kw.title()})"
        return PROVEEDORES["carrier"]
    if cat.destino_default == DestinoTicket.SIM_PROVIDER:
        iccid = ficha.get("iccid", "")
        if iccid:
            return f"{PROVEEDORES['fabricante_sim']} (ICCID {iccid[:8]}…)"
        return PROVEEDORES["fabricante_sim"]
    return PROVEEDORES.get(cat.proveedor_tipo, cat.proveedor_tipo or "Proveedor externo")


def resultado_a_dict(r: ResultadoClasificacion) -> dict:
    return {
        "accion": r.accion.value,
        "nivel": r.nivel.value if r.nivel else None,
        "destino": r.destino.value if r.destino else None,
        "proveedor": r.proveedor,
        "categoria": r.categoria,
        "motivo_escalamiento": r.motivo_escalamiento,
        "regla_aplicada": r.regla_aplicada,
        "confianza": r.confianza,
        "datos_faltantes": r.datos_faltantes,
        "pasos_n1": r.pasos_n1,
        "evidencia": r.evidencia,
    }
