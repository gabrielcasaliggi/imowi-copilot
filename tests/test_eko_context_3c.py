"""Fase 3C — consolidación factual: consumers N1 vía Eko Facts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.radius.contract import ServicioConectividad
from app.services.canal_abonado import (
    _abonado_cortado_por_deuda,
    _account_status,
    _billing_amount_str,
    _deuda_positiva,
    _servicio_abonado,
)
from app.services.canal_pppoe import _talvez_mensaje_pppoe
from app.services.eco_voice import build_contexto_abonado, enrich_contexto_desde_integraciones
from app.services.eko_context import (
    account_status,
    billing_amount_str,
    build_eko_facts,
    has_positive_debt,
    is_commercially_cut,
    service_types_present,
    servicio_agregado,
)
from app.services.protocolo_mesa import clasificar_cuenta


def _abonado(**kwargs):
    defaults = {
        "id": "abo-1",
        "organizacion_id": "org-1",
        "nombre": "María Pérez",
        "dni": "30111222",
        "servicio": "internet",
        "plan": "100Mb",
        "estado": "activo",
        "deuda_monto": "1500.00",
        "linea_msisdn": "2235551234",
        "client_number": "200",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# --- A. Billing ---


def test_3c_billing_deuda_positiva_cero_stale_unavailable():
    f_pos = build_eko_facts(_abonado(deuda_monto="2500.50"))
    assert has_positive_debt(f_pos) is True
    assert billing_amount_str(f_pos) == "2500.50"
    assert f_pos["billing"]["status"] == "stale"

    f_zero = build_eko_facts(_abonado(deuda_monto="0", estado="activo"))
    assert has_positive_debt(f_zero) is False
    assert billing_amount_str(f_zero) == "0"
    assert f_zero["billing"]["status"] == "stale"  # stale ≠ al día

    f_unav = build_eko_facts(None)
    assert f_unav["billing"]["status"] == "unavailable"
    assert billing_amount_str(f_unav) is None
    assert has_positive_debt(f_unav) is False  # unavailable ≠ $0 / al día

    # Helpers canal_abonado leen Facts
    assert _deuda_positiva(_abonado(deuda_monto="10")) is True
    assert _deuda_positiva(_abonado(deuda_monto="0")) is False
    assert _billing_amount_str(_abonado(deuda_monto="99.00")) == "99.00"
    assert _deuda_positiva(None) is False


# --- B. Account ---


def test_3c_account_status_comercial_not_technical():
    for est in ("activo", "corte", "suspendido", "baja"):
        facts = build_eko_facts(_abonado(estado=est, deuda_monto="0"))
        assert account_status(facts) == est
        assert _account_status(_abonado(estado=est)) == est

    assert is_commercially_cut(build_eko_facts(_abonado(estado="corte"))) is True
    assert is_commercially_cut(build_eko_facts(_abonado(estado="activo"))) is False
    assert _abonado_cortado_por_deuda(_abonado(estado="suspendido", deuda_monto="0")) is True
    assert clasificar_cuenta(_abonado(estado="baja"), None) == "baja"
    assert clasificar_cuenta(_abonado(estado="corte"), None) == "corte"
    # activo comercial ≠ online técnico
    assert account_status(build_eko_facts(_abonado(estado="activo"))) == "activo"


# --- C. Services ---


def test_3c_services_internet_imowi_sensa_multi():
    abo = _abonado(servicio="ambos")
    assert servicio_agregado(build_eko_facts(abo)) == "ambos"
    assert _servicio_abonado(abo) == "ambos"

    catalog = {
        "status": "ok",
        "services": [
            {"id": "1", "type": "internet", "label": "Fibra", "product": "100", "active": True},
            {"id": "2", "type": "movil", "label": "IMOWI", "product": "IMOWI", "active": True},
            {"id": "3", "type": "tv", "label": "Sensa", "product": "Sensa", "active": False},
        ],
        "checked_at": "t",
        "reason_code": None,
    }
    with patch("app.services.portal_services.evaluar_servicios_portal", return_value=catalog):
        facts = build_eko_facts(abo, db=MagicMock())
    types = service_types_present(facts)
    assert types == {"internet", "movil", "tv"}
    assert facts["services"]["items"][0]["active"] is True
    assert facts["services"]["items"][2]["active"] is False  # comercial, no técnico


# --- D. Multi-account ---


def test_3c_multi_account_sin_seleccion():
    abo = _abonado(servicio="internet")
    ctx: dict = {}
    s1 = ServicioConectividad(
        login="INT1", service_type_code="INTFO", state="Habilitado",
        service_on=True, id="a", base_account_number="200",
    )
    s2 = ServicioConectividad(
        login="INT2", service_type_code="INTFO", state="Habilitado",
        service_on=True, id="b", base_account_number="201",
    )
    with (
        patch("app.services.billtrack.lookup_servicios_conectividad", return_value=[s1, s2]),
        patch("app.services.conexion_pppoe.consultar_conexion_pppoe") as radius,
        patch(
            "app.services.billtrack.mensaje_seleccion_cuenta_internet",
            return_value="¿Cuál?",
        ),
    ):
        msg = _talvez_mensaje_pppoe(MagicMock(), abo, ctx, "internet")
    assert msg == "¿Cuál?"
    assert ctx.get("multi_cuenta_pendiente") is True
    radius.assert_not_called()


def test_3c_multi_account_con_seleccion():
    abo = _abonado(servicio="internet")
    ctx = {"login_seleccionado": "INT2"}
    from app.radius.contract import EstadoConexionPPPoE, SesionPPPoE

    s1 = ServicioConectividad(
        login="INT1", service_type_code="INTFO", state="Habilitado",
        service_on=True, id="a", base_account_number="200",
    )
    s2 = ServicioConectividad(
        login="INT2", service_type_code="INTFO", state="Habilitado",
        service_on=True, id="b", base_account_number="201",
    )
    estado = EstadoConexionPPPoE(
        servicio=s2,
        sesion=SesionPPPoE(username="INT2", online=True, nas="N1"),
        servicios=[s1, s2],
    )
    with (
        patch("app.services.billtrack.lookup_servicios_conectividad", return_value=[s1, s2]),
        patch("app.services.conexion_pppoe.consultar_conexion_pppoe", return_value=estado) as radius,
        patch("app.services.conexion_uisp.resolve_uisp_client", return_value=None),
        patch("app.services.conexion_bcm.resolve_bcm_client", return_value=None),
        patch("app.services.protocolo_mesa.rama_comercial", return_value=False),
        patch("app.services.connectivity_eko.evaluar_desde_sondas_eko", return_value=None),
        patch("app.services.conexion_pppoe.mensaje_abonado_pppoe", return_value="ok"),
    ):
        msg = _talvez_mensaje_pppoe(MagicMock(), abo, ctx, "internet_ftth")
    assert msg
    assert radius.call_count >= 1


# --- E. No auto-probe ---


def test_3c_normal_context_zero_probes():
    abo = _abonado()
    with (
        patch(
            "app.services.conexion_pppoe.contexto_pppoe_para_abonado",
            side_effect=AssertionError("Radius"),
        ) as pppoe,
        patch(
            "app.services.conexion_bcm.contexto_bcm_para_abonado",
            side_effect=AssertionError("BCM"),
        ) as bcm,
        patch(
            "app.services.conexion_uisp.contexto_uisp_para_abonado",
            side_effect=AssertionError("UISP"),
        ) as uisp,
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            side_effect=AssertionError("outage"),
        ) as outage,
    ):
        # Decisiones comerciales vía Facts tampoco disparan probes
        assert _deuda_positiva(abo) is True
        assert _servicio_abonado(abo) == "internet"
        assert _account_status(abo) == "activo"
        build_contexto_abonado(abo)
        enrich_contexto_desde_integraciones(abo)

    pppoe.assert_not_called()
    bcm.assert_not_called()
    uisp.assert_not_called()
    outage.assert_not_called()


# --- Security ---


def test_3c_facts_helpers_no_full_dni():
    abo = _abonado(dni="30111222")
    facts = build_eko_facts(abo)
    assert "30111222" not in str(facts.get("customer"))
    txt = build_contexto_abonado(abo)
    assert "30111222" not in txt
    assert "dni_enmascarado:" in txt
