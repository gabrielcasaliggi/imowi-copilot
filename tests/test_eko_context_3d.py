"""Fase 3D — contrato factual interno consolidado (tickets + OV públicos)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.radius.contract import ServicioConectividad
from app.services.abonado_tickets import load_ticket_facts, ticket_fact_item
from app.services.canal_pppoe import _talvez_mensaje_pppoe
from app.services.eco_voice import build_contexto_abonado
from app.services.eko_context import (
    build_eko_facts,
    has_positive_debt,
    load_ov_facts,
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
        "telefono_e164": "",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _ticket(**kwargs):
    defaults = {
        "id": "tkt-1",
        "organizacion_id": "org-1",
        "estado": "Abierto",
        "categoria": "Internet",
        "origen": "WhatsApp",
        "linea": "2235551234",
        "created_at": None,
        "updated_at": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# --- Contract ---


def test_3d_facts_contract_domains():
    facts = build_eko_facts(_abonado(), db=None)
    assert set(facts.keys()) >= {
        "customer",
        "account",
        "services",
        "billing",
        "tickets",
        "ov",
        "meta",
    }
    assert facts["meta"]["probes"] is False
    assert facts["customer"]["display_name"] == "María Pérez"
    assert "dni" not in (facts["customer"] or {})
    assert facts["tickets"]["status"] == "omitted"  # sin db
    assert facts["ov"]["available"] is True
    assert "pay" in facts["ov"]["links"]
    assert "invoice" in facts["ov"]["links"]
    assert "payment_slip" in facts["ov"]["links"]
    assert facts["ov"]["auth"] == "external"
    assert "sid" not in facts["ov"]
    assert "tsid" not in facts["ov"]
    assert "jsat_session" not in facts["ov"]
    blob = str(facts["ov"]).lower()
    assert "password" not in blob
    assert "cookie" not in blob


def test_3d_ov_facts_public_only_no_jsat_call():
    with patch(
        "app.services.ov_handoff.request_ov_handoff",
        side_effect=AssertionError("no JSAT en facts"),
    ):
        ov = load_ov_facts(db=None)
    assert ov["available"] is True
    assert ov["links"]["pay"].startswith("https://")
    assert "/#/" in ov["links"]["pay"]


# --- Tickets ---


def test_3d_ticket_facts_scoped_no_foreign():
    abo = _abonado(id="abo-mine", linea_msisdn="2231110000")
    mine = _ticket(id="mine-1", linea="2231110000", organizacion_id="org-1")
    foreign_id = "foreign-9"

    def _fake_list(db, org_id, abo_arg):
        assert abo_arg.id == "abo-mine"
        # Solo el propio — simula ownership del reader
        return [(mine, "conv-1")]

    with patch(
        "app.services.abonado_tickets.list_tickets_visibles_abonado",
        side_effect=_fake_list,
    ):
        block = load_ticket_facts(abo, db=MagicMock(), org_id="org-1")

    assert block["status"] == "ok"
    ids = {i["id"] for i in block["items"]}
    assert "mine-1" in ids
    assert foreign_id not in ids
    item = block["items"][0]
    assert set(item.keys()) >= {
        "id",
        "state",
        "category",
        "origin",
        "created_at",
        "updated_at",
        "conversation_id",
    }
    assert "eventos" not in item
    assert "prompt" not in item


def test_3d_ticket_fact_item_no_internal_fields():
    t = _ticket(id="x", estado="Cerrado", categoria="Facturación", origen="Portal")
    item = ticket_fact_item(t, conversation_id="c1")
    assert item["state"] == "Cerrado"
    assert item["conversation_id"] == "c1"
    assert "visible_cliente" not in item


def test_3d_build_eko_facts_includes_tickets_when_db():
    abo = _abonado()
    mine = _ticket(id="t1", linea="2235551234")
    with (
        patch(
            "app.services.abonado_tickets.list_tickets_visibles_abonado",
            return_value=[(mine, "cv1")],
        ),
        patch(
            "app.services.portal_services.evaluar_servicios_portal",
            return_value={"status": "empty", "services": []},
        ),
    ):
        facts = build_eko_facts(abo, db=MagicMock(), org_id="org-1")
    assert facts["tickets"]["status"] == "ok"
    assert facts["tickets"]["items"][0]["id"] == "t1"
    txt = build_contexto_abonado(abo, db=MagicMock(), org_id="org-1")
    # rebuild contexto usa facts — patch nuevamente
    with (
        patch(
            "app.services.abonado_tickets.list_tickets_visibles_abonado",
            return_value=[(mine, "cv1")],
        ),
        patch(
            "app.services.portal_services.evaluar_servicios_portal",
            return_value={"status": "empty", "services": []},
        ),
    ):
        txt = build_contexto_abonado(abo, db=MagicMock(), org_id="org-1")
    assert "## TICKETS" in txt
    assert "ov_link_pay:" in txt or "ov_available: true" in txt


# --- Billing / services / multi / probes ---


def test_3d_billing_unavailable_not_zero():
    f = build_eko_facts(None)
    assert f["billing"]["status"] == "unavailable"
    assert f["billing"]["balance"] is None
    assert has_positive_debt(f) is False


def test_3d_services_active_is_commercial():
    catalog = {
        "status": "ok",
        "services": [
            {"id": "1", "type": "internet", "label": "Fibra", "active": True},
            {"id": "2", "type": "movil", "label": "IMOWI", "active": False},
            {"id": "3", "type": "tv", "label": "Sensa", "active": True},
        ],
        "checked_at": "t",
        "reason_code": None,
    }
    with patch("app.services.portal_services.evaluar_servicios_portal", return_value=catalog):
        facts = build_eko_facts(_abonado(), db=MagicMock())
    assert {i["type"] for i in facts["services"]["items"]} == {"internet", "movil", "tv"}
    assert facts["services"]["items"][1]["active"] is False


def test_3d_multi_account_no_silent_selection():
    abo = _abonado()
    ctx: dict = {}
    s1 = ServicioConectividad(
        login="A", service_type_code="INTFO", state="Habilitado",
        service_on=True, id="1", base_account_number="200",
    )
    s2 = ServicioConectividad(
        login="B", service_type_code="INTFO", state="Habilitado",
        service_on=True, id="2", base_account_number="201",
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


def test_3d_build_eko_facts_zero_technical_probes():
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
        patch(
            "app.services.ov_handoff.request_ov_handoff",
            side_effect=AssertionError("JSAT"),
        ),
        patch(
            "app.services.abonado_tickets.list_tickets_visibles_abonado",
            return_value=[],
        ),
        patch(
            "app.services.portal_services.evaluar_servicios_portal",
            return_value={"status": "empty", "services": []},
        ),
    ):
        for _ in range(2):
            build_eko_facts(abo, db=MagicMock(), org_id="org-1")
            build_contexto_abonado(abo, db=MagicMock(), org_id="org-1")

    assert pppoe.call_count == 0
    assert bcm.call_count == 0
    assert uisp.call_count == 0
    assert outage.call_count == 0


def test_3d_security_no_full_dni_in_facts_or_prompt():
    abo = _abonado(dni="30111222")
    facts = build_eko_facts(abo)
    assert "30111222" not in str(facts)
    txt = build_contexto_abonado(abo)
    assert "30111222" not in txt
    assert "dni_enmascarado:" in txt


def test_3d_semantic_alignment_includes_tickets_ov():
    facts = build_eko_facts(_abonado())
    shape = semantic_alignment_with_summary_shape(facts)
    assert "tickets" in shape
    assert "ov" in shape
    assert shape["ov"]["auth"] == "external"
