"""Tests escritura Wi‑Fi BCM (password/SSID, ambas bandas) y flujo N1 remoto."""

from __future__ import annotations

from types import SimpleNamespace

from app.bcm.client import (
    WIFI_BANDAS,
    BcmClient,
    _error_en_cuerpo_tr_wifi,
    redactar_params_sensibles,
)
from app.radius.contract import ServicioConectividad
from app.services import wifi_bcm as wb
from app.services.diagnostico_n1 import aplicar_guardrails_cambio_clave_wifi


class _Resp:
    def __init__(self, status_code: int = 200, payload=None, text: str = ""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}
        self.text = text or ""

    def json(self):
        return self._payload


def _abo(aid: str = "abo-1") -> SimpleNamespace:
    return SimpleNamespace(id=aid, dni="30111222", client_number="12345")


def _dest_serial(sn: str) -> wb.DestinoWifiBcm:
    return wb.DestinoWifiBcm("serial", sn)


def _dest_radius(login: str) -> wb.DestinoWifiBcm:
    return wb.DestinoWifiBcm("user_radius", login)


def test_redactar_params_password():
    out = redactar_params_sensibles(
        {"usuario": "u", "token": "t", "password": "secreta123", "wifi": "2"}
    )
    assert out["password"] == "***"
    assert out["usuario"] == "u"
    assert out["wifi"] == "2"


def test_error_en_cuerpo_200_con_error_id():
    assert _error_en_cuerpo_tr_wifi(
        {"error_id": "201", "msg": "Datos Incorrectos"}, ""
    )
    assert not _error_en_cuerpo_tr_wifi({"ok": True}, "")
    assert _error_en_cuerpo_tr_wifi(
        None, '{"error_id":"201","msg":"ID NO ENCONTRADO"}'
    )


def test_modificar_password_200_con_error_body_no_ok(monkeypatch):
    bcm = BcmClient(base_url="https://bcm.example/api/v1", user="u", app_pass="p")
    bcm._token = "tok"

    def _fake_post(path, params, retry=True):
        return _Resp(
            200,
            {"error_id": "201", "msg": "Datos Incorrectos"},
            text='{"error_id":"201"}',
        )

    monkeypatch.setattr(bcm, "_request_post", _fake_post)
    r = bcm.modificar_wifi_password_por_serial("SN", "ClaveNueva1", "2")
    assert r.ok is False
    assert "201" in r.error or "Incorrectos" in r.error


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


def test_modificar_password_por_user_radius(monkeypatch):
    bcm = BcmClient(base_url="https://bcm.example/api/v1", user="u", app_pass="p")
    bcm._token = "tok"
    seen: list[dict] = []

    def _fake_post(path, params, retry=True):
        seen.append({"path": path, "params": dict(params)})
        assert params["userRadius"] == "pruebasadsl22"
        assert params["password"] == "ClaveNueva1"
        return _Resp(200)

    monkeypatch.setattr(bcm, "_request_post", _fake_post)
    results = bcm.modificar_wifi_password_ambas_bandas_por_user_radius(
        "pruebasadsl22", "ClaveNueva1"
    )
    assert all(r.ok for r in results)
    assert [s["params"]["wifi"] for s in seen] == ["2", "5"]
    assert all(s["path"] == "/tr/modificarWifiPasswordPorUserRadius" for s in seen)


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
    assert "incorrectos" in r.error.lower() or "201" in r.error


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


def test_sin_abonado_no_abre_remoto():
    ctx: dict = {"pasos_cubiertos": []}
    r = wb.turno_cambio_wifi_bcm(db=None, abonado=None, ctx=ctx, texto="clave")
    assert r is not None
    assert r["motivo"] == "wifi_bcm_sin_abonado"
    assert ctx.get("wifi_bcm") != "1"


def test_serial_ajeno_en_ctx_no_se_usa(monkeypatch):
    """Un serial cacheado de otro abonado no debe aplicarse."""
    ctx: dict = {
        "wifi_bcm": "1",
        "wifi_bcm_serial": "SERIAL-AJENO",
        "wifi_bcm_abonado_id": "otro-abonado",
        "pasos_cubiertos": [],
    }

    def _dest(db, abo, ctx, texto=""):
        d = _dest_serial("SERIAL-MIO")
        ctx["wifi_bcm_abonado_id"] = "abo-mio"
        ctx["wifi_bcm_serial"] = d.valor
        ctx["wifi_bcm_destino_kind"] = d.kind
        ctx["wifi_bcm_destino_valor"] = d.valor
        return d, "", ""

    monkeypatch.setattr(wb, "_destino_autorizado", _dest)
    applied: list[str] = []

    def _pass(db, destino, password):
        applied.append(destino.valor)
        return True, ""

    monkeypatch.setattr(wb, "_aplicar_password", _pass)

    r1 = wb.turno_cambio_wifi_bcm(
        db=None, abonado=_abo("abo-mio"), ctx=ctx, texto="clave"
    )
    assert r1 and ctx["wifi_bcm_serial"] == "SERIAL-MIO"
    assert ctx["wifi_bcm_abonado_id"] == "abo-mio"

    r2 = wb.turno_cambio_wifi_bcm(
        db=None, abonado=_abo("abo-mio"), ctx=ctx, texto="ClaveNueva99"
    )
    assert r2 and r2.get("motivo") == "wifi_bcm_ok"
    assert applied == ["SERIAL-MIO"]
    assert "olvid" in (r2["mensaje"] or "").lower()


def test_turno_remoto_pide_y_aplica_clave(monkeypatch):
    ctx: dict = {"pasos_cubiertos": []}
    abo = _abo()

    def _dest(db, abonado, ctx, texto=""):
        d = _dest_serial("HWTC999")
        ctx["wifi_bcm_abonado_id"] = abo.id
        ctx["wifi_bcm_serial"] = d.valor
        ctx["wifi_bcm_destino_kind"] = d.kind
        ctx["wifi_bcm_destino_valor"] = d.valor
        return d, "", ""

    monkeypatch.setattr(wb, "_destino_autorizado", _dest)
    applied: list[tuple[str, str]] = []

    def _pass(db, destino, password):
        applied.append((destino.valor, password))
        return True, ""

    monkeypatch.setattr(wb, "_aplicar_password", _pass)

    r1 = wb.turno_cambio_wifi_bcm(
        db=None, abonado=abo, ctx=ctx, texto="quiero la clave"
    )
    assert r1 is not None
    assert ctx["wifi_bcm"] == "1"
    assert ctx["wifi_bcm_abonado_id"] == abo.id
    assert "clave" in (r1["mensaje"] or "").lower() or "8" in (r1["mensaje"] or "")
    assert ctx["wifi_bcm_fase"] == "pedir_clave"

    r2 = wb.turno_cambio_wifi_bcm(
        db=None, abonado=abo, ctx=ctx, texto="ClaveNueva99"
    )
    assert r2 is not None
    assert r2.get("motivo") == "wifi_bcm_ok"
    assert applied == [("HWTC999", "ClaveNueva99")]
    assert "olvid" in (r2["mensaje"] or "").lower()


def test_turno_aplica_por_user_radius(monkeypatch):
    abo = _abo()
    ctx: dict = {
        "wifi_bcm": "1",
        "wifi_bcm_abonado_id": abo.id,
        "wifi_bcm_destino_kind": "user_radius",
        "wifi_bcm_destino_valor": "pruebasadsl22",
        "wifi_bcm_login": "pruebasadsl22",
        "pasos_cubiertos": [],
    }
    applied: list[tuple[str, str]] = []

    def _pass(db, destino, password):
        applied.append((destino.kind, destino.valor))
        assert destino.kind == "user_radius"
        return True, ""

    monkeypatch.setattr(wb, "_aplicar_password", _pass)
    wb.turno_cambio_wifi_bcm(db=None, abonado=abo, ctx=ctx, texto="clave")
    assert ctx["wifi_bcm_fase"] == "pedir_clave"
    r2 = wb.turno_cambio_wifi_bcm(
        db=None, abonado=abo, ctx=ctx, texto="ClaveNueva99"
    )
    assert r2 and r2.get("motivo") == "wifi_bcm_ok"
    assert applied == [("user_radius", "pruebasadsl22")]


def test_turno_multi_cuenta_pide_seleccion(monkeypatch):
    abo = _abo()
    ctx: dict = {"pasos_cubiertos": []}

    def _dest(db, abonado, ctx, texto=""):
        return (
            None,
            "necesita_seleccion",
            "Veo que tenés 2 cuentas de internet:\n• casa1FTTH\n• casa2FTTH\n"
            "¿En cuál querés cambiar el Wi‑Fi?",
        )

    monkeypatch.setattr(wb, "_destino_autorizado", _dest)
    r = wb.turno_cambio_wifi_bcm(
        db=None, abonado=abo, ctx=ctx, texto="quiero cambiar la clave"
    )
    assert r is not None
    assert r["motivo"] == "wifi_bcm_seleccion_cuenta"
    assert "casa1FTTH" in (r["mensaje"] or "")
    assert ctx.get("wifi_bcm") != "0"


def test_turno_ambos_clave_luego_ssid(monkeypatch):
    abo = _abo()
    ctx: dict = {
        "wifi_bcm": "1",
        "wifi_bcm_serial": "SN1",
        "wifi_bcm_destino_kind": "serial",
        "wifi_bcm_destino_valor": "SN1",
        "wifi_bcm_abonado_id": abo.id,
        "pasos_cubiertos": [],
    }
    monkeypatch.setattr(wb, "_aplicar_password", lambda *_a, **_k: (True, ""))
    monkeypatch.setattr(wb, "_aplicar_ssid", lambda *_a, **_k: (True, ""))
    monkeypatch.setattr(
        wb,
        "_servicios_abonado",
        lambda *_a, **_k: [],
    )

    r0 = wb.turno_cambio_wifi_bcm(db=None, abonado=abo, ctx=ctx, texto="ambas")
    assert ctx["wifi_bcm_que"] == "ambos"
    assert ctx["wifi_bcm_fase"] == "pedir_clave"
    assert r0 and "clave" in (r0["mensaje"] or "").lower()

    r1 = wb.turno_cambio_wifi_bcm(
        db=None, abonado=abo, ctx=ctx, texto="ClaveNueva99"
    )
    assert ctx["wifi_bcm_fase"] == "pedir_ssid"
    assert r1 and "nombre" in (r1["mensaje"] or "").lower()

    r2 = wb.turno_cambio_wifi_bcm(
        db=None, abonado=abo, ctx=ctx, texto="RedNuevaFTTH"
    )
    assert r2 and r2.get("motivo") == "wifi_bcm_ok"
    assert ctx["wifi_bcm_fase"] == "hecho"
    assert "olvid" in (r2["mensaje"] or "").lower()


def test_tras_clave_ok_pide_nombre_reabre_ssid(monkeypatch):
    """Regresión: tras cambio de clave, pedir el nombre no debe caer a guía local."""
    abo = _abo()
    ctx: dict = {
        "wifi_bcm": "1",
        "wifi_bcm_fase": "hecho",
        "wifi_bcm_que": "clave",
        "wifi_bcm_destino_kind": "user_radius",
        "wifi_bcm_destino_valor": "pruebasADSL22",
        "wifi_bcm_login": "pruebasADSL22",
        "wifi_bcm_abonado_id": abo.id,
        "pasos_cubiertos": ["wifi_bcm_clave_ok", "aviso_reconexion"],
    }
    monkeypatch.setattr(
        wb,
        "_servicios_abonado",
        lambda *_a, **_k: [],
    )
    applied: list[str] = []

    def _ssid(db, destino, ssid):
        applied.append(ssid)
        return True, ""

    monkeypatch.setattr(wb, "_aplicar_ssid", _ssid)

    r1 = wb.turno_cambio_wifi_bcm(
        db=None,
        abonado=abo,
        ctx=ctx,
        texto="excelente, hay posibilidad de cambiar el nombre de la red tambien?",
    )
    assert r1 is not None
    assert r1.get("motivo") == "wifi_bcm_pedir_ssid"
    assert ctx["wifi_bcm_fase"] == "pedir_ssid"
    assert "nombre" in (r1["mensaje"] or "").lower()

    r2 = wb.turno_cambio_wifi_bcm(
        db=None, abonado=abo, ctx=ctx, texto="RedNuevaEko"
    )
    assert r2 and r2.get("motivo") == "wifi_bcm_ok"
    assert applied == ["RedNuevaEko"]
    assert "olvid" in (r2["mensaje"] or "").lower()


def test_turno_sin_destino_cae_a_local(monkeypatch):
    ctx: dict = {"pasos_cubiertos": []}
    monkeypatch.setattr(
        wb,
        "_destino_autorizado",
        lambda *_a, **_k: (None, "sin_serial_ni_login", ""),
    )
    assert (
        wb.turno_cambio_wifi_bcm(db=None, abonado=_abo(), ctx=ctx, texto="clave")
        is None
    )
    assert ctx["wifi_bcm"] == "0"


def test_resolver_multi_ftth_necesita_seleccion(monkeypatch):
    abo = _abo()
    ctx: dict = {}
    svcs = [
        ServicioConectividad(
            login="unoFTTH",
            service_type_code="INTFO",
            service_type_label="Fibra Optica",
            product="Fibra 100",
            service_on=True,
            base_account_number="10",
        ),
        ServicioConectividad(
            login="dosFTTH",
            service_type_code="INTFO",
            service_type_label="Fibra Optica",
            product="Fibra 200",
            service_on=True,
            base_account_number="20",
        ),
    ]
    monkeypatch.setattr(wb, "_servicios_abonado", lambda *_a, **_k: svcs)
    monkeypatch.setattr(
        "app.services.conexion_bcm.resolve_bcm_client", lambda db=None: object()
    )
    monkeypatch.setattr(
        "app.services.conexion_bcm.es_servicio_ftth", lambda svc: True
    )
    monkeypatch.setattr(
        "app.services.billtrack.servicio_habilitado", lambda svc: True
    )
    monkeypatch.setattr(wb, "_buscar_serial", lambda *_a, **_k: "")
    dest, motivo, msg = wb.resolver_destino_wifi_bcm(None, abo, ctx, texto="clave")
    assert dest is None
    assert motivo == "necesita_seleccion"
    assert "unoFTTH" in msg and "dosFTTH" in msg
    assert ctx.get("wifi_bcm_pendiente_cuenta") == "1"

    dest2, motivo2, _ = wb.resolver_destino_wifi_bcm(
        None, abo, ctx, texto="unoFTTH"
    )
    assert motivo2 == ""
    assert dest2 is not None
    assert dest2.kind == "user_radius"
    assert dest2.valor == "unoFTTH"


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


def test_guardrail_bloquea_llm_router_ip_y_privacidad():
    from app.services.diagnostico_n1 import llm_inventa_admin_router_wifi

    assert llm_inventa_admin_router_wifi(
        "Para cambiar el nombre y la clave, necesito que entres a la configuración "
        "del router. ¿Tenés a mano el manual o sabés cómo acceder a la dirección IP?"
    )
    assert llm_inventa_admin_router_wifi(
        "Por seguridad y privacidad, los cambios de contraseña se deben hacer "
        "directamente desde el equipo. ¿Te guío paso a paso?"
    )
    g = aplicar_guardrails_cambio_clave_wifi(
        mensaje=(
            "Por seguridad y privacidad, los cambios se deben hacer desde el equipo. "
            "¿Te guío paso a paso?"
        ),
        mensaje_cliente="pero lo tenes que hacer vos",
        intencion="cambio_clave_wifi",
        gestion_remota=False,
    )
    assert g["motivo"] == "bloqueado_llm_admin_router_wifi"
    assert "etiqueta" in g["mensaje"].lower() or "módem" in g["mensaje"].lower()

    g2 = aplicar_guardrails_cambio_clave_wifi(
        mensaje=(
            "Por seguridad no lo podemos cambiar nosotros. Entrá a la configuración "
            "del router con la dirección IP."
        ),
        mensaje_cliente="ambas",
        intencion="cambio_clave_wifi",
        gestion_remota=True,
    )
    assert g2["motivo"] == "bloqueado_llm_niega_remoto_wifi"
    assert "clave nueva" in g2["mensaje"].lower() or "8 caracteres" in g2["mensaje"].lower()
