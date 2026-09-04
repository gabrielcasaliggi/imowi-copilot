"""Tests BCM (Sopnet): parser ONU/OLT, JWT, settings admin, triage FTTH."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.bcm.client import (
    BcmClient,
    clasificar_optica,
    extraer_token,
    normalizar_rx_dbm,
    parse_cliente,
    unwrap_payload,
)
from app.bcm.contract import EstadoOnuBcm
from app.services.conexion_bcm import (
    aplicar_bcm_a_ctx,
    clasificar_rama_bcm,
    evaluar_turno_onu_bcm,
    mensaje_abonado_bcm,
    mensaje_informe_potencia_onu,
    parse_rx_dbm_desde_resumen,
    requiere_visita_por_optica,
    triage_bcm_para_prompt,
)
from main import app

client = TestClient(app)

SAMPLE_CLIENTE = {
    "status": "ok",
    "data": {
        "numero_cliente": 12345,
        "nombre": "Juan",
        "apellido": "Pérez",
        "onu": {
            "serial": "HWTC12345678",
            "mac": "AA:BB:CC:DD:EE:FF",
            "modelo": "HG8145V5",
            "estado": "online",
            "rx": -18.2,
            "tx": 2.1,
            "olt": "OLT-Batan-Centro",
            "pon": "0/1/2",
        },
    },
}

SAMPLE_FLAT = {
    "numero_cliente": "12345",
    "serial_onu": "HWTC9999",
    "estado_onu": "registrado",
    "potencia_rx": "19.5",
    "nombre_olt": "OLT-Viamonte-Norte",
    "puerto_pon": "GPON 0/2/4",
}

SAMPLE_OFFLINE = {"onu": {"serial": "X", "estado": "offline", "rx": None}}
SAMPLE_MALA = {"onu": {"estado": "online", "rx": -29.5, "olt": "OLT-X"}}


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_unwrap_y_token():
    assert unwrap_payload({"data": {"nombre": "A"}})["nombre"] == "A"
    assert extraer_token({"token": "jwt-abc-token-16chars"}) == "jwt-abc-token-16chars"
    assert extraer_token({"data": {"jwt": "nested-token-value1"}}) == "nested-token-value1"
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.aaaaaaaa"
    assert extraer_token({"datos": {"Token": jwt}}) == jwt
    assert extraer_token({"Data": jwt}) == jwt
    assert extraer_token({"mensaje": "ok", "objeto": jwt}) == jwt
    assert extraer_token("  " + jwt + "  ") == jwt
    assert extraer_token({"status": False, "mensaje": "usuario inválido"}) == ""


def test_describir_auth_incluye_claves_y_mensaje():
    from app.bcm.client import describir_auth_fallida

    err = describir_auth_fallida(
        {"status": False, "mensaje": "usuario o password incorrectos"},
        status_code=200,
        content_type="application/json",
    )
    assert "claves=status,mensaje" in err
    assert "usuario o password" in err
    assert "HTTP 200" in err


def test_normalizar_rx_positiva_como_dbm():
    assert normalizar_rx_dbm(-18.2) == -18.2
    assert normalizar_rx_dbm(19.5) == -19.5
    assert normalizar_rx_dbm("-21 dBm") == -21.0
    assert clasificar_optica(-18.0) == "buena"
    assert clasificar_optica(-25.5) == "aceptable"
    assert clasificar_optica(-29.0) == "mala"
    assert clasificar_optica(-6.0) == "mala"
    assert clasificar_optica(None) == ""


def test_parse_onu_anidada():
    onu = parse_cliente(SAMPLE_CLIENTE, numero_cliente="12345")
    assert onu.encontrado is True
    assert onu.online is True
    assert onu.serial == "HWTC12345678"
    assert onu.olt_nombre == "OLT-Batan-Centro"
    assert onu.rx_dbm == -18.2
    assert onu.calidad_optica == "buena"
    assert clasificar_rama_bcm(onu) == "enlace_ok"
    assert "en_linea" in onu.resumen_prompt()
    assert "OLT-Batan-Centro" in onu.resumen_prompt()


def test_parse_onu_aplanada_rx_positiva():
    onu = parse_cliente(SAMPLE_FLAT, numero_cliente="12345")
    assert onu.encontrado is True
    assert onu.online is True
    assert onu.serial == "HWTC9999"
    assert onu.olt_nombre == "OLT-Viamonte-Norte"
    assert onu.rx_dbm == -19.5
    assert onu.calidad_optica == "buena"


def test_parse_offline_y_potencia_mala():
    off = parse_cliente(SAMPLE_OFFLINE, numero_cliente="1")
    assert off.online is False
    assert clasificar_rama_bcm(off) == "onu_offline"

    mala = parse_cliente(SAMPLE_MALA, numero_cliente="1")
    assert clasificar_rama_bcm(mala) == "potencia_mala"
    assert requiere_visita_por_optica(mala) is True


def test_parse_no_encontrado():
    onu = parse_cliente({"status": "error", "mensaje": "no existe"}, numero_cliente="0")
    assert onu.encontrado is False


def test_informe_potencia_buena_vs_mala():
    buena = EstadoOnuBcm(
        numero_cliente="x", encontrado=True, online=True, rx_dbm=-18.0, calidad_optica="buena"
    )
    mala = EstadoOnuBcm(
        numero_cliente="x", encontrado=True, online=True, rx_dbm=-29.0, calidad_optica="mala"
    )
    txt_b = mensaje_informe_potencia_onu(buena)
    assert "-18.0" in txt_b
    assert "visita" not in txt_b.lower()
    txt_m = mensaje_informe_potencia_onu(mala)
    assert "-29.0" in txt_m
    assert "baja" in txt_m


def test_parse_rx_desde_resumen():
    assert parse_rx_dbm_desde_resumen("nro_cliente=1; rx=-18.2dBm; calidad=buena") == -18.2
    assert parse_rx_dbm_desde_resumen("sin dato") is None


def test_evaluar_turno_potencia_mala_deriva_visita():
    ctx = (
        "CONTEXTO_ABONADO:\n"
        "- bcm: nro_cliente=1; estado=en_linea; rx=-29.5dBm; calidad=mala\n"
        "- bcm_triage: triage=onu_ftth_potencia_mala; cable amarillo\n"
    )
    out = evaluar_turno_onu_bcm(
        contexto_abonado=ctx,
        mensaje_cliente="sigue sin andar internet",
        historial_mensajes=[],
        pasos_cubiertos=["bcm_potencia_mala"],
        turnos_diagnostico=1,
        intencion="internet_ftth",
    )
    assert out is not None
    assert out["accion"] == "escalate"
    assert out["motivo"] == "bcm_potencia_mala_visita"
    assert "visita" in (out.get("mensaje") or "").lower()


def test_evaluar_turno_consulta_potencia():
    ctx = (
        "CONTEXTO_ABONADO:\n"
        "- bcm: nro_cliente=1; estado=en_linea; rx=-18.2dBm; calidad=buena\n"
        "- bcm_triage: triage=onu_ftth_enlace_ok; indagar Wi‑Fi\n"
    )
    out = evaluar_turno_onu_bcm(
        contexto_abonado=ctx,
        mensaje_cliente="qué potencia tiene la onu",
        historial_mensajes=[],
        pasos_cubiertos=[],
        turnos_diagnostico=1,
        intencion="internet_ftth",
    )
    assert out is not None
    assert out["accion"] == "ask"
    assert out["motivo"] == "bcm_consulta_potencia"
    assert "-18.2" in (out.get("mensaje") or "")


def test_evaluar_turno_no_aplica_radio():
    ctx = (
        "CONTEXTO_ABONADO:\n"
        "- uisp: login=x; estado=en_linea; senal=-33dBm\n"
        "- uisp_triage: triage=cpe_radio_enlace_ok\n"
    )
    out = evaluar_turno_onu_bcm(
        contexto_abonado=ctx,
        mensaje_cliente="sigue sin andar",
        historial_mensajes=[],
        pasos_cubiertos=[],
        turnos_diagnostico=2,
        intencion="internet_radio",
    )
    assert out is None


def test_aplicar_bcm_a_ctx():
    ctx: dict = {}
    onu = EstadoOnuBcm(
        numero_cliente="12345",
        encontrado=True,
        online=True,
        rx_dbm=-18.2,
        calidad_optica="buena",
        olt_nombre="OLT-Batan-Centro",
    )
    aplicar_bcm_a_ctx(ctx, onu)
    assert "en_linea" in ctx["bcm_resumen"]
    assert "onu_ftth_enlace_ok" in ctx["bcm_triage"]
    assert ctx["ont_estado"] == "en_linea"
    assert ctx["olt_huawei"] == "OLT-Batan-Centro"


def test_mensaje_n1_ftth():
    off = EstadoOnuBcm(numero_cliente="x", encontrado=True, online=False)
    msg = mensaje_abonado_bcm(off, es_ftth=True)
    assert msg and "cajita" in msg.lower()
    assert "triage=onu_ftth_offline" in triage_bcm_para_prompt(off)

    ok = EstadoOnuBcm(
        numero_cliente="x", encontrado=True, online=True, rx_dbm=-18.0, calidad_optica="buena"
    )
    msg_ok = mensaje_abonado_bcm(ok, es_ftth=True)
    assert msg_ok and "Wi‑Fi" in msg_ok
    assert mensaje_abonado_bcm(ok, es_ftth=False) is None
    assert mensaje_abonado_bcm(EstadoOnuBcm(numero_cliente="x", encontrado=False), es_ftth=True) is None


def test_contexto_bcm_sin_cliente_vacio(monkeypatch):
    from app.services import conexion_bcm as cb

    monkeypatch.setattr(cb, "resolve_bcm_client", lambda db=None: None)
    ctx = cb.contexto_bcm_para_abonado(SimpleNamespace(dni="30111222", client_number="12345"))
    assert ctx["bcm_resumen"] == ""


def test_contexto_bcm_conectado(monkeypatch):
    from app.services import conexion_bcm as cb

    fake = MagicMock()
    fake.buscar_onu_por_cliente.return_value = parse_cliente(SAMPLE_CLIENTE, numero_cliente="12345")
    monkeypatch.setattr(cb, "resolve_bcm_client", lambda db=None: fake)
    ctx = cb.contexto_bcm_para_abonado(SimpleNamespace(dni="1", client_number="12345"))
    assert ctx["bcm_estado"] == "en_linea"
    assert "12345" in ctx["bcm_resumen"]
    assert "onu_ftth_enlace_ok" in ctx["bcm_triage"]
    assert ctx["olt_huawei"] == "OLT-Batan-Centro"
    fake.buscar_onu_por_cliente.assert_called_once_with("12345")


def test_buscar_onu_envia_query_numero():
    """Swagger BCM: obtenerPorNumeroCliente usa `numero`, no `numero_cliente`."""
    captured: dict[str, object] = {}

    class _Resp:
        status_code = 200

        def json(self):
            return SAMPLE_CLIENTE

    bcm = BcmClient(base_url="https://bcm.example/api/v1", user="u", app_pass="p")
    bcm._token = "tok"

    def _fake_get(path, params, retry=True):
        captured["path"] = path
        captured["params"] = params
        return _Resp()

    bcm._request_get = _fake_get  # type: ignore[method-assign]
    onu = bcm.buscar_onu_por_cliente("200")
    assert captured["path"] == "/cliente/obtenerPorNumeroCliente"
    assert captured["params"]["numero"] == "200"
    assert "numero_cliente" not in captured["params"]
    assert onu.encontrado is True


def test_test_bcm_sin_credenciales():
    r = client.post(
        "/api/v1/admin/settings/test-bcm",
        headers=_admin_headers(),
        json={"base_url": "https://la23.sopnet.com.ar:7117/api/v1", "user": "", "app_pass": ""},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["scope"] == "bcm"
    assert "usuario" in (body.get("error") or "").lower() or "password" in (body.get("error") or "").lower()


def test_put_bcm_settings_enmascara_password():
    h = _admin_headers()
    r = client.put(
        "/api/v1/admin/settings",
        headers=h,
        json={
            "settings": {
                "bcm": {
                    "enabled": True,
                    "base_url": "https://la23.sopnet.com.ar:7117/api/v1",
                    "user": "ops-bcm",
                    "app_pass": "super-secret-bcm-pass-xyz",
                    "verify_ssl": True,
                    "timeout": 12,
                }
            }
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["bcm_configured"] is True
    assert body["bcm_enabled"] is True
    secret = body["settings"]["bcm"].get("app_pass") or ""
    assert "***" in secret
    assert "super-secret" not in secret
    assert body["settings"]["bcm"]["base_url"].endswith("/api/v1")
    assert body["settings"]["bcm"]["enabled"] is True
    client.put(
        "/api/v1/admin/settings",
        headers=h,
        json={"settings": {"bcm": {"enabled": False}}},
    )
