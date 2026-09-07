"""Tests escritura Wi‑Fi BCM (password/SSID, ambas bandas) y flujo N1 remoto."""

from __future__ import annotations

from app.bcm.client import WIFI_BANDAS, BcmClient, redactar_params_sensibles
from app.services import wifi_bcm as wb
from app.services.diagnostico_n1 import aplicar_guardrails_cambio_clave_wifi


class _Resp:
    def __init__(self, status_code: int = 200, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}
        self.text = text or ""

    def json(self):
        return self._payload


def test_redactar_params_password():
    out = redactar_params_sensibles(
        {"usuario": "u", "token": "t", "password": "secreta123", "wifi": "2"}
    )
    assert out["password"] == "***"
    assert out["usuario"] == "u"
    assert out["wifi"] == "2"


def test_modificar_password_ambas_bandas_query(monkeypatch):
    bcm = BcmClient(base_url="https://bcm.example/api/v1", user="u", app_pass="p")
    bcm._token = "tok"
    seen: list[dict] = []

    def _fake_post(path, params, retry=True):
        seen.append({"path": path, "params": dict(params)})
        assert "password" in params
        assert params["password"] == "ClaveNueva1"
        assert params["serialNumber"] == "HWTC123"
        assert params["usuario"] == "u"
        assert params["token"] == "tok"
        return _Resp(200)

    monkeypatch.setattr(bcm, "_request_post", _fake_post)
    results = bcm.modificar_wifi_password_ambas_bandas("HWTC123", "ClaveNueva1")
    assert len(results) == 2
    assert all(r.ok for r in results)
    assert [r.banda for r in results] == list(WIFI_BANDAS)
    assert [s["params"]["wifi"] for s in seen] == ["2", "5"]
    assert all(
        s["path"] == "/tr/modificarWifiPasswordPorSerialNumber" for s in seen
    )


def test_modificar_ssid_ambas_bandas(monkeypatch):
    bcm = BcmClient(base_url="https://bcm.example/api/v1", user="u", app_pass="p")
    bcm._token = "tok"
    seen: list[str] = []

    def _fake_post(path, params, retry=True):
        seen.append(params["wifi"])
        assert params["ssid"] == "MiRedNueva"
        return _Resp(200)

    monkeypatch.setattr(bcm, "_request_post", _fake_post)
    results = bcm.modificar_wifi_ssid_ambas_bandas("SN1", "MiRedNueva")
    assert all(r.ok for r in results)
    assert seen == ["2", "5"]


def test_modificar_password_http_error(monkeypatch):
    bcm = BcmClient(base_url="https://bcm.example/api/v1", user="u", app_pass="p")
    bcm._token = "tok"

    def _fake_post(path, params, retry=True):
        return _Resp(201, {"mensaje": "Datos incorrectos"})

    monkeypatch.setattr(bcm, "_request_post", _fake_post)
    r = bcm.modificar_wifi_password_por_serial("SN", "ClaveNueva1", "2")
    assert r.ok is False
    assert r.http_status == 201
    assert "201" in r.error


def test_validar_password_y_ssid():
    assert wb.validar_password_wifi("corta") 
    assert not wb.validar_password_wifi("ClaveNueva1")
    assert wb.validar_ssid_wifi("")
    assert not wb.validar_ssid_wifi("EcoLAN-Casa")


def test_interpretar_que_cambiar():
    assert wb.interpretar_que_cambiar("la clave") == "clave"
    assert wb.interpretar_que_cambiar("el nombre de la red") == "ssid"
    assert wb.interpretar_que_cambiar("ambas") == "ambos"
    assert wb.interpretar_que_cambiar("hola") == ""


def test_turno_remoto_pide_y_aplica_clave(monkeypatch):
    ctx: dict = {"bcm_serial": "HWTC999", "wifi_bcm": "", "pasos_cubiertos": []}

    monkeypatch.setattr(
        wb,
        "resolver_serial_wifi_bcm",
        lambda *_a, **_k: ("HWTC999", ""),
    )
    applied: list[tuple[str, str]] = []

    def _pass(db, serial, password):
        applied.append((serial, password))
        return True, ""

    monkeypatch.setattr(wb, "_aplicar_password", _pass)

    # 1) Intent con “clave” → pide password
    r1 = wb.turno_cambio_wifi_bcm(db=None, abonado=None, ctx=ctx, texto="quiero la clave")
    assert r1 is not None
    assert ctx["wifi_bcm"] == "1"
    assert "clave" in (r1["mensaje"] or "").lower() or "8" in (r1["mensaje"] or "")
    assert ctx["wifi_bcm_fase"] == "pedir_clave"

    # 2) Password válida → aplica ambas (mock) y confirma
    r2 = wb.turno_cambio_wifi_bcm(
        db=None, abonado=None, ctx=ctx, texto="ClaveNueva99"
    )
    assert r2 is not None
    assert r2.get("motivo") == "wifi_bcm_ok"
    assert applied == [("HWTC999", "ClaveNueva99")]
    assert "reconect" in (r2["mensaje"] or "").lower()


def test_turno_ambos_clave_luego_ssid(monkeypatch):
    ctx: dict = {
        "wifi_bcm": "1",
        "wifi_bcm_serial": "SN1",
        "bcm_serial": "SN1",
        "pasos_cubiertos": [],
    }
    monkeypatch.setattr(wb, "_aplicar_password", lambda *_a, **_k: (True, ""))
    monkeypatch.setattr(wb, "_aplicar_ssid", lambda *_a, **_k: (True, ""))

    r0 = wb.turno_cambio_wifi_bcm(db=None, abonado=None, ctx=ctx, texto="ambas")
    assert ctx["wifi_bcm_que"] == "ambos"
    assert ctx["wifi_bcm_fase"] == "pedir_clave"
    assert r0 and "clave" in (r0["mensaje"] or "").lower()

    r1 = wb.turno_cambio_wifi_bcm(db=None, abonado=None, ctx=ctx, texto="ClaveNueva99")
    assert ctx["wifi_bcm_fase"] == "pedir_ssid"
    assert r1 and "nombre" in (r1["mensaje"] or "").lower()

    r2 = wb.turno_cambio_wifi_bcm(db=None, abonado=None, ctx=ctx, texto="RedNuevaFTTH")
    assert r2 and r2.get("motivo") == "wifi_bcm_ok"
    assert ctx["wifi_bcm_fase"] == "hecho"


def test_turno_sin_serial_cae_a_local(monkeypatch):
    ctx: dict = {"pasos_cubiertos": []}
    monkeypatch.setattr(
        wb, "resolver_serial_wifi_bcm", lambda *_a, **_k: ("", "sin_serial")
    )
    assert wb.turno_cambio_wifi_bcm(db=None, abonado=None, ctx=ctx, texto="clave") is None
    assert ctx["wifi_bcm"] == "0"


def test_guardrail_permite_pedido_si_gestion_remota():
    g = aplicar_guardrails_cambio_clave_wifi(
        mensaje="Escribí la nueva clave que querés poner",
        mensaje_cliente="la clave",
        intencion="cambio_clave_wifi",
        gestion_remota=True,
    )
    assert not g.get("motivo")
    assert "nueva clave" in g["mensaje"].lower()


def test_guardrail_sigue_bloqueando_sin_remoto():
    g = aplicar_guardrails_cambio_clave_wifi(
        mensaje="Pasame la nueva clave que querés poner en el WiFi",
        mensaje_cliente="hola",
        intencion="cambio_clave_wifi",
        gestion_remota=False,
    )
    assert g["motivo"] == "bloqueado_pedido_clave_wifi"
