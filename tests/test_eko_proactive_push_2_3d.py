"""Eko 2.3D — Proactive Push Adapter: XOR, whitelist, policy gates."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.estate import repository as repo
from app.estate.models import Abonado, PortalDevice
from app.services import app_push
from app.services.eko_proactive_contract import SUPPORTED_PROACTIVE_EVENTS, ProactiveEvent
from app.services.eko_proactive_policy import (
    authorize_outage_push,
    evaluate_proactive_notification,
    suppress_decision,
)
from app.services.eko_proactive_push import deliver_proactive_push


def _add_abonado(session, org_id: str, *, dni: str) -> Abonado:
    abo = Abonado(
        organizacion_id=org_id,
        dni=dni,
        nombre=f"Test {dni}",
        telefono_e164="",
        servicio="internet",
        estado="activo",
    )
    session.add(abo)
    session.commit()
    session.refresh(abo)
    return abo


def _add_device(session, org_id: str, *, dni: str, token: str) -> PortalDevice:
    row = PortalDevice(
        organizacion_id=org_id,
        dni_normalized=dni,
        expo_push_token=token,
        platform="android",
        activo="Sí",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _add_outage(session, org_id: str, *, nas: str = "nas-a"):
    return repo.create_network_outage(
        session,
        org_id,
        nas_shortname=nas,
        nas_ip="",
        comentario="test",
        mensaje_cliente="Hay una incidencia en tu zona.",
        eta_validada="No",
        created_by="test",
    )


def _allow_started(org_id: str, outage_id: str, msg: str = "msg"):
    return authorize_outage_push(
        event_type="outage.started",
        org_id=org_id,
        outage_id=outage_id,
        customer_message=msg,
        customer_title="Corte en la red",
    )


# --- TEST 1–3: ALLOW → exactly 1 push ---


def test_23d_01_outage_started_allow_one_push(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23010001")
    _add_device(session, org_id, dni="23010001", token="ExponentPushToken[t1]")
    calls = []

    def _send(tokens, *, title, body, data=None):
        calls.append({"tokens": list(tokens), "data": dict(data or {})})
        return {"ok": True, "sent": len(tokens)}

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(app_push, "enviar_push_expo", side_effect=_send),
    ):
        r = deliver_proactive_push(
            session, _allow_started(org_id, o.id), nas_shortname="nas-a"
        )

    assert r["decision"] == "ALLOW"
    assert r["sent"] == 1
    assert r["provider_ok"] is True
    assert len(calls) == 1
    assert calls[0]["data"]["event"] == "declared"
    assert calls[0]["data"]["tipo"] == "incidente"
    assert "nas" not in calls[0]["data"]


def test_23d_02_outage_material_update_allow_one_push(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23010002")
    _add_device(session, org_id, dni="23010002", token="ExponentPushToken[t2]")
    calls = []

    def _send(tokens, *, title, body, data=None):
        calls.append(1)
        return {"ok": True, "sent": len(tokens)}

    decision = authorize_outage_push(
        event_type="outage.material_update",
        org_id=org_id,
        outage_id=o.id,
        customer_message="Actualización material",
    )
    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(app_push, "enviar_push_expo", side_effect=_send),
    ):
        r = deliver_proactive_push(
            session, decision, nas_shortname="nas-a"
        )

    assert r["sent"] == 1
    assert len(calls) == 1


def test_23d_03_outage_resolved_allow_one_push(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23010003")
    _add_device(session, org_id, dni="23010003", token="ExponentPushToken[t3]")
    calls = []

    def _send(tokens, *, title, body, data=None):
        calls.append(dict(data or {}))
        return {"ok": True, "sent": len(tokens)}

    decision = authorize_outage_push(
        event_type="outage.resolved",
        org_id=org_id,
        outage_id=o.id,
    )
    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(app_push, "enviar_push_expo", side_effect=_send),
    ):
        r = deliver_proactive_push(
            session, decision, nas_shortname="nas-a"
        )

    assert r["sent"] == 1
    assert len(calls) == 1
    assert calls[0]["event"] == "resolved"


# --- TEST 4: duplicate ---


def test_23d_04_duplicate_declared_zero_extra(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23010004")
    _add_device(session, org_id, dni="23010004", token="ExponentPushToken[t4]")

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(
            app_push,
            "enviar_push_expo",
            return_value={"ok": True, "sent": 1},
        ) as send,
    ):
        d = _allow_started(org_id, o.id)
        r1 = deliver_proactive_push(session, d, nas_shortname="nas-a")
        r2 = deliver_proactive_push(session, d, nas_shortname="nas-a")

    assert r1["sent"] == 1
    assert r2.get("skipped") == "already_declared"
    assert r2["sent"] == 0
    assert send.call_count == 1


# --- TEST 5: no device ---


def test_23d_05_no_device_zero_push(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    # abonado sin device → affected puede ser >0 pero tokens vacíos
    _add_abonado(session, org_id, dni="23010005")

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(
            app_push,
            "enviar_push_expo",
            side_effect=lambda tokens, **kw: {"ok": True, "sent": len(tokens)},
        ) as send,
    ):
        r = deliver_proactive_push(
            session, _allow_started(org_id, o.id), nas_shortname="nas-a"
        )

    assert r["sent"] == 0
    # app_push llama Expo con lista vacía (short-circuit sent=0); no hay dispositivos.
    if send.called:
        assert send.call_args[0][0] == []


# --- TEST 6: ownership unresolved ---


def test_23d_06_ownership_unresolved_zero_push(db):
    session, org_id = db
    decision = authorize_outage_push(
        event_type="outage.started",
        org_id="",  # missing org
        outage_id="x",
        customer_message="msg",
    )
    assert decision.decision == "SUPPRESS"
    assert decision.suppression_reason == "OWNERSHIP_UNRESOLVED"

    with patch.object(app_push, "enviar_push_expo") as send:
        r = deliver_proactive_push(session, decision, nas_shortname="nas-a")

    assert r["sent"] == 0
    assert r.get("skipped")
    send.assert_not_called()


# --- TEST 7–8: SUPPRESS / NOT_ELIGIBLE ---


def test_23d_07_policy_suppress_zero_push(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    event = ProactiveEvent(
        event_type="outage.started",
        source="estate.network_outages",
        source_event_id=o.id,
        outage_id=o.id,
        organizacion_id=org_id,
        customer_message="msg",
        source_authority="AUTHORITATIVE",
    )
    decision = suppress_decision(event, reason_code="CUSTOMER_SUPPRESSED")

    with patch.object(app_push, "notificar_incidente_app") as notify:
        r = deliver_proactive_push(session, decision, nas_shortname="nas-a")

    assert r["sent"] == 0
    assert r["skipped"] == "CUSTOMER_SUPPRESSED"
    notify.assert_not_called()


def test_23d_08_policy_not_eligible_zero_push(db):
    from app.services.eko_proactive_contract import ProactiveDecision

    session, org_id = db
    event = ProactiveEvent(
        event_type="outage.started",
        source="estate.network_outages",
        source_event_id="1",
        outage_id="1",
        organizacion_id=org_id,
        customer_message="msg",
        source_authority="AUTHORITATIVE",
    )
    decision = ProactiveDecision(
        decision="NOT_ELIGIBLE",
        event=event,
        suppression_reason="SIGNAL_NOT_SUPPORTED",
        reason="forced_not_eligible",
    )

    with patch.object(app_push, "notificar_incidente_app") as notify:
        r = deliver_proactive_push(session, decision)
    assert r["sent"] == 0
    assert r["skipped"] == "SIGNAL_NOT_SUPPORTED"
    notify.assert_not_called()


# --- TEST 9–12: other domains rejected ---


def test_23d_09_billing_zero_push(db):
    session, org_id = db
    event = ProactiveEvent(
        event_type="billing.invoice_available",
        source="billtrack",
        source_event_id="inv-1",
        organizacion_id=org_id,
        client_number="123",
        customer_message="Factura",
        source_authority="TRUSTED_READ",
    )
    decision = evaluate_proactive_notification(event)
    assert decision.decision == "NOT_ELIGIBLE"
    assert decision.suppression_reason == "SIGNAL_NOT_SUPPORTED"
    with patch.object(app_push, "enviar_push_expo") as send:
        r = deliver_proactive_push(session, decision)
    assert r["sent"] == 0
    send.assert_not_called()


def test_23d_10_ticket_policy_allow_but_no_owner_zero_expo(db):
    """2.3G-B: ticket.* habilitado en policy; sin dueño/devices → 0 Expo."""
    session, org_id = db
    decision = evaluate_proactive_notification(
        ProactiveEvent(
            event_type="ticket.updated",
            source="estate.ticket_events",
            source_event_id="ev-no-owner",
            ticket_id="T-NO-OWNER",
            organizacion_id=org_id,
            source_authority="AUTHORITATIVE",
            customer_message="update",
            customer_title="t",
        )
    )
    assert decision.decision == "ALLOW"
    with patch.object(app_push, "enviar_push_expo") as send:
        r = deliver_proactive_push(session, decision)
    assert r["sent"] == 0
    assert r.get("skipped") == "OWNERSHIP_UNRESOLVED"
    send.assert_not_called()


def test_23d_11_connectivity_zero_push(db):
    session, org_id = db
    decision = evaluate_proactive_notification(
        ProactiveEvent(
            event_type="connectivity.down",
            source="portal",
            source_event_id="s1",
            organizacion_id=org_id,
            source_authority="DERIVED",
            customer_message="down",
        )
    )
    assert decision.suppression_reason == "SIGNAL_NOT_SUPPORTED"
    with patch.object(app_push, "enviar_push_expo") as send:
        assert deliver_proactive_push(session, decision)["sent"] == 0
    send.assert_not_called()


def test_23d_12_service_zero_push(db):
    session, org_id = db
    decision = evaluate_proactive_notification(
        ProactiveEvent(
            event_type="service.changed",
            source="api_service",
            source_event_id="svc1",
            organizacion_id=org_id,
            source_authority="TRUSTED_READ",
            customer_message="changed",
        )
    )
    assert decision.suppression_reason == "SIGNAL_NOT_SUPPORTED"
    with patch.object(app_push, "enviar_push_expo") as send:
        assert deliver_proactive_push(session, decision)["sent"] == 0
    send.assert_not_called()


# --- TEST 13: legacy + proactive XOR → 1 push ---


def test_23d_13_legacy_plus_adapter_exactly_one_push(db):
    """Si alguien llama adapter y luego notificar_* legacy, claim garantiza 1 Expo."""
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23010013")
    _add_device(session, org_id, dni="23010013", token="ExponentPushToken[t13]")

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(
            app_push,
            "enviar_push_expo",
            return_value={"ok": True, "sent": 1},
        ) as send,
    ):
        r1 = deliver_proactive_push(
            session, _allow_started(org_id, o.id), nas_shortname="nas-a"
        )
        # Camino legacy directo (solo debería dedupear)
        r2 = app_push.notificar_incidente_app(
            session,
            org_id,
            title="Corte",
            body="msg",
            outage_id=o.id,
            nas_shortname="nas-a",
        )

    assert r1["sent"] == 1
    assert r2.get("skipped") == "already_declared"
    assert r2["sent"] == 0
    assert send.call_count == 1


def test_23d_13b_api_create_uses_adapter_only(db):
    """Router create no llama notificar_* directo: solo deliver_proactive_push."""
    from app.api.v1 import outages as outages_api

    session, org_id = db
    ctx = MagicMock()
    ctx.organizacion_id = org_id
    ctx.organizacion_slug = "coop"
    ctx.usuario_email = "ops@test"
    ctx.usuario_nombre = "Ops"
    body = outages_api.OutageCreate(
        nas_shortname="nas-a",
        comentario="Fibra cortada",
        eta_minutos=45,
        usar_ia=False,
    )
    fake = MagicMock()
    fake.id = "out-xor"
    fake.nas_ip = ""
    fake.nas_shortname = "nas-a"
    fake.started_at = None

    with (
        patch.object(outages_api.outage_svc, "outage_activo_para_nas", return_value=None),
        patch.object(
            outages_api.outage_svc,
            "health_nas",
            side_effect=RuntimeError("skip"),
        ),
        patch.object(outages_api.repo, "create_network_outage", return_value=fake),
        patch.object(
            outages_api.outage_svc,
            "generar_mensaje_cliente",
            return_value="Mensaje",
        ),
        patch.object(outages_api.repo, "update_network_outage", return_value=fake),
        patch.object(
            outages_api.outage_svc,
            "outage_to_dict",
            return_value={"id": "out-xor", "estado": "activo"},
        ),
        patch(
            "app.services.eko_proactive_push.deliver_proactive_push",
            return_value={"ok": True, "sent": 1},
        ) as deliver,
        patch("app.services.app_push.notificar_incidente_app") as legacy,
    ):
        result = outages_api.create_outage(body, ctx, session)

    assert result["status"] == "creado"
    assert deliver.call_count == 1
    legacy.assert_not_called()


# --- TEST 14: non-material → 0 ---


def test_23d_14_non_material_update_zero_push(db):
    from app.api.v1 import outages as outages_api
    from app.services import outages as outage_svc

    session, org_id = db
    o = _add_outage(session, org_id)
    # Solo comentario interno → no material
    assert (
        outage_svc.outage_update_es_material(
            prev_mensaje_cliente=o.mensaje_cliente,
            new_mensaje_cliente=o.mensaje_cliente,
            prev_eta_minutos=45,
            new_eta_minutos=45,
            prev_eta_validada="No",
            new_eta_validada="No",
            prev_alcance="total",
            new_alcance="total",
            touched_comentario=True,
            touched_alcance=False,
            touched_eta_minutos=False,
            touched_eta_validada=False,
            touched_tipo=False,
        )
        is False
    )

    ctx = MagicMock()
    ctx.organizacion_id = org_id
    body = outages_api.OutageUpdate(comentario="nota interna ops", usar_ia=False)

    with (
        patch.object(
            outages_api.outage_svc,
            "generar_mensaje_cliente",
            return_value=o.mensaje_cliente,
        ),
        patch.object(
            outages_api.outage_svc,
            "outage_to_dict",
            return_value={"id": o.id, "estado": "activo"},
        ),
        patch(
            "app.services.eko_proactive_push.deliver_proactive_push",
        ) as deliver,
        patch.object(app_push, "enviar_push_expo") as send,
    ):
        outages_api.update_outage(o.id, body, ctx, session)

    deliver.assert_not_called()
    send.assert_not_called()


# --- TEST 15: provider failure ---


def test_23d_15_provider_failure_not_false_success(db):
    session, org_id = db
    o = _add_outage(session, org_id)
    _add_abonado(session, org_id, dni="23010015")
    _add_device(session, org_id, dni="23010015", token="ExponentPushToken[t15]")

    with (
        patch("app.services.outages.abonado_afectado_por_nas", return_value=True),
        patch.object(
            app_push,
            "enviar_push_expo",
            return_value={"ok": False, "sent": 0, "status": 500},
        ),
    ):
        r = deliver_proactive_push(
            session, _allow_started(org_id, o.id), nas_shortname="nas-a"
        )

    assert r["ok"] is False
    assert r["provider_ok"] is False
    assert r["sent"] == 0
    # Claim puede haberse tomado (intento); no confundir con éxito de delivery
    assert r.get("skipped") is None or r["ok"] is False


def test_23d_whitelist_includes_outage_and_ticket_events():
    assert "outage.started" in SUPPORTED_PROACTIVE_EVENTS
    assert "outage.material_update" in SUPPORTED_PROACTIVE_EVENTS
    assert "outage.resolved" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.created" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.updated" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.closed" in SUPPORTED_PROACTIVE_EVENTS
    assert "ticket.resolved" not in SUPPORTED_PROACTIVE_EVENTS
    assert "billing.invoice_issued" not in SUPPORTED_PROACTIVE_EVENTS
