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
    assert body.get("authenticated") in (True, False)
    assert body.get("mode") in ("authenticated", "public", "failed")


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
    """ready + authenticated solo con JSAT v2 (POST /ov/handoff)."""
    from app.services.ov_handoff import MODE_AUTHENTICATED, HandoffOutcome

    auth = _portal_identified()
    token = auth["portal_token"]

    def _fake_resolve(intent, abonado, **_kw):
        dest = {"pay": "pagar", "invoice": "my", "payment_slip": "talon-de-pago"}[intent]
        return HandoffOutcome(
            mode=MODE_AUTHENTICATED,
            url=f"https://ov.batan.coop/handoff?c=opaque-{intent}",
            destination=dest,
            intent=intent,
            reason="",
            expires_in=60,
        )

    with (
        patch("app.services.ov_batan.ov_configurado", return_value=True),
        patch("app.services.portal_ov_links.resolve_handoff", side_effect=_fake_resolve),
    ):
        r = client.get("/api/v1/portal/ov-links", headers=_headers(token))

    assert r.status_code == 200, r.text
    body = r.json()
    _shape_ok(body)
    _assert_no_secret_leak(body)
    assert body["status"] == "ready"
    assert body["authenticated"] is True
    assert body["mode"] == "authenticated"
    assert body["reason_code"] is None
    assert all(x["available"] and x["url"] for x in body["links"])
    assert '"sid":' not in str(body)


def test_ov_links_partial_one_missing():
    from app.services.ov_handoff import MODE_AUTHENTICATED, MODE_FAILED, HandoffOutcome

    auth = _portal_identified()
    token = auth["portal_token"]

    def _fake_resolve(intent, abonado, **_kw):
        if intent == "payment_slip":
            return HandoffOutcome(
                mode=MODE_FAILED,
                url="",
                destination="talon-de-pago",
                intent=intent,
                reason="jsat_down",
            )
        dest = {"pay": "pagar", "invoice": "my"}[intent]
        return HandoffOutcome(
            mode=MODE_AUTHENTICATED,
            url=f"https://ov.batan.coop/handoff?c=opaque-{intent}",
            destination=dest,
            intent=intent,
            reason="",
        )

    with (
        patch("app.services.ov_batan.ov_configurado", return_value=True),
        patch("app.services.portal_ov_links.resolve_handoff", side_effect=_fake_resolve),
    ):
        r = client.get("/api/v1/portal/ov-links", headers=_headers(token))

    assert r.status_code == 200
    body = r.json()
    _shape_ok(body)
    assert body["status"] == "partial"
    assert body["authenticated"] is False
    by_id = {x["id"]: x for x in body["links"]}
    assert by_id["pay"]["available"] is True
    assert by_id["invoice"]["available"] is True
    assert by_id["payment_slip"]["available"] is False
    assert by_id["payment_slip"]["url"] is None


def test_ov_links_publico_sin_credenciales_api():
    """OV-04R: hashes públicos no dependen de login técnico JSAT."""
    auth = _portal_identified()
    token = auth["portal_token"]

    with patch("app.services.ov_batan.ov_configurado", return_value=False):
        r = client.get("/api/v1/portal/ov-links", headers=_headers(token))

    assert r.status_code == 200
    body = r.json()
    _shape_ok(body)
    _assert_no_secret_leak(body)
    assert body["status"] == "partial"
    assert body["authenticated"] is False
    assert body["mode"] == "public"
    assert all(x["available"] and x["url"] for x in body["links"])
    for x in body["links"]:
        assert x["url"].startswith("https://ov.batan.coop/#/")
        assert "tsid=" not in x["url"].lower()
        assert "sid=" not in x["url"].lower()


def test_ov_links_unavailable_on_exception():
    auth = _portal_identified()
    token = auth["portal_token"]

    with (
        patch("app.services.ov_batan.ov_configurado", return_value=True),
        patch(
            "app.services.portal_ov_links.resolve_handoff",
            side_effect=TimeoutError("OV timeout"),
        ),
    ):
        r = client.get("/api/v1/portal/ov-links", headers=_headers(token))

    assert r.status_code == 200
    body = r.json()
    _shape_ok(body)
    _assert_no_secret_leak(body)
    assert body["status"] == "unavailable"
    assert body["authenticated"] is False
    assert body["reason_code"] == "ov_unavailable"
    assert "timeout" not in str(body).lower()
    assert "OV timeout" not in str(body)


def test_ov_links_insufficient_data_public_only():
    """Sin JSAT v2 → hashes públicos → partial, no ready, no authenticated."""
    auth = _portal_identified()
    token = auth["portal_token"]

    with patch("app.services.ov_batan.ov_configurado", return_value=True):
        r = client.get("/api/v1/portal/ov-links", headers=_headers(token))

    assert r.status_code == 200
    body = r.json()
    _shape_ok(body)
    _assert_no_secret_leak(body)
    assert body["status"] == "partial"
    assert body["authenticated"] is False
    assert body["mode"] == "public"
    assert body["reason_code"] == "insufficient_data"
    assert all(x["available"] for x in body["links"])
    assert all("tsid=" not in (x["url"] or "").lower() for x in body["links"])


def test_ov_links_ignora_query_abonado_ajeno():
    """No hay query de account/subscriber; identidad solo del JWT."""
    from app.services.ov_handoff import MODE_PUBLIC, HandoffOutcome

    auth = _portal_identified()
    token = auth["portal_token"]
    seen: list[str] = []

    def _fake_resolve(intent, abonado, **_kw):
        seen.append(str(getattr(abonado, "dni", "") or ""))
        return HandoffOutcome(
            mode=MODE_PUBLIC,
            url="https://ov.batan.coop/#/pagar",
            destination="pagar",
            intent=intent,
            reason="legacy_link",
        )

    with (
        patch("app.services.ov_batan.ov_configurado", return_value=True),
        patch("app.services.portal_ov_links.resolve_handoff", side_effect=_fake_resolve),
    ):
        r = client.get(
            "/api/v1/portal/ov-links",
            params={"abonado_id": "otro", "service_id": "xyz", "customer_id": "1"},
            headers=_headers(token),
        )

    assert r.status_code == 200
    assert r.json()["authenticated"] is False
    assert seen
    assert all(d == "30111222" for d in seen)
