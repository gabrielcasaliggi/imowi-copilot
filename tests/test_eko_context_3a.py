"""Fase 3A — contexto N1 sin auto-probes + diagnóstico explícito."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.radius.contract import ServicioConectividad
from app.services.canal_pppoe import _talvez_mensaje_pppoe
from app.services.eco_voice import build_contexto_abonado, enrich_contexto_desde_integraciones
from app.services.eko_context import build_eko_facts


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


def test_normal_context_zero_radius_bcm_uisp_outage():
    """Gate 3A: construir contexto normal no dispara probes técnicos."""
    abo = _abonado()
    with (
        patch(
            "app.services.conexion_pppoe.contexto_pppoe_para_abonado",
            side_effect=AssertionError("Radius auto-probe"),
        ) as pppoe,
        patch(
            "app.services.conexion_bcm.contexto_bcm_para_abonado",
            side_effect=AssertionError("BCM auto-probe"),
        ) as bcm,
        patch(
            "app.services.conexion_uisp.contexto_uisp_para_abonado",
            side_effect=AssertionError("UISP auto-probe"),
        ) as uisp,
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
    ):
        txt = build_contexto_abonado(abo)
        enrich = enrich_contexto_desde_integraciones(abo)

    assert "identificado" in txt
    assert "María Pérez" in txt
    assert "deuda_monto: 1500.00" in txt
    assert "billing_status: stale" in txt
    assert "billing_freshness: snapshot" in txt
    assert enrich["pppoe_resumen"] == ""
    assert enrich["bcm_resumen"] == ""
    assert enrich["uisp_resumen"] == ""
    pppoe.assert_not_called()
    bcm.assert_not_called()
    uisp.assert_not_called()


def test_normal_context_facts_preserved_without_probes():
    abo = _abonado(deuda_monto="0", estado="activo", client_number="200")
    facts = build_eko_facts(abo, db=None)
    assert facts["customer"]["display_name"] == "María Pérez"
    assert facts["account"]["status"] == "activo"
    assert facts["account"]["client_number"] == "200"
    assert facts["billing"]["status"] == "stale"
    assert facts["billing"]["balance"]["amount"] == "0"
    assert facts["billing"]["balance"]["freshness"] == "snapshot"
    assert facts["billing"]["balance"]["as_of"] is None
    assert facts["meta"]["probes"] is False

    txt = build_contexto_abonado(abo)
    assert "deuda_monto: 0" in txt
    assert "billing_status: stale" in txt
    # El bloque factual no afirma «Cuenta al día» como estado (sí puede aparecer en reglas).
    factual = "\n".join(
        ln for ln in txt.splitlines() if ln.startswith("- ") and "Regla" not in ln
        and "Si billing_status" not in ln and "NO digas" not in ln
    )
    assert "Cuenta al día" not in factual
    assert "- estado_servicio: activo" in txt


def test_billing_unavailable_facts_never_become_zero_invented():
    """unavailable sin amount no inventa $0 en adapter (abonado ausente)."""
    facts = build_eko_facts(None)
    assert facts["billing"]["status"] == "unavailable"
    assert facts["billing"]["balance"] is None


def test_extras_observation_still_injected_without_live_probe():
    """Tras diagnóstico explícito, extras (ctx) alimentan el prompt sin re-probe."""
    abo = _abonado()
    with (
        patch(
            "app.services.conexion_pppoe.contexto_pppoe_para_abonado",
            side_effect=AssertionError("no auto"),
        ),
        patch(
            "app.services.conexion_bcm.contexto_bcm_para_abonado",
            side_effect=AssertionError("no auto"),
        ),
        patch(
            "app.services.conexion_uisp.contexto_uisp_para_abonado",
            side_effect=AssertionError("no auto"),
        ),
    ):
        txt = build_contexto_abonado(
            abo,
            extras={
                "pppoe_resumen": "tipo=Fibra; login=userBAI; estado=conectado",
                "pppoe_triage": "linea_ok_indagar_wifi",
                "bcm_resumen": "estado=en_linea; rx=-22.0dBm",
                "bcm_triage": "onu_ftth_enlace_ok",
            },
        )
    assert "conectado" in txt
    assert "onu_ftth_enlace_ok" in txt
    assert "userBAI" in txt


def test_include_technical_true_still_can_probe():
    """Legacy path explícito include_technical=True conserva readers."""
    abo = _abonado()
    called = {"pppoe": 0}

    def _fake_pppoe(_abo, db=None):
        called["pppoe"] += 1
        return {"pppoe_resumen": "estado=conectado", "pppoe_triage": "x"}

    with (
        patch(
            "app.services.conexion_pppoe.contexto_pppoe_para_abonado",
            side_effect=_fake_pppoe,
        ),
        patch(
            "app.services.conexion_bcm.contexto_bcm_para_abonado",
            return_value={},
        ),
        patch(
            "app.services.conexion_uisp.contexto_uisp_para_abonado",
            return_value={},
        ),
    ):
        enrich_contexto_desde_integraciones(abo, include_technical=True)
        build_contexto_abonado(abo, include_technical=True)

    assert called["pppoe"] >= 1


def test_explicit_pppoe_diagnosis_invokes_radius():
    abo = _abonado(servicio="internet")
    ctx: dict = {}
    from app.radius.contract import EstadoConexionPPPoE, SesionPPPoE

    svc = ServicioConectividad(
        login="soloBAI",
        service_type_code="INTFO",
        service_type_label="Fibra",
        product="100Mb",
        state="Habilitado",
        service_on=True,
        base_account_number="200",
        id="s1",
    )
    estado = EstadoConexionPPPoE(
        servicio=svc,
        sesion=SesionPPPoE(username="soloBAI", online=True, nas="NAS1"),
        servicios=[svc],
    )

    with (
        patch(
            "app.services.billtrack.lookup_servicios_conectividad",
            return_value=[svc],
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
        msg = _talvez_mensaje_pppoe(
            MagicMock(),
            abo,
            ctx,
            "internet_ftth",
        )

    assert radius.call_count >= 1
    assert ctx.get("pppoe_resumen")
    assert msg is not None


def test_multi_cuenta_no_silent_radius_selection():
    """2 logins sin login_seleccionado → selección, sin consultar Radius."""
    abo = _abonado(servicio="internet")
    ctx: dict = {}
    s1 = ServicioConectividad(
        login="unoBAI",
        service_type_code="INTFO",
        state="Habilitado",
        service_on=True,
        id="1",
        base_account_number="200",
    )
    s2 = ServicioConectividad(
        login="dosBAI",
        service_type_code="INTFO",
        state="Habilitado",
        service_on=True,
        id="2",
        base_account_number="200",
    )
    with (
        patch(
            "app.services.billtrack.lookup_servicios_conectividad",
            return_value=[s1, s2],
        ),
        patch(
            "app.services.conexion_pppoe.consultar_conexion_pppoe",
        ) as radius,
        patch(
            "app.services.billtrack.mensaje_seleccion_cuenta_internet",
            return_value="¿Cuál de tus cuentas?",
        ) as sel,
    ):
        msg = _talvez_mensaje_pppoe(MagicMock(), abo, ctx, "internet")

    assert msg == "¿Cuál de tus cuentas?"
    assert ctx.get("multi_cuenta_pendiente") is True
    radius.assert_not_called()
    sel.assert_called_once()


def test_multi_cuenta_with_login_selected_probes():
    abo = _abonado(servicio="internet")
    ctx = {"login_seleccionado": "dosBAI"}
    s1 = ServicioConectividad(
        login="unoBAI", service_type_code="INTFO", state="Habilitado",
        service_on=True, id="1", base_account_number="200",
    )
    s2 = ServicioConectividad(
        login="dosBAI", service_type_code="INTFO", state="Habilitado",
        service_on=True, id="2", base_account_number="200",
    )
    from app.radius.contract import EstadoConexionPPPoE, SesionPPPoE

    estado = EstadoConexionPPPoE(
        servicio=s2,
        sesion=SesionPPPoE(username="dosBAI", online=True),
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
        patch("app.services.conexion_uisp.resolve_uisp_client", return_value=None),
        patch("app.services.conexion_bcm.resolve_bcm_client", return_value=None),
        patch("app.services.protocolo_mesa.rama_comercial", return_value=False),
        patch("app.services.connectivity_eko.evaluar_desde_sondas_eko", return_value=None),
        patch(
            "app.services.conexion_pppoe.mensaje_abonado_pppoe",
            return_value="ok",
        ),
    ):
        _talvez_mensaje_pppoe(MagicMock(), abo, ctx, "internet")

    radius.assert_called()
    assert radius.call_args.kwargs.get("login") == "dosBAI" or (
        len(radius.call_args.args) >= 0
        and radius.call_args.kwargs.get("login") == "dosBAI"
    )


def test_explicit_bcm_reader_still_callable():
    from app.bcm.contract import EstadoOnuBcm
    from app.services.conexion_bcm import consultar_onu_bcm

    onu = EstadoOnuBcm(
        numero_cliente="200",
        encontrado=True,
        online=True,
        rx_dbm=-22.0,
        calidad_optica="buena",
    )
    with patch(
        "app.services.conexion_bcm.resolve_bcm_client",
    ) as resolve:
        client = MagicMock()
        client.buscar_onu_por_cliente.return_value = onu
        resolve.return_value = client
        out = consultar_onu_bcm("200")
    assert out.encontrado is True
    assert out.rx_dbm == -22.0
    client.buscar_onu_por_cliente.assert_called_once_with("200")


def test_explicit_uisp_reader_still_callable():
    from app.services.conexion_uisp import consultar_cpe_uisp
    from app.uisp.contract import EstadoCpeUisp

    cpe = EstadoCpeUisp(login="xBAI", encontrado=True, online=True, signal_dbm=-60.0)
    client = MagicMock()
    client.buscar_cpe_por_login.return_value = cpe
    with patch(
        "app.services.conexion_uisp.resolve_uisp_client",
        return_value=client,
    ):
        out = consultar_cpe_uisp("xBAI")
    assert out.online is True
    assert out.signal_dbm == -60.0
    client.buscar_cpe_por_login.assert_called_once_with("xBAI")


def test_explicit_outage_reader_still_callable():
    from app.services.outages import abonado_afectado_por_nas

    abo = _abonado()
    with (
        patch(
            "app.services.conexion_pppoe.resolve_radius_client",
            return_value=None,
        ),
    ):
        # Sin radius → False (fail closed), pero la función sigue existiendo.
        assert abonado_afectado_por_nas(MagicMock(), abo, "NAS1") is False
