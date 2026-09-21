"""Fase 3B — Eko Facts como fuente factual primaria del contexto N1."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.radius.contract import ServicioConectividad
from app.services.canal_pppoe import _talvez_mensaje_pppoe
from app.services.eco_voice import build_contexto_abonado, enrich_contexto_desde_integraciones
from app.services.eko_context import (
    build_eko_facts,
    extract_technical_observations,
    format_n1_contexto,
    semantic_alignment_with_summary_shape,
)


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


def _probe_patches():
    return (
        patch(
            "app.services.conexion_pppoe.contexto_pppoe_para_abonado",
            side_effect=AssertionError("Radius auto-probe"),
        ),
        patch(
            "app.services.conexion_bcm.contexto_bcm_para_abonado",
            side_effect=AssertionError("BCM auto-probe"),
        ),
        patch(
            "app.services.conexion_uisp.contexto_uisp_para_abonado",
            side_effect=AssertionError("UISP auto-probe"),
        ),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            side_effect=AssertionError("Radius consult"),
        ),
        patch(
            "app.services.conexion_bcm.consultar_onu_bcm",
            side_effect=AssertionError("BCM consult"),
        ),
        patch(
            "app.services.conexion_uisp.consultar_cpe_uisp",
            side_effect=AssertionError("UISP consult"),
        ),
        patch(
            "app.services.outages.abonado_afectado_por_nas",
            side_effect=AssertionError("outage"),
        ),
    )


# --- A. Facts from Eko Facts ---


def test_3b_n1_receives_customer_account_services_billing_from_facts():
    abo = _abonado()
    catalog = {
        "status": "ok",
        "services": [
            {
                "id": "s1",
                "type": "internet",
                "label": "Fibra 100",
                "product": "100Mb",
                "active": True,
                "line_msisdn": None,
            }
        ],
        "checked_at": "2026-09-21T12:00:00+00:00",
        "reason_code": None,
    }
    with patch("app.services.portal_services.evaluar_servicios_portal", return_value=catalog):
        facts = build_eko_facts(abo, db=MagicMock())
        txt = build_contexto_abonado(abo, db=MagicMock())

    assert facts["customer"]["display_name"] == "María Pérez"
    assert facts["account"]["client_number"] == "200"
    assert facts["account"]["status"] == "activo"
    assert facts["services"]["status"] == "ok"
    assert facts["services"]["items"][0]["active"] is True
    assert facts["billing"]["balance"]["amount"] == "1500.00"

    assert "## CUSTOMER FACTS" in txt
    assert "## ACCOUNT FACTS" in txt
    assert "## SERVICES" in txt
    assert "## BILLING" in txt
    assert "## TECHNICAL OBSERVATIONS" in txt
    assert "María Pérez" in txt
    assert "nro_asociado: 200" in txt
    assert "deuda_monto: 1500.00" in txt
    assert "billing_status: stale" in txt
    assert "servicios_catalogo:" in txt
    assert "internet:Fibra 100(activo)" in txt
    # Semántica comercial explícita
    assert "active en catálogo es comercial" in txt


# --- B. No auto-probe ---


def test_3b_normal_context_repeated_zero_probes():
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
        for _ in range(3):
            build_contexto_abonado(abo)
            enrich_contexto_desde_integraciones(abo)

    pppoe.assert_not_called()
    bcm.assert_not_called()
    uisp.assert_not_called()
    outage.assert_not_called()


# --- C / D. Observations + no re-probe ---


def test_3b_technical_observation_reused_without_reprobe():
    abo = _abonado()
    extras = {
        "bcm_resumen": "estado=en_linea; rx=-22.0dBm",
        "bcm_triage": "onu_ftth_enlace_ok",
        "pppoe_resumen": "estado=conectado",
        "pppoe_triage": "linea_ok_indagar_wifi",
    }
    with (
        patch(
            "app.services.conexion_bcm.contexto_bcm_para_abonado",
            side_effect=AssertionError("BCM re-probe"),
        ) as bcm,
        patch(
            "app.services.conexion_pppoe.contexto_pppoe_para_abonado",
            side_effect=AssertionError("Radius re-probe"),
        ) as radius,
        patch(
            "app.services.conexion_uisp.contexto_uisp_para_abonado",
            side_effect=AssertionError("UISP re-probe"),
        ) as uisp,
        patch(
            "app.services.conexion_bcm.consultar_onu_bcm",
            side_effect=AssertionError("BCM consult"),
        ),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            side_effect=AssertionError("Radius consult"),
        ),
    ):
        t1 = build_contexto_abonado(abo, extras=extras)
        t2 = build_contexto_abonado(abo, extras=extras)

    assert "onu_ftth_enlace_ok" in t1
    assert "onu_ftth_enlace_ok" in t2
    assert "conectado" in t2
    bcm.assert_not_called()
    radius.assert_not_called()
    uisp.assert_not_called()

    obs = extract_technical_observations(extras)
    assert "bcm_resumen" in obs
    assert "pppoe_resumen" in obs
    assert "canal" not in obs


# --- E. Billing ---


def test_3b_billing_deuda_positiva_cero_stale_unavailable():
    f_pos = build_eko_facts(_abonado(deuda_monto="2500.50"))
    assert f_pos["billing"]["status"] == "stale"
    assert f_pos["billing"]["balance"]["amount"] == "2500.50"
    assert f_pos["billing"]["balance"]["as_of"] is None

    f_zero = build_eko_facts(_abonado(deuda_monto="0"))
    assert f_zero["billing"]["balance"]["amount"] == "0"
    assert f_zero["billing"]["status"] == "stale"  # stale != «al día»

    f_unav = build_eko_facts(None)
    assert f_unav["billing"]["status"] == "unavailable"
    assert f_unav["billing"]["balance"] is None  # unavailable != $0

    t_unav = build_contexto_abonado(None)
    assert "billing_status: unavailable" in t_unav
    assert "deuda: (sin dato)" in t_unav

    t_zero = build_contexto_abonado(_abonado(deuda_monto="0"))
    factual = "\n".join(
        ln
        for ln in t_zero.splitlines()
        if ln.startswith("- ")
        and "Regla" not in ln
        and "Si billing_status" not in ln
        and "NO digas" not in ln
    )
    assert "deuda_monto: 0" in factual
    assert "Cuenta al día" not in factual


# --- F. Multi-account ---


def test_3b_multi_account_sin_seleccion_no_probe():
    abo = _abonado(servicio="internet")
    ctx: dict = {}
    s1 = ServicioConectividad(
        login="INT1",
        service_type_code="INTFO",
        service_type_label="Fibra",
        product="100Mb",
        state="Habilitado",
        service_on=True,
        base_account_number="200",
        id="a",
    )
    s2 = ServicioConectividad(
        login="INT2",
        service_type_code="INTFO",
        service_type_label="Fibra",
        product="100Mb",
        state="Habilitado",
        service_on=True,
        base_account_number="201",
        id="b",
    )
    with (
        patch(
            "app.services.billtrack.lookup_servicios_conectividad",
            return_value=[s1, s2],
        ),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            side_effect=AssertionError("no Radius sin selección"),
        ) as radius,
        patch(
            "app.services.conexion_bcm.consultar_onu_bcm",
            side_effect=AssertionError("no BCM"),
        ),
        patch(
            "app.services.conexion_uisp.consultar_cpe_uisp",
            side_effect=AssertionError("no UISP"),
        ),
        patch(
            "app.services.billtrack.mensaje_seleccion_cuenta_internet",
            return_value="¿Cuál de tus cuentas?",
        ),
        patch(
            "app.services.protocolo_mesa.rama_comercial",
            return_value=False,
        ),
    ):
        msg = _talvez_mensaje_pppoe(MagicMock(), abo, ctx, "internet")

    assert msg == "¿Cuál de tus cuentas?"
    assert ctx.get("multi_cuenta_pendiente") is True
    assert not ctx.get("login_seleccionado")
    radius.assert_not_called()
    # Facts no eligen services[0] silenciosamente
    facts = build_eko_facts(abo, db=None)
    assert facts["services"]["status"] in ("empty", "unavailable", "ok")


def test_3b_multi_account_con_seleccion_permite_diagnostico():
    abo = _abonado(servicio="internet")
    ctx = {"login_seleccionado": "INT1", "multi_cuenta_pendiente": False}
    from app.radius.contract import EstadoConexionPPPoE, SesionPPPoE

    s1 = ServicioConectividad(
        login="INT1",
        service_type_code="INTFO",
        service_type_label="Fibra",
        product="100Mb",
        state="Habilitado",
        service_on=True,
        base_account_number="200",
        id="a",
    )
    s2 = ServicioConectividad(
        login="INT2",
        service_type_code="INTFO",
        service_type_label="Fibra",
        product="50Mb",
        state="Habilitado",
        service_on=True,
        base_account_number="201",
        id="b",
    )
    estado = EstadoConexionPPPoE(
        servicio=s1,
        sesion=SesionPPPoE(username="INT1", online=True, nas="NAS1"),
        servicios=[s1, s2],
    )
    with (
        patch(
            "app.services.billtrack.lookup_servicios_conectividad",
            return_value=[s1, s2],
        ),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
            return_value=estado,
        ) as radius,
        patch(
            "app.services.conexion_uisp.resolve_uisp_client",
            return_value=None,
        ),
        patch(
            "app.services.conexion_bcm.resolve_bcm_client",
            return_value=None,
        ),
        patch(
            "app.services.protocolo_mesa.rama_comercial",
            return_value=False,
        ),
        patch(
            "app.services.connectivity_eko.evaluar_desde_sondas_eko",
            return_value=None,
        ),
        patch(
            "app.services.conexion_pppoe.mensaje_abonado_pppoe",
            return_value="Revisé tu conexión.",
        ),
    ):
        msg = _talvez_mensaje_pppoe(MagicMock(), abo, ctx, "internet_ftth")

    assert msg
    assert radius.call_count >= 1


# --- G / contract ---


def test_3b_factual_contract_aligns_with_customer_summary_semantics():
    """Detecta divergencia semántica futura Facts ↔ Summary (sin HTTP)."""
    abo = _abonado()
    catalog = {
        "status": "ok",
        "services": [
            {
                "id": "svc-1",
                "type": "internet",
                "label": "Fibra",
                "product": "100Mb",
                "active": True,
                "line_msisdn": None,
            },
            {
                "id": "svc-2",
                "type": "movil",
                "label": "IMOWI",
                "product": "IMOWI",
                "active": False,
                "line_msisdn": "2231112222",
            },
        ],
        "checked_at": "t",
        "reason_code": None,
    }
    with patch("app.services.portal_services.evaluar_servicios_portal", return_value=catalog):
        facts = build_eko_facts(abo, db=MagicMock())

    shape = semantic_alignment_with_summary_shape(facts)
    assert set(shape.keys()) >= {"customer", "account", "billing", "services"}
    assert shape["customer"]["display_name"] == "María Pérez"
    assert shape["account"]["client_number"] == "200"
    assert shape["account"]["status"] == "activo"
    assert shape["billing"]["status"] == "stale"
    assert shape["billing"]["balance"]["currency"] == "ARS"
    assert shape["billing"]["balance"]["freshness"] == "snapshot"
    assert shape["billing"]["balance"]["as_of"] is None
    # active = comercial (servicio 2 False no implica offline técnico)
    assert shape["services"]["items"][0]["active"] is True
    assert shape["services"]["items"][1]["active"] is False
    assert shape["services"]["items"][0]["type"] == "internet"


def test_3b_prompt_not_dual_legacy_abonado_fields_as_primary():
    """deuda/estado/plan salen de Facts; no hay bloque paralelo legacy conflictivo."""
    abo = _abonado(deuda_monto="99.00", estado="suspendido", plan="50Mb")
    facts = build_eko_facts(abo)
    txt = format_n1_contexto(
        facts,
        extras={},
        dni_enmascarado="30***222",
    )
    assert txt.count("deuda_monto:") == 1
    assert txt.count("billing_status:") == 1
    assert "deuda_monto: 99.00" in txt
    assert "estado_servicio: suspendido" in txt
    assert "plan: 50Mb" in txt
    assert "## CUSTOMER FACTS" in txt


# --- Security ---


def test_3b_factual_context_omits_full_dni_and_session_secrets():
    abo = _abonado(dni="30111222")
    txt = build_contexto_abonado(abo)
    assert "30111222" not in txt
    assert "dni_enmascarado:" in txt
    assert "30***222" in txt
    for secret in ("jwt", "JWT", "sid=", "tsid", "cookie", "Authorization"):
        assert secret not in txt


def test_3b_conversation_state_section_when_canal_present():
    abo = _abonado()
    txt = build_contexto_abonado(abo, extras={"canal": "whatsapp", "tecnologia_acceso": "ftth"})
    assert "## CONVERSATION STATE" in txt
    assert "canal: whatsapp" in txt
    assert "tecnologia_acceso: ftth" in txt
