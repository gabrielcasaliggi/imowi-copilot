"""F2: deep-links Oficina Virtual por celular (multi-canal)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.ov_batan import (
    PATH_MY,
    PATH_PAGAR,
    _response_json,
    clear_sid_cache,
    fast_or_public,
    public_url,
    resolver_celular_ov,
    urls_ov_gestiones,
)


def test_response_json_tolera_latin1_con_o_acento():
    """OV a veces responde Latin-1; 0xf3 = ó (p.ej. 'sesión')."""
    body = b'{"status":"OK","result":{"sid":"abc","msg":"Sesi\xf3n activa"}}'
    r = MagicMock()
    r.content = body
    r.charset_encoding = None
    r.encoding = "utf-8"
    data = _response_json(r)
    assert data["status"] == "OK"
    assert data["result"]["sid"] == "abc"
    assert "ó" in data["result"]["msg"]


def test_response_json_utf8_sigue_ok():
    body = b'{"status":"OK","result":{"sid":"xyz"}}'
    r = MagicMock()
    r.content = body
    r.charset_encoding = "utf-8"
    r.encoding = "utf-8"
    assert _response_json(r)["result"]["sid"] == "xyz"


def test_public_url_paths():
    assert public_url(PATH_PAGAR).endswith("#/pagar")
    assert public_url(PATH_MY).endswith("#/my")


def test_resolver_celular_prioriza_padron():
    abo = SimpleNamespace(telefono_e164="5492235551234", linea_msisdn="")
    assert resolver_celular_ov(abo, canal="web") == "5492235551234"
    assert resolver_celular_ov(abo, canal="telegram", telefono_hilo="999") == "5492235551234"


def test_resolver_celular_wa_fallback_hilo():
    assert (
        resolver_celular_ov(
            None, canal="whatsapp", wa_id="5492235559999", telefono_hilo=""
        )
        == "5492235559999"
    )
    assert resolver_celular_ov(None, canal="telegram", telefono_hilo="12345") == ""


def test_urls_sin_api_son_publicas(monkeypatch):
    from app.services import ov_batan as ov

    monkeypatch.setattr(ov, "ov_configurado", lambda db=None: False)
    urls = urls_ov_gestiones("5492235551234", db=None)
    assert "#/pagar" in urls["pagar"]
    assert "#/my" in urls["my"]
    assert "#/talon-de-pago" in urls["talon"]


def test_fast_or_public_usa_link_api(monkeypatch):
    from app.services import ov_batan as ov

    clear_sid_cache()
    monkeypatch.setattr(ov, "ov_configurado", lambda db=None: True)
    monkeypatch.setattr(
        ov,
        "get_fast_link",
        lambda path, celular, db=None: f"https://ov.batan.coop/fast/{path.split('?')[0]}",
    )
    link = fast_or_public(PATH_PAGAR, "5492235551234", db=None)
    assert link.startswith("https://ov.batan.coop/fast/pagar")


def test_mensaje_factura_usa_my_cuando_hay_celular(monkeypatch):
    from app.services.diagnostico_n1 import _mensaje_envio_factura_ov

    monkeypatch.setattr(
        "app.services.ov_batan.urls_ov_gestiones",
        lambda celular="", db=None: {
            "pagar": "https://ov.batan.coop/fast/pagar",
            "my": "https://ov.batan.coop/fast/my",
            "talon": "https://ov.batan.coop/fast/talon",
            "pack": "https://ov.batan.coop/fast/pack",
            "portabilidad": "https://ov.batan.coop/fast/port",
            "home": "https://ov.batan.coop",
        },
    )
    msg = _mensaje_envio_factura_ov(
        saldo=None,
        contexto_abonado="CONTEXTO\n- celular_ov: 5492235551234\n",
    )
    assert "https://ov.batan.coop/fast/my" in msg
    assert "acceso con tu celular" in msg.lower()


def test_plantilla_pago_ctx_inyecta_pagar(monkeypatch):
    from app.services.diagnostico_n1 import _plantilla_pago_ctx

    monkeypatch.setattr(
        "app.services.ov_batan.urls_ov_gestiones",
        lambda celular="", db=None: {
            "pagar": "https://ov.batan.coop/fast/pagar-x",
            "my": "https://ov.batan.coop/fast/my-x",
            "talon": "",
            "pack": "",
            "portabilidad": "",
            "home": "https://ov.batan.coop",
        },
    )
    txt = _plantilla_pago_ctx("- celular_ov: 5492235551234\n")
    assert "https://ov.batan.coop/fast/pagar-x" in txt
    assert "https://ov.batan.coop/fast/my-x" in txt
