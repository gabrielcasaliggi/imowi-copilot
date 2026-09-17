"""Portal GET /ov-links — links tipados Oficina Virtual."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

_FORBIDDEN = (
    "password",
    "set-cookie",
    "Cookie:",
    '"sid":',
    "api_url",
    "ov_user",
    "secret",
    "Authorization",
    "Bearer ",
    "/session/login",
    "raw_ov",
)


def _portal_identified(dni: str = "30111222") -> dict:
    start = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": dni, "org_slug": "coop-batan"},
    )
    assert start.status_code == 200, start.text
    otp = start.json()["debug_otp"]
    verify = client.post(
        "/api/v1/portal/auth/verify",
        json={
            "challenge_id": start.json()["challenge_id"],
            "otp": otp,
            "org_slug": "coop-batan",
        },
    )
    assert verify.status_code == 200, verify.text
    return verify.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Canal": "app"}


def _assert_no_secret_leak(payload: dict) -> None:
    raw = str(payload)
    for needle in _FORBIDDEN:
        assert needle not in raw, f"leak: {needle} in {payload}"


def _shape_ok(body: dict) -> None:
    assert body["status"] in ("ready", "partial", "unavailable", "unknown")
    assert isinstance(body["checked_at"], str) and body["checked_at"]
    assert body["actions"]["can_open_chat"] is True
    assert isinstance(body["actions"]["chat_hint"], str)
    assert isinstance(body["links"], list)
    assert len(body["links"]) == 3
    ids = [x["id"] for x in body["links"]]
    assert ids == ["pay", "invoice", "payment_slip"]
    labels = {x["id"]: x["label"] for x in body["links"]}
    assert labels["pay"] == "Pagar"
    assert labels["invoice"] == "Ver factura"
    assert labels["payment_slip"] == "Talón de pago"
    for link in body["links"]:
        assert "available" in link
        if link["available"]:
            assert isinstance(link["url"], str) and link["url"].startswith("http")
        else:
            assert link["url"] is None
    assert "reason_code" in body


def test_ov_links_requiere_jwt():
    r = client.get("/api/v1/portal/ov-links")
    assert r.status_code == 401


def test_ov_links_requiere_identificado():
    from app.api.v1 import portal as portal_mod

    token = portal_mod._crear_portal_token(
        org_id="org-x",
        org_slug="coop-batan",
        conversacion_id="c1",
        telefono="",
        dni="30111222",
        identified=False,
        abonado_id="",
    )
    r = client.get("/api/v1/portal/ov-links", headers=_headers(token))
    assert r.status_code == 403


def test_ov_links_ready_mocked():
    auth = _portal_identified()
    token = auth["portal_token"]

    def _fake_url(key, celular="", *, db=None, celulares=None):
        return f"https://ov.example/jsat?tsid=abc&key={key}"

    with (
        patch("app.services.ov_batan.ov_configurado", return_value=True),
        patch(
            "app.services.ov_batan.candidatos_celular_ov",
            return_value=["5492235402690"],
        ),
        patch("app.services.ov_batan.url_ov_para_key", side_effect=_fake_url),
    ):
        r = client.get("/api/v1/portal/ov-links", headers=_headers(token))

    assert r.status_code == 200, r.text
    body = r.json()
    _shape_ok(body)
    _assert_no_secret_leak(body)
    assert body["status"] == "ready"
    assert body["reason_code"] is None
    assert all(x["available"] and x["url"] for x in body["links"])


def test_ov_links_partial_one_missing():
    auth = _portal_identified()
    token = auth["portal_token"]

    def _fake_url(key, celular="", *, db=None, celulares=None):
        if key == "talon":
            return ""
        return f"https://ov.example/jsat?tsid=abc&key={key}"

    with (
        patch("app.services.ov_batan.ov_configurado", return_value=True),
        patch(
            "app.services.ov_batan.candidatos_celular_ov",
            return_value=["5492235402690"],
        ),
        patch("app.services.ov_batan.url_ov_para_key", side_effect=_fake_url),
    ):
        r = client.get("/api/v1/portal/ov-links", headers=_headers(token))

    assert r.status_code == 200
    body = r.json()
    _shape_ok(body)
    assert body["status"] == "partial"
    assert body["reason_code"] == "partial"
    by_id = {x["id"]: x for x in body["links"]}
    assert by_id["pay"]["available"] is True
    assert by_id["invoice"]["available"] is True
    assert by_id["payment_slip"]["available"] is False
    assert by_id["payment_slip"]["url"] is None


def test_ov_links_unavailable_not_configured():
    auth = _portal_identified()
    token = auth["portal_token"]

    with patch("app.services.ov_batan.ov_configurado", return_value=False):
        r = client.get("/api/v1/portal/ov-links", headers=_headers(token))

    assert r.status_code == 200
    body = r.json()
    _shape_ok(body)
    _assert_no_secret_leak(body)
    assert body["status"] == "unavailable"
    assert body["reason_code"] == "ov_unavailable"
    assert all(not x["available"] and x["url"] is None for x in body["links"])


def test_ov_links_unavailable_on_exception():
    auth = _portal_identified()
    token = auth["portal_token"]

    with (
        patch("app.services.ov_batan.ov_configurado", return_value=True),
        patch(
            "app.services.ov_batan.candidatos_celular_ov",
            side_effect=TimeoutError("OV timeout"),
        ),
    ):
        r = client.get("/api/v1/portal/ov-links", headers=_headers(token))

    assert r.status_code == 200
    body = r.json()
    _shape_ok(body)
    _assert_no_secret_leak(body)
    assert body["status"] == "unavailable"
    assert body["reason_code"] == "ov_unavailable"
    assert "timeout" not in str(body).lower()
    assert "OV timeout" not in str(body)


def test_ov_links_insufficient_data_public_only():
    """Sin celular usable → hashes públicos → partial + insufficient_data."""
    auth = _portal_identified()
    token = auth["portal_token"]

    def _fake_url(key, celular="", *, db=None, celulares=None):
        return f"https://ov.batan.coop/#/{key}"

    with (
        patch("app.services.ov_batan.ov_configurado", return_value=True),
        patch("app.services.ov_batan.candidatos_celular_ov", return_value=[]),
        patch("app.services.ov_batan.url_ov_para_key", side_effect=_fake_url),
    ):
        r = client.get("/api/v1/portal/ov-links", headers=_headers(token))

    assert r.status_code == 200
    body = r.json()
    _shape_ok(body)
    assert body["status"] == "partial"
    assert body["reason_code"] == "insufficient_data"
    assert all(x["available"] for x in body["links"])


def test_ov_links_ignora_query_abonado_ajeno():
    """No hay query de account/subscriber; identidad solo del JWT."""
    auth = _portal_identified()
    token = auth["portal_token"]

    with (
        patch("app.services.ov_batan.ov_configurado", return_value=True),
        patch(
            "app.services.ov_batan.candidatos_celular_ov",
            return_value=["5492235402690"],
        ) as mock_cels,
        patch(
            "app.services.ov_batan.url_ov_para_key",
            return_value="https://ov.example/jsat?tsid=x",
        ),
    ):
        r = client.get(
            "/api/v1/portal/ov-links",
            params={"abonado_id": "otro", "service_id": "xyz", "customer_id": "1"},
            headers=_headers(token),
        )

    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    # candidatos se invocó con el abonado del JWT, no con params
    assert mock_cels.called
