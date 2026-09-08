"""Comprensión de gestos Oficina Virtual (sin menú estático)."""

from __future__ import annotations

from app.services.ov_intencion import (
    GESTO_ACLARAR,
    GESTO_PACK,
    GESTO_PAGAR,
    GESTO_PORTABILIDAD,
    GESTO_TALON,
    GESTO_VER_FACTURA,
    clasificar_gesto_ov,
    mensaje_gesto_ov,
    pregunta_aclaracion_ov,
)


def test_gesto_ver_factura():
    assert clasificar_gesto_ov("mandame la factura") == GESTO_VER_FACTURA
    assert clasificar_gesto_ov("quiero descargar la factura") == GESTO_VER_FACTURA
    assert clasificar_gesto_ov("quiero mi factura") == GESTO_VER_FACTURA
    assert clasificar_gesto_ov("Quiero mi factura") == GESTO_VER_FACTURA
    assert clasificar_gesto_ov("Podes dármela vos?") == GESTO_VER_FACTURA
    assert clasificar_gesto_ov("ver mis facturas") == GESTO_VER_FACTURA
    assert clasificar_gesto_ov("pdf de la boleta") == GESTO_VER_FACTURA


def test_gesto_pagar():
    assert clasificar_gesto_ov("quiero pagar") == GESTO_PAGAR
    assert clasificar_gesto_ov("dónde pago la factura") == GESTO_PAGAR
    assert clasificar_gesto_ov("link para pagar") == GESTO_PAGAR


def test_gesto_talon_antes_que_pagar_generico():
    assert clasificar_gesto_ov("generame el QR de pago") == GESTO_TALON
    assert clasificar_gesto_ov("necesito el talón de pago") == GESTO_TALON


def test_gesto_pack_y_portabilidad():
    assert clasificar_gesto_ov("quiero comprar un pack de datos") == GESTO_PACK
    assert clasificar_gesto_ov("consultar estado de portabilidad") == GESTO_PORTABILIDAD


def test_gesto_aclarar_sin_menu_fijo():
    assert clasificar_gesto_ov("oficina virtual") == GESTO_ACLARAR
    assert clasificar_gesto_ov("factura") == GESTO_ACLARAR
    q = pregunta_aclaracion_ov().lower()
    assert "1)" not in q and "2)" not in q
    assert "factura" in q and "pagar" in q


def test_gesto_none_deja_flujo_saldo():
    assert clasificar_gesto_ov("cuánto debo") is None
    assert clasificar_gesto_ov("cuánto debo en mi factura") is None
    assert clasificar_gesto_ov("ya pagué y no se refleja") is None
    assert clasificar_gesto_ov("hola") is None


def test_mensaje_gesto_incluye_link():
    urls = {
        "pagar": "https://ov.example/pagar",
        "my": "https://ov.example/my",
        "talon": "https://ov.example/talon",
        "pack": "https://ov.example/pack",
        "portabilidad": "https://ov.example/port",
        "home": "https://ov.example",
    }
    msg = mensaje_gesto_ov(GESTO_VER_FACTURA, urls)
    assert "https://ov.example/my" in msg
    assert "no te adjunto el PDF" in msg.lower() or "no te adjunto el pdf" in msg.lower()
    msg_p = mensaje_gesto_ov(GESTO_PAGAR, urls, prefijo="Saldo: $100\n")
    assert "Saldo: $100" in msg_p
    assert "https://ov.example/pagar" in msg_p


def test_facturacion_deterministica_usa_gesto(monkeypatch):
    from app.services import diagnostico_n1 as d

    monkeypatch.setattr(
        d,
        "_urls_ov_desde_contexto",
        lambda _c: {
            "pagar": "https://ov.fast/pagar",
            "my": "https://ov.fast/my",
            "talon": "https://ov.fast/talon",
            "pack": "https://ov.fast/pack",
            "portabilidad": "https://ov.fast/port",
            "home": "https://ov.batan.coop",
        },
    )
    out = d._facturacion_deterministica(
        "quiero mi factura",
        contexto_abonado="CONTEXTO\n- modo: identificado\n- deuda_monto: 10\n- celular_ov: 5492235551234\n",
        historial_mensajes=[],
    )
    assert out is not None
    assert out["motivo"] == "facturacion_ov_ver_factura"
    assert "https://ov.fast/my" in (out["mensaje"] or "")

    out2 = d._facturacion_deterministica(
        "Podes dármela vos?",
        contexto_abonado="CONTEXTO\n- modo: identificado\n- deuda_monto: 10\n- celular_ov: 5492235551234\n",
        historial_mensajes=[],
    )
    assert out2 is not None
    assert out2["motivo"] == "facturacion_ov_ver_factura"
    assert "https://ov.fast/my" in (out2["mensaje"] or "")
