"""Tests UISP NMS: parser, matching por username Radius, settings admin."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.services.conexion_uisp import (
    aplicar_uisp_a_ctx,
    clasificar_rama_uisp,
    evaluar_turno_visita_antena_uisp,
    mensaje_abonado_uisp,
    mensaje_informe_senal_antena,
    mensaje_visita_antena_por_senal,
    parse_signal_dbm_desde_resumen,
    requiere_visita_campo_por_senal,
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
    assert requiere_visita_campo_por_senal(baja) is True


def test_informe_senal_buena_vs_mala():
    buena = EstadoCpeUisp(
        login="x", encontrado=True, online=True, signal_dbm=-33, calidad_senal="buena"
    )
    mala = EstadoCpeUisp(
        login="x", encontrado=True, online=True, signal_dbm=-82, calidad_senal="mala"
    )
    txt_b = mensaje_informe_senal_antena(buena)
    assert "-33" in txt_b
    assert "excelente" in txt_b
    assert "visita" not in txt_b.lower()
    assert "📊" in txt_b
    txt_m = mensaje_informe_senal_antena(mala)
    assert "-82" in txt_m
    assert "baja" in txt_m
    assert "📊" in txt_m
    assert "visita" in mensaje_visita_antena_por_senal(mala).lower()


def test_parse_signal_desde_resumen():
    assert parse_signal_dbm_desde_resumen("login=x; senal=-58dBm; calidad=buena") == -58
    assert parse_signal_dbm_desde_resumen("sin dato") is None


def test_evaluar_turno_senal_mala_deriva_visita():
    ctx = (
        "CONTEXTO_ABONADO:\n"
        "- uisp: login=x; estado=en_linea; senal=-82dBm; calidad=mala\n"
        "- uisp_triage: triage=cpe_radio_senal_mala; linea_de_vista\n"
    )
    out = evaluar_turno_visita_antena_uisp(
        contexto_abonado=ctx,
        mensaje_cliente="sigue sin andar internet",
        historial_mensajes=[],
        pasos_cubiertos=["poe_antena"],
        turnos_diagnostico=1,
        intencion="internet_radio",
    )
    assert out is not None
    assert out["accion"] == "escalate"
    assert out["motivo"] == "uisp_senal_mala_visita"
    assert "visita" in (out.get("mensaje") or "").lower()


def test_evaluar_turno_senal_mala_voy_a_cortar_arbol_no_deriva():
    ctx = (
        "CONTEXTO_ABONADO:\n"
        "- uisp: login=x; estado=en_linea; senal=-79dBm; calidad=mala\n"
        "- uisp_triage: triage=cpe_radio_senal_mala; linea_de_vista\n"
    )
    out = evaluar_turno_visita_antena_uisp(
        contexto_abonado=ctx,
        mensaje_cliente="voy a cortar un arbol que hay en el medio",
        historial_mensajes=[],
        pasos_cubiertos=["uisp_senal_mala"],
        turnos_diagnostico=3,
        intencion="internet_radio",
    )
    assert out is not None
    assert out["accion"] == "ask"
    assert out["motivo"] == "uisp_linea_vista_accion_cliente"
    assert "visita" not in (out.get("mensaje") or "").lower()
    assert "despejes" in (out.get("mensaje") or "").lower()


def test_evaluar_turno_senal_mala_pendiente_despeje_sigue_mal_deriva():
    ctx = (
        "CONTEXTO_ABONADO:\n"
        "- uisp: login=x; estado=en_linea; senal=-79dBm; calidad=mala\n"
        "- uisp_triage: triage=cpe_radio_senal_mala; linea_de_vista\n"
    )
    out = evaluar_turno_visita_antena_uisp(
        contexto_abonado=ctx,
        mensaje_cliente="sigue sin andar",
        historial_mensajes=[],
        pasos_cubiertos=["uisp_senal_mala", "linea_vista_accion_pendiente"],
        turnos_diagnostico=4,
        intencion="internet_radio",
    )
    assert out is not None
    assert out["accion"] == "escalate"
    assert out["motivo"] == "uisp_senal_mala_visita"


def test_evaluar_turno_senal_buena_consulta_no_deriva():
    ctx = (
        "CONTEXTO_ABONADO:\n"
        "- uisp: login=x; estado=en_linea; senal=-33dBm; calidad=buena\n"
        "- uisp_triage: triage=cpe_radio_enlace_ok; indagar Wi‑Fi\n"
    )
    out = evaluar_turno_visita_antena_uisp(
        contexto_abonado=ctx,
        mensaje_cliente="que señal tengo y cual es el ideal",
        historial_mensajes=[],
        pasos_cubiertos=[],
        turnos_diagnostico=2,
        intencion="internet_lento",
    )
    assert out is not None
    assert out["accion"] == "ask"
    assert out["motivo"] == "uisp_consulta_senal"
    assert "-33" in (out.get("mensaje") or "")


def test_aplicar_uisp_a_ctx():
    ctx: dict = {}
    cpe = EstadoCpeUisp(
        login="4640854", encontrado=True, online=True, signal_dbm=-82, calidad_senal="mala"
    )
    aplicar_uisp_a_ctx(ctx, cpe)
    assert ctx["uisp_signal_dbm"] == "-82"
    assert ctx["uisp_calidad_senal"] == "mala"
    assert "senal_mala" in ctx["uisp_triage"]


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
    assert "Señal de tu antena" in msg_ok
    assert "-55 dBm" in msg_ok
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
