"""Paridad Eko ↔ Portal: mismas sondas → mismo decidir() / TSS.

Sin I/O OSS. No toca wifi_bcm.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.bcm.contract import EstadoOnuBcm
from app.radius.contract import EstadoConexionPPPoE, ServicioConectividad, SesionPPPoE
from app.services.canal_abonado import _linea_acceso_ok_ctx
from app.services.connectivity_decision import decidir
from app.services.connectivity_eko import (
    aplicar_resultado_a_ctx,
    conversational_branch_for,
    evaluar_desde_sondas_eko,
    incident_from_outage,
    stamp_incident_activo_en_ctx,
)
from app.services.pre_triaje_acceso import mensaje_pre_triaje_acceso
from app.uisp.contract import EstadoCpeUisp

CHECKED = datetime(2026, 9, 17, 16, 0, tzinfo=UTC)


def _svc_ftth(**kw) -> ServicioConectividad:
    base = dict(
        id="svc-ftth-1",
        login="userFTTH",
        service_type_code="INTFO",
        service_type_label="Fibra Optica",
        product="Fibra 300",
        state="Habilitado",
        service_on=True,
    )
    base.update(kw)
    return ServicioConectividad(**base)


def _svc_radio(**kw) -> ServicioConectividad:
    base = dict(
        id="svc-radio-1",
        login="userBAI",
        service_type_code="INTBA",
        service_type_label="Internet Inalambrico",
        product="Bai 15MB",
        state="Habilitado",
        service_on=True,
    )
    base.update(kw)
    return ServicioConectividad(**base)


def _onu_ok(**kw) -> EstadoOnuBcm:
    base = dict(
        numero_cliente="12345",
        encontrado=True,
        online=True,
        rx_dbm=-18.0,
        calidad_optica="buena",
    )
    base.update(kw)
    return EstadoOnuBcm(**base)


def _onu_down(**kw) -> EstadoOnuBcm:
    return _onu_ok(online=False, rx_dbm=None, calidad_optica="", **kw)


def _onu_poor(**kw) -> EstadoOnuBcm:
    return _onu_ok(rx_dbm=-29.0, calidad_optica="mala", **kw)


def _cpe_ok(**kw) -> EstadoCpeUisp:
    base = dict(
        login="userBAI",
        encontrado=True,
        online=True,
        signal_dbm=-60.0,
        calidad_senal="buena",
    )
    base.update(kw)
    return EstadoCpeUisp(**base)


def _pppoe(*, svc=None, online=True, error="", uptime="2d") -> EstadoConexionPPPoE:
    servicio = svc or _svc_ftth()
    sesion = None
    if not error:
        sesion = SesionPPPoE(
            username=servicio.login,
            online=online,
            nas="apposada",
            public_ip="10.1.2.3",
            uptime=uptime if online else "",
        )
    return EstadoConexionPPPoE(servicio=servicio, sesion=sesion, error=error)


def _eko_result(**kwargs):
    kwargs.setdefault("checked_at", CHECKED)
    return evaluar_desde_sondas_eko(**kwargs)


def _reason_via_decidir(result_bundle_kwargs) -> str | None:
    """Sanity: el adaptador y decidir() no divergen."""
    from app.services.connectivity_eko import bundle_from_probes

    bundle = bundle_from_probes(**result_bundle_kwargs)
    return decidir(bundle).reason_code


# --- Paridad de reason_code ---


def test_eko_portal_incident_active():
    outage = SimpleNamespace(
        id="out-1",
        estado="activo",
        mensaje_cliente="Incidencia en tu zona.",
        alcance="total",
        eta_minutos=45,
        eta_validada="Sí",
        started_at=CHECKED,
    )
    r = _eko_result(
        estado_pppoe=_pppoe(),
        onu=_onu_ok(),
        es_ftth=True,
        incident=incident_from_outage(outage),
    )
    assert r.diagnosis.reason_code == "incident_active"
    assert r.diagnosis.status == "outage"
    assert r.incident is not None
    assert r.incident.id == "out-1"
    assert conversational_branch_for("incident_active") == "outage"


def test_eko_portal_access_link_down_ftth():
    kwargs = dict(estado_pppoe=_pppoe(), onu=_onu_down(), es_ftth=True)
    r = _eko_result(**kwargs)
    assert r.diagnosis.reason_code == "access_link_down"
    assert _reason_via_decidir(kwargs) == "access_link_down"
    assert conversational_branch_for("access_link_down", tech="ftth") == "onu_offline"


def test_eko_portal_access_link_down_radio():
    kwargs = dict(
        estado_pppoe=_pppoe(svc=_svc_radio()),
        cpe=_cpe_ok(online=False, signal_dbm=None, calidad_senal=""),
        es_radio=True,
    )
    r = _eko_result(**kwargs)
    assert r.diagnosis.reason_code == "access_link_down"
    assert conversational_branch_for("access_link_down", tech="radio") == "cpe_offline"


def test_eko_portal_no_session():
    kwargs = dict(
        estado_pppoe=_pppoe(online=False),
        onu=_onu_ok(),
        es_ftth=True,
    )
    r = _eko_result(**kwargs)
    assert r.diagnosis.reason_code == "no_session"
    assert _reason_via_decidir(kwargs) == "no_session"
    assert conversational_branch_for("no_session") == "sin_sesion"


def test_eko_portal_link_quality_poor():
    kwargs = dict(estado_pppoe=_pppoe(), onu=_onu_poor(), es_ftth=True)
    r = _eko_result(**kwargs)
    assert r.diagnosis.reason_code == "link_quality_poor"
    assert conversational_branch_for("link_quality_poor", tech="ftth") == "potencia_mala"


def test_eko_portal_operational():
    kwargs = dict(estado_pppoe=_pppoe(), onu=_onu_ok(), es_ftth=True)
    r = _eko_result(**kwargs)
    assert r.diagnosis.status == "operational"
    assert r.diagnosis.reason_code is None
    assert _reason_via_decidir(kwargs) is None
    assert conversational_branch_for(None, status="operational") == "enlace_ok"


def test_eko_portal_sources_unavailable():
    kwargs = dict(
        estado_pppoe=_pppoe(error="radius api no configurada"),
        onu=None,
        es_ftth=True,
    )
    r = _eko_result(**kwargs)
    assert r.diagnosis.reason_code == "sources_unavailable"
    assert conversational_branch_for("sources_unavailable") == "unknown_sources"
    assert conversational_branch_for("sources_unavailable") != "sin_sesion"
    assert conversational_branch_for("sources_unavailable") != "onu_offline"


def test_eko_portal_insufficient_data():
    kwargs = dict(
        estado_pppoe=_pppoe(error="timeout reading session"),
        onu=_onu_ok(),
        es_ftth=True,
    )
    r = _eko_result(**kwargs)
    assert r.diagnosis.reason_code == "insufficient_data"
    assert conversational_branch_for("insufficient_data") == "unknown_insufficient"
    assert conversational_branch_for("insufficient_data") != "sin_sesion"


def test_eko_portal_service_selection_required():
    estado = EstadoConexionPPPoE(
        servicio=None,
        servicios=[_svc_ftth(), _svc_ftth(id="svc-ftth-2", login="otro")],
    )
    r = _eko_result(estado_pppoe=estado, needs_selection=True, freshness="none")
    assert r.diagnosis.reason_code == "service_selection_required"
    assert r.subject.service_id is None
    assert r.freshness.freshness == "none"


def test_historical_outage_is_not_incident_active():
    hist = SimpleNamespace(
        id="out-old",
        estado="resuelto",
        mensaje_cliente="Ya se resolvió.",
        alcance="total",
        eta_minutos=45,
        eta_validada="Sí",
        started_at=CHECKED,
    )
    inc = incident_from_outage(hist)
    assert inc.matched is False
    r = _eko_result(
        estado_pppoe=_pppoe(),
        onu=_onu_ok(),
        es_ftth=True,
        incident=inc,
    )
    assert r.diagnosis.reason_code is None
    assert r.diagnosis.status == "operational"
    assert r.incident is None


def test_operational_does_not_trigger_wifi_bcm_write(monkeypatch):
    called: list[str] = []

    def _boom(*_a, **_k):
        called.append("wifi")
        raise AssertionError("operational no debe escribir Wi-Fi")

    monkeypatch.setattr("app.services.wifi_bcm.turno_cambio_wifi_bcm", _boom)
    r = _eko_result(estado_pppoe=_pppoe(), onu=_onu_ok(), es_ftth=True)
    ctx: dict = {}
    aplicar_resultado_a_ctx(ctx, r)
    blob = str(r.to_dict())
    assert r.diagnosis.status == "operational"
    assert "change_wifi" not in blob
    assert "wifi_bcm" not in ctx
    assert not called
    assert r.recommendation.recommended_action == "none"


def test_conversational_question_preserves_reason_code():
    """Pregunta de luces/dispositivos no altera el veredicto técnico."""
    r = _eko_result(estado_pppoe=_pppoe(), onu=_onu_down(), es_ftth=True)
    ctx: dict = {}
    aplicar_resultado_a_ctx(ctx, r)
    assert ctx["tss_reason_code"] == "access_link_down"
    msg = mensaje_pre_triaje_acceso(
        _pppoe(),
        abonado=SimpleNamespace(servicio="internet", estado="activo", deuda_monto="0"),
        onu=_onu_down(),
        es_ftth=True,
    )
    assert msg
    assert "luces" in msg.lower() or "prendid" in msg.lower()
    ctx["pregunta_conversacional"] = msg
    assert ctx["tss_reason_code"] == "access_link_down"
    assert r.diagnosis.reason_code == "access_link_down"


def test_ctx_stamp_is_customer_safe():
    r = _eko_result(estado_pppoe=_pppoe(), onu=_onu_ok(), es_ftth=True)
    ctx: dict = {}
    aplicar_resultado_a_ctx(ctx, r)
    blob = " ".join(str(v) for v in ctx.values())
    assert "userFTTH" not in blob
    assert "apposada" not in blob
    assert "10.1.2.3" not in blob
    assert ctx["tss_status"] == "operational"
    assert ctx["tss_eko_branch"] == "enlace_ok"
    assert ctx["tss_freshness"] == "live"


def test_linea_acceso_ok_respeta_tss_no_session():
    ctx = {
        "tss_status": "impaired",
        "tss_reason_code": "no_session",
        "pppoe_rama": "wifi_lan",
        "bcm_triage": "triage=onu_ftth_enlace_ok",
    }
    assert not _linea_acceso_ok_ctx(ctx)
    assert _linea_acceso_ok_ctx({"tss_status": "operational"})
    assert _linea_acceso_ok_ctx({"pppoe_rama": "wifi_lan"})


def test_stamp_incident_activo_en_ctx():
    outage = SimpleNamespace(
        id="out-canal",
        estado="activo",
        mensaje_cliente="Corte.",
        alcance="parcial",
        eta_minutos=30,
        eta_validada="Sí",
        started_at=CHECKED,
    )
    ctx: dict = {}
    r = stamp_incident_activo_en_ctx(ctx, outage)
    assert r.diagnosis.reason_code == "incident_active"
    assert ctx["tss_incident_id"] == "out-canal"
    assert ctx["tss_eko_branch"] == "outage"


def test_canal_pppoe_stamps_tss_and_keeps_mesa_copy(monkeypatch):
    from app.services import canal_pppoe as cp
    from app.services import conexion_bcm as cb
    from app.services import conexion_pppoe as cpp
    from app.services import conexion_uisp as cu

    estado = _pppoe()
    onu = _onu_ok()
    monkeypatch.setattr(cpp, "consultar_conexion_pppoe", lambda **kw: estado)
    monkeypatch.setattr(cu, "resolve_uisp_client", lambda db=None: None)
    monkeypatch.setattr(cb, "resolve_bcm_client", lambda db=None: object())
    monkeypatch.setattr(cb, "consultar_onu_bcm", lambda *a, **k: onu)
    monkeypatch.setattr(cb, "consultar_onu_bcm_mejor_esfuerzo", lambda *a, **k: onu)

    abonado = SimpleNamespace(
        dni="30111222",
        client_number="12345",
        servicio="internet",
        estado="activo",
        deuda_monto=None,
    )
    ctx: dict = {}
    msg = cp._talvez_mensaje_pppoe(MagicMock(), abonado, ctx, "internet")
    assert msg
    assert ctx.get("tss_status") == "operational"
    assert ctx.get("tss_reason_code") == ""
    assert ctx.get("pppoe_rama") == "wifi_lan"
    assert "wifi_bcm" not in ctx
    low = msg.lower()
    assert "luces" not in low or "wifi" in low or "dispositivo" in low


def test_canal_pppoe_no_session_does_not_force_wifi_lan(monkeypatch):
    from app.services import canal_pppoe as cp
    from app.services import conexion_bcm as cb
    from app.services import conexion_pppoe as cpp
    from app.services import conexion_uisp as cu

    estado = _pppoe(online=False)
    onu = _onu_ok()
    monkeypatch.setattr(cpp, "consultar_conexion_pppoe", lambda **kw: estado)
    monkeypatch.setattr(cu, "resolve_uisp_client", lambda db=None: None)
    monkeypatch.setattr(cb, "resolve_bcm_client", lambda db=None: object())
    monkeypatch.setattr(cb, "consultar_onu_bcm_mejor_esfuerzo", lambda *a, **k: onu)

    abonado = SimpleNamespace(
        dni="30111222",
        client_number="12345",
        servicio="internet",
        estado="activo",
        deuda_monto=None,
    )
    ctx: dict = {}
    msg = cp._talvez_mensaje_pppoe(MagicMock(), abonado, ctx, "internet")
    assert msg
    assert ctx.get("tss_reason_code") == "no_session"
    assert ctx.get("pppoe_rama") != "wifi_lan"
    assert not _linea_acceso_ok_ctx(ctx)
