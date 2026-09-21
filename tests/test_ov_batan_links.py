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


def test_ov_link_uri_cruda_como_botmaker():
    """jsat concatena path con ? literal; no percent-encode."""
    api = "https://ov.batan.coop/api"
    cel = "5492235402690"
    path = "pagar?useCustomer=true"
    url = f"{api}/ov/link?celular={cel}&path={path}"
    assert "path=pagar?useCustomer=true" in url
    assert "%3F" not in url


def test_url_ov_para_key_un_solo_path(monkeypatch):
    from app.services import ov_batan as ov
    from app.services.ov_batan import url_ov_para_key

    calls: list[str] = []

    def _fake(path, celular="", db=None, celulares=None):
        calls.append(path)
        return f"https://ov.batan.coop/#/{path.split('?', 1)[0]}?tsid=t&user=549"

    monkeypatch.setattr(ov, "fast_or_public", _fake)
    link = url_ov_para_key("pagar", "5492235402690")
    assert "tsid=t" in link
    assert calls == [ov.PATH_PAGAR]



def test_link_ov_usable_exige_pedido_con_54():
    from app.services.ov_batan import _link_ov_usable

    ok = (
        "https://ov.batan.coop/#/pagar?useCustomer=true"
        "&tsid=abc&user=5492235402690"
    )
    assert _link_ov_usable(ok, celular_pedido="5492235402690") is True
    assert _link_ov_usable(ok, celular_pedido="92235402690") is False


def test_resolver_celular_app_igual_portal():
    """App y portal: celular del padrón (BillTrack), mismo criterio OV."""
    from app.services.ov_batan import candidatos_celular_ov

    abo = SimpleNamespace(telefono_e164="5492235402690", linea_msisdn="")
    assert candidatos_celular_ov(abo, canal="app") == ["5492235402690"]
    assert candidatos_celular_ov(abo, canal="web") == ["5492235402690"]
    assert resolver_celular_ov(abo, canal="app") == "5492235402690"


def test_candidatos_rechaza_portal_dni_sintetico():
    """portal{dni} no debe mandarse a /ov/link (quedaba el DNI como «celular»)."""
    from app.services.ov_batan import candidatos_celular_ov

    abo = SimpleNamespace(telefono_e164="", linea_msisdn="", id="", dni="24914867")
    assert (
        candidatos_celular_ov(
            abo, canal="app", wa_id="portal24914867", telefono_hilo="portal24914867"
        )
        == []
    )


def test_resolver_celular_portal_usa_hilo_real():
    """Tras login portal el hilo con MSISDN BillTrack sí cuenta."""
    from app.services.ov_batan import candidatos_celular_ov

    abo = SimpleNamespace(telefono_e164="", linea_msisdn="", id="", dni="")
    assert candidatos_celular_ov(
        abo, canal="web", wa_id="", telefono_hilo="5492235551234"
    ) == ["5492235551234"]
    assert candidatos_celular_ov(
        abo, canal="web", wa_id="", telefono_hilo="guestabcdef"
    ) == []
    assert candidatos_celular_ov(
        abo, canal="app", wa_id="", telefono_hilo="5492235551234"
    ) == ["5492235551234"]


def test_candidatos_app_usa_wa_hermano(monkeypatch):
    """Sin tel en padrón: reusa MSISDN del hilo WhatsApp del mismo abonado."""
    from app.services import ov_batan as ov
    from app.services.ov_batan import candidatos_celular_ov

    abo = SimpleNamespace(
        telefono_e164="",
        linea_msisdn="",
        id="abo-1",
        dni="24914867",
        organizacion_id="org-1",
    )
    monkeypatch.setattr(
        ov,
        "_celulares_wa_mismo_abonado",
        lambda _db, _id: ["5492235402690"],
    )
    cels = candidatos_celular_ov(
        abo, canal="app", telefono_hilo="portal24914867", db=object()
    )
    assert cels == ["5492235402690"]


def test_urls_ov_desde_contexto_no_pide_cinco_paths():
    """Saldo/plantilla usan URLs precomputadas o hash público; no /ov/link."""
    from app.services import diagnostico_n1 as d

    out = d._urls_ov_desde_contexto(
        "- ov_url_pagar: https://ov.batan.coop/#/pagar\n"
        "- ov_url_my: https://ov.batan.coop/#/my\n"
    )
    assert out["pagar"].endswith("#/pagar")
    assert out["my"].endswith("#/my")
    assert "tsid=" not in out["pagar"]
    ctx_auth = d._urls_ov_desde_contexto(
        "- ov_url_pagar: https://ov.batan.coop/handoff?c=opaque\n"
        "- ov_handoff_mode: authenticated\n"
    )
    assert ctx_auth["pagar"] == "https://ov.batan.coop/handoff?c=opaque"


def test_resolver_celular_wa_prioriza_hilo_botmaker():
    """WhatsApp: MSISDN del chat primero (como Botmaker)."""
    from app.services.ov_batan import candidatos_celular_ov

    abo = SimpleNamespace(telefono_e164="5492235551234", linea_msisdn="")
    assert (
        resolver_celular_ov(
            abo, canal="whatsapp", wa_id="5492235559999", telefono_hilo=""
        )
        == "5492235559999"
    )
    assert candidatos_celular_ov(
        abo, canal="whatsapp", wa_id="5492235559999", telefono_hilo=""
    ) == ["5492235559999", "5492235551234"]


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


def test_fast_or_public_un_solo_celular(monkeypatch):
    """LEGADO: un MSISDN, sin round-robin de variantes ni de otros números."""
    from app.services import ov_batan as ov

    clear_sid_cache()
    tried: list[str] = []

    def _fake_link(path, celular, db=None):
        tried.append(celular)
        return (
            "https://ov.batan.coop/#/pagar?useCustomer=true"
            f"&tsid=x&user={celular}"
        )

    monkeypatch.setattr(ov, "ov_configurado", lambda db=None: True)
    monkeypatch.setattr(ov, "get_fast_link", _fake_link)
    link = fast_or_public(
        PATH_PAGAR,
        "5492235551234",
        db=None,
        celulares=["5491111111111", "5492222222222"],
    )
    assert "tsid=x" in link
    assert tried == ["5492235551234"]


def test_resolve_ov_abre_db_si_session_none(monkeypatch):
    """Sin Session explícita, igual lee platform settings (Admin), no solo env."""
    from app.services import ov_batan as ov

    calls: list[object] = []

    class _FakeSession:
        def close(self):
            calls.append("close")

    monkeypatch.setattr(
        "app.estate.database.get_session_factory",
        lambda: (lambda: _FakeSession()),
    )

    def _fake_resolve(db):
        calls.append(db)
        return {
            "enabled": True,
            "api_url": "https://ov.batan.coop/api",
            "public_url": "https://ov.batan.coop",
            "user": "u",
            "password": "p",
            "timeout": 20,
            "nota": "",
        }

    monkeypatch.setattr(
        "app.services.platform_settings.resolve_ov_batan",
        _fake_resolve,
    )
    cfg = ov.resolve_ov_batan(None)
    assert cfg["enabled"] is True
    assert any(isinstance(c, _FakeSession) for c in calls)
    assert "close" in calls


def test_mensaje_saldo_usa_urls_dinamicas():
    from app.services.eco_voice import mensaje_saldo_padron

    msg = mensaje_saldo_padron(
        0,
        pagar_url="https://ov.batan.coop/#/pagar?tsid=1&user=549",
        ov_url="https://ov.batan.coop/#/my?tsid=1&user=549",
    )
    assert "tsid=1" in msg
    assert "user=549" in msg
    assert "#/pagar?tsid=1" in msg
    assert "#/my?tsid=1" in msg


def test_mensaje_factura_publico_pide_identificarse():
    from app.services.diagnostico_n1 import _mensaje_envio_factura_ov

    msg = _mensaje_envio_factura_ov(
        saldo=None,
        contexto_abonado="CONTEXTO\n- ov_url_my: https://ov.batan.coop/#/my\n",
    )
    assert "https://ov.batan.coop/#/my" in msg
    assert "identificarte" in msg.lower()
    assert "acceso con tu celular" not in msg.lower()


def test_mensaje_factura_auth_no_vende_celular():
    from app.services.diagnostico_n1 import _mensaje_envio_factura_ov

    msg = _mensaje_envio_factura_ov(
        saldo=None,
        contexto_abonado=(
            "CONTEXTO\n- ov_url_my: https://ov.batan.coop/handoff?c=opaque\n"
            "- ov_handoff_mode: authenticated\n"
        ),
    )
    assert "https://ov.batan.coop/handoff?c=opaque" in msg
    assert "acceso con tu celular" not in msg.lower()


def test_plantilla_pago_ctx_inyecta_pagar():
    from app.services.diagnostico_n1 import _plantilla_pago_ctx

    txt = _plantilla_pago_ctx(
        "- ov_url_pagar: https://ov.batan.coop/fast/pagar-x\n"
        "- ov_url_my: https://ov.batan.coop/fast/my-x\n"
    )
    assert "https://ov.batan.coop/fast/pagar-x" in txt
    assert "https://ov.batan.coop/fast/my-x" in txt
