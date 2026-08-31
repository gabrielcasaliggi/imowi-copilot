"""Tests UISP NMS: parser, matching por username Radius, settings admin."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.services.conexion_uisp import (
    clasificar_rama_uisp,
    mensaje_abonado_uisp,
    triage_uisp_para_prompt,
)
from app.uisp.client import (
    api_root,
    buscar_en_indice,
    clasificar_senal,
    extraer_lista_dispositivos,
    indexar_dispositivos,
    normalizar_nombre_cpe,
    parse_device,
)
from app.uisp.contract import EstadoCpeUisp
from main import app

client = TestClient(app)

SAMPLE_DEVICES = [
    {
        "identification": {
            "id": "dev-1",
            "name": "4640854",
            "mac": "80:2A:A8:11:22:33",
            "model": "LiteBeam 5AC",
            "modelName": "LiteBeam 5AC Gen2",
            "type": "airMax",
            "status": "active",
            "site": {"id": "site-1", "name": "Torre Norte"},
        },
        "overview": {
            "status": "active",
            "signal": -58,
            "uptime": 3600,
        },
        "attributes": {"apDevice": {"name": "AP-NORTE"}},
    },
    {
        "identification": {
            "id": "dev-2",
            "name": "CPE-OFF",
            "modelName": "NanoStation",
            "site": {"name": "Torre Sur"},
        },
        "overview": {"status": "disconnected", "signal": None, "uptime": 0},
    },
    {
        "identification": {
            "id": "dev-3",
            "name": "senal-baja",
            "modelName": "PowerBeam",
            "site": {"name": "Cerro"},
        },
        "overview": {"status": "active", "signal": -82},
    },
]


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_api_root_no_duplica_prefijo():
    assert api_root("https://uisp.ecolan.com") == "https://uisp.ecolan.com/nms/api/v2.1"
    assert (
        api_root("https://uisp.ecolan.com/nms/api/v2.1") == "https://uisp.ecolan.com/nms/api/v2.1"
    )
    assert api_root("https://uisp.ecolan.com/") == "https://uisp.ecolan.com/nms/api/v2.1"


def test_normalizar_nombre_cpe():
    assert normalizar_nombre_cpe("  4640854  ") == "4640854"
    assert normalizar_nombre_cpe("CPE-Off") == "cpe-off"


def test_clasificar_senal():
    assert clasificar_senal(-58) == "buena"
    assert clasificar_senal(-70) == "aceptable"
    assert clasificar_senal(-82) == "mala"
    assert clasificar_senal(None) == ""


def test_parse_y_match_por_username_radius():
    idx = indexar_dispositivos(SAMPLE_DEVICES)
    dev = buscar_en_indice(idx, "4640854")
    assert dev is not None
    cpe = parse_device(dev, login="4640854")
    assert cpe.encontrado is True
    assert cpe.online is True
    assert cpe.calidad_senal == "buena"
    assert cpe.sitio == "Torre Norte"
    assert cpe.modelo == "LiteBeam 5AC Gen2"
    assert cpe.ap_nombre == "AP-NORTE"
    assert "en_linea" in cpe.resumen_prompt()

    off = parse_device(buscar_en_indice(idx, "cpe-off"), login="CPE-OFF")
    assert off.online is False
    assert clasificar_rama_uisp(off) == "cpe_offline"

    baja = parse_device(buscar_en_indice(idx, "senal-baja"), login="senal-baja")
    assert clasificar_rama_uisp(baja) == "senal_mala"


def test_match_case_insensitive():
    idx = indexar_dispositivos(SAMPLE_DEVICES)
    assert buscar_en_indice(idx, "4640854") is not None
    assert buscar_en_indice(idx, " 4640854 ") is not None
    assert buscar_en_indice(idx, "no-existe") is None


def test_extraer_lista_envuelta():
    wrapped = extraer_lista_dispositivos({"data": SAMPLE_DEVICES})
    assert len(wrapped) == 3
    assert extraer_lista_dispositivos(SAMPLE_DEVICES)[0]["identification"]["id"] == "dev-1"


def test_mensaje_n1_radio():
    off = EstadoCpeUisp(login="x", encontrado=True, online=False)
    msg = mensaje_abonado_uisp(off, es_radio=True)
    assert msg and "PoE" in msg
    assert "triage=cpe_radio_offline" in triage_uisp_para_prompt(off)

    ok = EstadoCpeUisp(
        login="x", encontrado=True, online=True, signal_dbm=-55, calidad_senal="buena"
    )
    msg_ok = mensaje_abonado_uisp(ok, es_radio=True)
    assert msg_ok and "Wi‑Fi" in msg_ok
    assert mensaje_abonado_uisp(ok, es_radio=False) is None
    assert mensaje_abonado_uisp(EstadoCpeUisp(login="x", encontrado=False), es_radio=True) is None


def test_contexto_uisp_sin_cliente_vacio(monkeypatch):
    from app.services import conexion_uisp as cu

    monkeypatch.setattr(cu, "resolve_uisp_client", lambda db=None: None)
    ctx = cu.contexto_uisp_para_abonado(SimpleNamespace(dni="30111222"))
    assert ctx["uisp_resumen"] == ""


def test_contexto_uisp_conectado(monkeypatch):
    from app.services import conexion_uisp as cu

    fake = MagicMock()
    fake.buscar_cpe_por_login.return_value = parse_device(SAMPLE_DEVICES[0], login="4640854")
    monkeypatch.setattr(cu, "resolve_uisp_client", lambda db=None: fake)
    ctx = cu.contexto_uisp_para_abonado(SimpleNamespace(dni="1"), login="4640854")
    assert ctx["uisp_estado"] == "en_linea"
    assert "4640854" in ctx["uisp_resumen"]
    assert "cpe_radio_enlace_ok" in ctx["uisp_triage"]
    fake.buscar_cpe_por_login.assert_called_once_with("4640854")


def test_test_uisp_sin_token():
    r = client.post(
        "/api/v1/admin/settings/test-uisp",
        headers=_admin_headers(),
        json={"base_url": "https://uisp.ecolan.com", "token": ""},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["scope"] == "uisp"
    assert "token" in (body.get("error") or "").lower()


def test_put_uisp_settings_enmascara_token():
    h = _admin_headers()
    r = client.put(
        "/api/v1/admin/settings",
        headers=h,
        json={
            "settings": {
                "uisp": {
                    "enabled": True,
                    "base_url": "https://uisp.ecolan.com",
                    "token": "super-secret-uisp-token-xyz",
                    "verify_ssl": True,
                    "timeout": 12,
                }
            }
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["uisp_configured"] is True
    assert body["uisp_enabled"] is True
    tok = body["settings"]["uisp"].get("token") or ""
    assert "***" in tok
    assert "super-secret" not in tok
    assert body["settings"]["uisp"]["base_url"] == "https://uisp.ecolan.com"
    assert body["settings"]["uisp"]["enabled"] is True
    # No dejar enabled en el sqlite compartido de tests (evitar HTTP real a UISP).
    client.put(
        "/api/v1/admin/settings",
        headers=h,
        json={"settings": {"uisp": {"enabled": False}}},
    )
