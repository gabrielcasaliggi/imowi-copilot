"""OV-03 — identidad DNI, AUTH vs PUBLIC, login JSON, allowlists."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from app.services.ov_handoff import (
    MODE_AUTHENTICATED,
    MODE_FAILED,
    MODE_PUBLIC,
    canonical_dni,
    destination_for_intent,
    identity_reason,
    reset_handoff_metrics,
    resolve_handoff,
    snapshot_handoff_metrics,
    url_host_allowed,
)


def _abo(**kwargs):
    defaults = {
        "id": "abo-1",
        "dni": "30111222",
        "telefono_e164": "5492235402690",
        "organizacion_id": "org-1",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_ov3_01_abonado_con_dni_usa_dni():
    assert canonical_dni(_abo()) == "30111222"
    assert canonical_dni(_abo(dni="30.111.222")) == "30111222"


def test_ov3_02_sin_abonado_no_auth():
    out = resolve_handoff("invoice", None)
    assert out.mode == MODE_PUBLIC
    assert out.authenticated is False
    assert out.reason == "not_identified"
    assert "tsid=" not in (out.url or "").lower()


def test_ov3_03_abonado_sin_dni_no_auth():
    assert canonical_dni(_abo(dni="")) == ""
    out = resolve_handoff("pay", _abo(dni=""))
    assert out.mode == MODE_PUBLIC
    assert out.reason == "no_dni"
    assert out.authenticated is False


def test_ov3_04_wa_multiples_cuentas_ambiguous():
    assert identity_reason(None, phone_candidates=[{"dni": "1"}, {"dni": "2"}]) == (
        "identity_ambiguous"
    )
    out = resolve_handoff(
        "pay",
        None,
        phone_candidates=[{"dni": "1"}, {"dni": "2"}],
    )
    assert out.reason == "identity_ambiguous"
    assert out.mode == MODE_PUBLIC
    assert out.authenticated is False


def test_ov3_05_no_round_robin_celulares(monkeypatch):
    from app.services import ov_batan as ov

    calls: list[str] = []

    def _fake_link(path, celular, db=None):
        calls.append(celular)
        return None

    monkeypatch.setattr(ov, "ov_configurado", lambda db=None: True)
    monkeypatch.setattr(ov, "get_fast_link", _fake_link)
    ov.fast_or_public(
        ov.PATH_PAGAR,
        "5492235551234",
        celulares=["5491111111111", "5492222222222"],
    )
    assert calls == ["5492235551234"]


def test_ov3_06_07_session_login_post_json(monkeypatch):
    from app.services import ov_batan as ov

    ov.clear_sid_cache()
    captured: dict = {}

    class _Resp:
        is_success = True
        content = b'{"status":"OK","result":{"sid":"sid-tecnico"}}'
        charset_encoding = "utf-8"
        encoding = "utf-8"

        def raise_for_status(self):
            return None

    def _post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers")
        return _Resp()

    monkeypatch.setattr(ov.httpx, "post", _post)
    sid = ov._ensure_sid(
        {
            "api_url": "https://ov.batan.coop/api",
            "user": "svc",
            "password": "s3cret-value",
            "timeout": 5,
        }
    )
    assert sid == "sid-tecnico"
    assert captured["url"] == "https://ov.batan.coop/api/session/login"
    assert "password=" not in captured["url"]
    assert "user=" not in captured["url"].split("login", 1)[-1]
    assert captured["json"] == {
        "user": "svc",
        "password": "s3cret-value",
        "external": True,
    }
    ov.clear_sid_cache()


def test_ov3_08_sid_tecnico_no_en_outcome():
    """El sid de servicio no forma parte del resultado entregable al abonado."""
    out = resolve_handoff("pay", _abo())
    blob = f"{out.mode} {out.url} {out.reason} {out.destination}"
    assert "sid" not in blob.lower()
    assert "sid-tecnico" not in blob


def test_ov3_09_13_destinations_and_host():
    assert destination_for_intent("invoice") == "my"
    assert destination_for_intent("pay") == "pagar"
    assert destination_for_intent("payment_slip") == "talon-de-pago"
    assert destination_for_intent("https://evil.example") is None
    assert destination_for_intent("../../etc") is None
    bad = resolve_handoff("https://evil.example", _abo())
    assert bad.mode == MODE_FAILED
    assert bad.reason == "destination_forbidden"
    assert url_host_allowed("https://ov.batan.coop/handoff?c=x") is True
    assert url_host_allowed("https://evil.example/handoff?c=x") is False
    assert url_host_allowed("http://ov.batan.coop/handoff") is False


def test_ov3_14_authenticated_only_jsat_v2(monkeypatch):
    from app.services import ov_handoff as h

    monkeypatch.setattr(h, "handoff_v2_enabled", lambda db=None: True)
    monkeypatch.setattr(
        h,
        "request_ov_handoff",
        lambda **_kw: {
            "status": "OK",
            "result": {
                "handoff_url": "https://ov.batan.coop/handoff?c=opaque",
                "expires_in": 60,
                "destination": "my",
                "mode": "authenticated",
            },
        },
    )
    out = resolve_handoff("invoice", _abo())
    assert out.mode == MODE_AUTHENTICATED
    assert out.authenticated is True
    assert out.url.startswith("https://ov.batan.coop/handoff")


def test_ov3_15_16_public_not_ready():
    out = resolve_handoff("pay", _abo())
    assert out.mode == MODE_PUBLIC
    assert out.authenticated is False
    assert out.reason == "public_entry"
    assert "tsid=" not in out.url.lower()
    assert "/#/pagar" in out.url or out.url.endswith("pagar")


def test_ov3_17_jsat_error_not_authenticated(monkeypatch):
    from app.services import ov_handoff as h

    monkeypatch.setattr(h, "handoff_v2_enabled", lambda db=None: True)
    monkeypatch.setattr(
        h,
        "request_ov_handoff",
        lambda **_kw: {"status": "ERROR", "code": "identity_not_found", "result": None},
    )
    out = resolve_handoff("invoice", _abo())
    assert out.authenticated is False
    assert out.mode == MODE_PUBLIC
    assert out.reason == "jsat_0"


def test_ov3_17b_jsat_ambiguous(monkeypatch):
    from app.services import ov_handoff as h

    monkeypatch.setattr(h, "handoff_v2_enabled", lambda db=None: True)
    monkeypatch.setattr(
        h,
        "request_ov_handoff",
        lambda **_kw: {"status": "ERROR", "code": "identity_ambiguous", "result": None},
    )
    out = resolve_handoff("invoice", _abo())
    assert out.reason == "jsat_n"
    assert out.authenticated is False


def test_ov3_13b_handoff_url_host_rejected(monkeypatch):
    from app.services import ov_handoff as h

    monkeypatch.setattr(h, "handoff_v2_enabled", lambda db=None: True)
    monkeypatch.setattr(
        h,
        "request_ov_handoff",
        lambda **_kw: {
            "status": "OK",
            "result": {"handoff_url": "https://evil.example/handoff?c=x", "expires_in": 60},
        },
    )
    out = resolve_handoff("invoice", _abo())
    assert out.mode == MODE_PUBLIC
    assert out.reason == "host_forbidden"
    assert "evil.example" not in out.url


def test_ov3_18_21_logs_sin_secretos(monkeypatch, caplog):
    from app.services import ov_batan as ov

    ov.clear_sid_cache()

    class _Resp:
        is_success = True
        content = b'{"status":"OK","result":{"sid":"sid-tecnico"}}'
        charset_encoding = "utf-8"
        encoding = "utf-8"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(ov.httpx, "post", lambda *a, **k: _Resp())
    with caplog.at_level(logging.INFO, logger="operations_hub"):
        ov._ensure_sid(
            {
                "api_url": "https://ov.batan.coop/api",
                "user": "svc",
                "password": "s3cret-value",
                "timeout": 5,
            }
        )
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert "s3cret-value" not in blob
    assert "sid-tecnico" not in blob
    assert "password=" not in blob
    ov.clear_sid_cache()


def test_ov3_19_20_handoff_no_log_token(monkeypatch, caplog):
    from app.services import ov_handoff as h

    monkeypatch.setattr(h, "handoff_v2_enabled", lambda db=None: True)
    monkeypatch.setattr(
        h,
        "request_ov_handoff",
        lambda **_kw: {
            "status": "OK",
            "result": {
                "handoff_url": "https://ov.batan.coop/handoff?c=opaqueTOKEN",
                "expires_in": 60,
            },
        },
    )
    reset_handoff_metrics()
    with caplog.at_level(logging.INFO, logger="operations_hub"):
        resolve_handoff("invoice", _abo(), canal="app")
    blob = " ".join(r.getMessage() for r in caplog.records)
    assert "opaqueTOKEN" not in blob
    assert "tsid=" not in blob
    assert "30111222" not in blob
    assert snapshot_handoff_metrics()["ov_handoff_authenticated"] == 1


def test_ov3_22_legacy_ov_link_sigue(monkeypatch):
    from app.services import ov_batan as ov

    monkeypatch.setattr(ov, "ov_configurado", lambda db=None: True)
    monkeypatch.setattr(
        ov,
        "get_fast_link",
        lambda path, celular, db=None: (
            "https://ov.batan.coop/#/pagar?tsid=legacy&user=549"
        ),
    )
    link = ov.url_ov_para_key("pagar", "5492235402690")
    assert "tsid=legacy" in link


def test_ov3_23_legacy_tsid_no_es_authenticated():
    """Un resultado con tsid (simulado) no pasa por resolve_handoff como AUTH."""
    out = resolve_handoff("pay", _abo())
    assert out.mode != MODE_AUTHENTICATED
    assert "handoff_safe" not in (out.reason or "")


def test_ov4r_url_existente_sin_secretos():
    out = resolve_handoff("invoice", _abo())
    assert out.url.startswith("https://ov.batan.coop/#/my")
    assert out.mode == MODE_PUBLIC
    assert out.authenticated is False
    blob = f"{out.url} {out.reason} {out.mode}"
    for needle in ("password", "cookie", "Authorization", "sid=", "tsid=", "Bearer "):
        assert needle.lower() not in blob.lower()


def test_ov4r_destino_arbitrario_no_inventa_url():
    out = resolve_handoff("https://evil.example/steal", _abo())
    assert out.mode == MODE_FAILED
    assert not out.url
    assert out.reason == "destination_forbidden"


def test_ov4r_no_invoca_cliente_jsat_v2(monkeypatch):
    from app.services import ov_handoff as h

    def _boom(**_kw):
        raise AssertionError("OV-04R no debe llamar POST /ov/handoff")

    monkeypatch.setattr(h, "request_ov_handoff", _boom)
    monkeypatch.setattr(h, "handoff_v2_enabled", lambda db=None: False)
    out = resolve_handoff("pay", _abo())
    assert out.mode == MODE_PUBLIC
    assert "/#/pagar" in out.url
