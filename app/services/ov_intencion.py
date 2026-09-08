"""Comprensión de gestos OV: qué quiere hacer el abonado (sin menú estático).

Mapea lenguaje natural → path jsat-get-link-ov. Si la intención es de
oficina virtual pero ambigua, pide UNA aclaración corta.
"""

from __future__ import annotations

import re

# Gestos que disparan deep-link (o aclaración).
GESTO_VER_FACTURA = "ver_factura"
GESTO_PAGAR = "pagar"
GESTO_TALON = "talon"
GESTO_PACK = "pack"
GESTO_PORTABILIDAD = "portabilidad"
GESTO_ACLARAR = "aclarar"

_PATH_POR_GESTO = {
    GESTO_VER_FACTURA: "my",
    GESTO_PAGAR: "pagar",
    GESTO_TALON: "talon",
    GESTO_PACK: "pack",
    GESTO_PORTABILIDAD: "portabilidad",
}


def _norm(texto: str) -> str:
    t = (texto or "").lower().strip()
    t = (
        t.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    t = re.sub(r"[¡!¿?.,;:]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def clasificar_gesto_ov(texto: str) -> str | None:
    """Detecta el gesto OV del mensaje. None = no es un pedido de gestión OV.

    Orden: más específico primero (portabilidad/pack antes que pagar genérico).
    Si pregunta monto/saldo («cuánto me vino»), no captura: lo resuelve el flujo de saldo.
    """
    t = _norm(texto)
    if not t or len(t) > 280:
        return None

    pide_monto = any(
        k in t
        for k in (
            "cuanto",
            "cuánto",
            "debo",
            "saldo",
            "me vino",
            "vino en",
            "importe",
            "monto de",
            "cuanto me",
            "cuánto me",
        )
    )
    quiere_documento = any(
        k in t
        for k in (
            "descarg",
            "pdf",
            "copia de",
            "bajar la",
            "bajar factura",
            "ver la factura",
            "ver mi factura",
            "ver factura",
            "mandame la factura",
            "enviame la factura",
            "pasame la factura",
            "quiero mi factura",
            "quiero la factura",
            "quiero factura",
            "necesito mi factura",
            "necesito la factura",
            "necesito factura",
            "dame mi factura",
            "dame la factura",
            "dame la boleta",
            "darmela",
            "pasamela",
            "enviamela",
            "mandamela",
            "me la das",
            "me la pasas",
            "me la mandas",
            "me la envias",
            "podes darmela",
            "puedes darmela",
            "pasame la boleta",
            "enviame la boleta",
            "mandame la boleta",
        )
    )
    # «¿Cuánto me vino?» / saldo + web → flujo de saldo, no deep-link suelto.
    if pide_monto and not quiere_documento:
        return None

    # Portabilidad imowi
    if any(
        k in t
        for k in (
            "portabilidad",
            "porteabilidad",
            "estado de mi portacion",
            "estado de la portacion",
            "pase mi numero",
            "pase el numero",
            "porte mi linea",
        )
    ):
        return GESTO_PORTABILIDAD

    # Pack / bono de datos (compra en OV)
    if any(
        k in t
        for k in (
            "comprar pack",
            "comprar un pack",
            "comprar bono",
            "quiero un pack",
            "quiero pack",
            "cargar pack",
            "cargar un pack",
            "pack de datos",
            "pack datos",
            "bono de datos",
            "comprar datos",
            "recargar datos imowi",
        )
    ):
        return GESTO_PACK

    # Talón / cupón / QR para pagar (documento de pago)
    if any(
        k in t
        for k in (
            "talon de pago",
            "talon pago",
            "cupon de pago",
            "cupon pago",
            "generar qr",
            "generame el qr",
            "pasame el qr",
            "mandame el qr",
            "qr de pago",
            "qr para pagar",
            "codigo qr",
        )
    ):
        return GESTO_TALON

    # Ver / descargar factura o servicios en OV
    if quiere_documento or any(
        k in t
        for k in (
            "descargar factura",
            "descargar la factura",
            "descargar boleta",
            "bajar la factura",
            "bajar factura",
            "copia de factura",
            "copia de la factura",
            "copia de boleta",
            "pdf de la factura",
            "pdf factura",
            "ver mis servicios",
            "ver mis facturas",
            "mis facturas",
            "facturas en la ov",
            "facturas en ov",
        )
    ) or (
        any(k in t for k in ("factura", "boleta"))
        and any(
            k in t
            for k in (
                "ver",
                "descarg",
                "bajar",
                "copia",
                "pdf",
                "mandame",
                "enviame",
                "enviane",
                "pasame",
                "necesito la",
                "necesito mi",
                "quiero la",
                "quiero mi",
                "dame la",
                "dame mi",
                "darme la",
                "darme mi",
                "podes darme",
                "puedes darme",
            )
        )
    ):
        return GESTO_VER_FACTURA

    # Pedido pronominal («dámela vos») tras hablar de factura/boleta en el hilo.
    if any(
        k in t
        for k in (
            "darmela",
            "pasamela",
            "enviamela",
            "mandamela",
            "me la das",
            "me la pasas",
            "me la mandas",
            "me la envias",
            "podes darmela",
            "puedes darmela",
            "darmela vos",
            "pasamela vos",
        )
    ):
        return GESTO_VER_FACTURA

    # Pagar / abonar (sin talón explícito)
    if any(
        k in t
        for k in (
            "quiero pagar",
            "necesito pagar",
            "quiero abonar",
            "necesito abonar",
            "como pago",
            "como abonar",
            "donde pago",
            "para pagar",
            "para abonar",
            "pagar la factura",
            "pagar factura",
            "pagar la boleta",
            "abonar la factura",
            "abonar factura",
            "ir a pagar",
            "link de pago",
            "link para pagar",
            "web para abonar",
            "web para pagar",
        )
    ):
        return GESTO_PAGAR

    # Quiere la OV / gestiones pero sin decir qué
    if any(
        k in t
        for k in (
            "oficina virtual",
            "ov batan",
            "ov.batan",
            "mi cuenta ov",
            "entrar a la ov",
            "entrar a ov",
            "gestiones online",
            "autogestion",
            "auto gestion",
        )
    ) and not any(k in t for k in ("aviso de pago", "ya pague", "ya pagué")):
        return GESTO_ACLARAR

    # «¿Qué opciones tengo de facturación?»
    if any(
        k in t
        for k in (
            "opciones",
            "que opciones",
            "que puedo hacer",
            "que gestiones",
            "menu de factur",
            "parte de factur",
        )
    ) and any(
        k in t
        for k in (
            "factura",
            "factur",
            "pago",
            "deuda",
            "boleta",
            "ov",
            "oficina",
        )
    ):
        return GESTO_ACLARAR

    # “factura” / “boleta” sueltos en contexto de gestión (sin monto/saldo)
    if re.fullmatch(r"(la )?(factura|boleta|facturas|boletas)", t):
        return GESTO_ACLARAR

    return None


def path_key_para_gesto(gesto: str) -> str | None:
    return _PATH_POR_GESTO.get(gesto)


def pregunta_aclaracion_ov() -> str:
    """Una sola pregunta natural — no menú numerado estático."""
    return (
        "Dale. ¿Qué necesitás hacer: ver o descargar la factura, pagar, "
        "generar el talón/QR, o es otra gestión (pack o portabilidad)?"
    )


def mensaje_gesto_ov(
    gesto: str,
    urls: dict[str, str],
    *,
    prefijo: str = "",
) -> str:
    """Arma la respuesta con el deep-link correspondiente."""
    pref = (prefijo or "").strip()
    if pref and not pref.endswith("\n"):
        pref = pref + "\n"

    my = (urls.get("my") or urls.get("home") or "https://ov.batan.coop").strip()
    pagar = (urls.get("pagar") or my).strip()
    talon = (urls.get("talon") or pagar).strip()

    if gesto == GESTO_ACLARAR:
        return (
            f"{pref}"
            "Estas son las gestiones de facturación en la Oficina Virtual:\n"
            f"• Ver / descargar factura:\n{my}\n"
            f"• Pagar:\n{pagar}\n"
            f"• Talón / QR:\n{talon}\n"
            "¿Cuál necesitás? También aviso de pago, pack de datos o portabilidad."
        )

    key = path_key_para_gesto(gesto)
    link = (urls.get(key or "") or urls.get("home") or "https://ov.batan.coop").strip()

    if gesto == GESTO_VER_FACTURA:
        return (
            f"{pref}"
            "Todavía no te adjunto el PDF por este chat, pero podés verla y "
            "descargarla acá:\n"
            f"{link}\n"
            "¿Pudiste abrirla? Si el link no entra o ves otra cuenta, avisame."
        )
    if gesto == GESTO_PAGAR:
        return (
            f"{pref}"
            "Abonar tu factura\n"
            f"Ingresá al siguiente link\n{link}\n"
            "¿Pudiste pagar?"
        )
    if gesto == GESTO_TALON:
        return (
            f"{pref}"
            "Generá el talón / QR de pago acá:\n"
            f"{link}\n"
            "¿Te sirvió?"
        )
    if gesto == GESTO_PACK:
        return (
            f"{pref}"
            "Para comprar pack de datos imowi (con usuario de Oficina Virtual):\n"
            f"{link}\n"
            "¿Pudiste cargar el pack?"
        )
    if gesto == GESTO_PORTABILIDAD:
        return (
            f"{pref}"
            "Consultá el estado de tu portabilidad imowi acá:\n"
            f"{link}\n"
            "¿Encontraste el estado?"
        )
    return f"{pref}{pregunta_aclaracion_ov()}"
