"""Cierre diferido: oferta de continuidad, rechazo, intención nueva y timeout."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy import select

import app.config as app_config
from app.estate import canal_repo as crepo
from app.estate.models import ConversacionCanal, MensajeCanal
from app.services.eko_action_runtime import ActionResult
from app.services.eko_journeys import (
    CONTINUITY_OFFER_MESSAGE,
    get_journey,
    maybe_handle_journey_turn,
    sweep_expired_continuity_offers,
)
from app.services.encuesta_satisfaccion import PREGUNTA

DIAG = "Veo una sesión de conexión activa"


def _abo():
    return SimpleNamespace(
        id="abo-dc",
        organizacion_id="org-1",
        nombre="Armando",
        dni="30111222",
        servicio="internet",
        client_number="200",
    )


def _conv():
    return SimpleNamespace(
        id="conv-dc",
        ticket_id="",
        estado="bot",
        telefono="2230000000",
        canal="portal",
        abonado_id="abo-dc",
        organizacion_id="org-1",
    )


def _enable(monkeypatch):
    monkeypatch.setattr(app_config, "EKO_JOURNEYS_ENABLED", True)


def _online():
    estado = SimpleNamespace(online=True, sesion=SimpleNamespace(online=True))
    return ActionResult(
        action="run_diagnostic_pppoe",
        status="success",
        data={"_estado": estado, "login_used": "INT1", "service_id": "svc-1"},
        user_message="resumen",
        correlation_id="c-dc",
        execution_path="runtime",
        reason_code=None,
    )


def _patch_close(bucket: dict):
    def fake_close(db, org_id, conv, canal="", **kwargs):
        conv.estado = "cerrado"
        bucket["close"] = bucket.get("close", 0) + 1
        bucket["survey"] = bucket.get("survey", 0) + 1
        return {"ok": True, "modo": "cerrado", "estado": "cerrado"}

    return patch(
        "app.services.canal_abonado._cerrar_consulta_resuelta",
        side_effect=fake_close,
    )


def _play(monkeypatch, turns: list[str], *, bucket: dict | None = None):
    _enable(monkeypatch)
    ctx: dict = {}
    conv = _conv()
    abo = _abo()
    calls: list[str] = []
    holder = bucket if bucket is not None else {"close": 0, "survey": 0}

    def dispatch(action, *args, **kwargs):
        calls.append(action)
        if action == "run_diagnostic_pppoe":
            return _online()
        return ActionResult(
            action=action,
            status="success",
            user_message="Factura 0001-1. Importe 1000.",
            data={"invoices": []},
            execution_path="runtime",
        )

    patches = [
        patch("app.services.eko_journeys._login_count", return_value=1),
        patch("app.services.eko_journeys.dispatch_runtime", side_effect=dispatch),
        patch("app.services.eko_journeys._capability_allowed", return_value=True),
        _patch_close(holder),
    ]
    with patches[0], patches[1], patches[2], patches[3]:
        out = []
        for texto in turns:
            before = len(calls)
            turn = maybe_handle_journey_turn(
                MagicMock(), "org-1", conv, abo, texto, canal="portal", ctx=ctx
            )
            out.append(
                (
                    turn,
                    list(calls[before:]),
                    conv.estado,
                    dict(get_journey(ctx)),
                )
            )
    return out, ctx, conv, holder


def test_t1_resolution_offers_continuity(monkeypatch):
    out, ctx, conv, bucket = _play(
        monkeypatch,
        ["no tengo internet", "ya se solucionó"],
    )
    diag, offer = out
    assert DIAG in (diag[0].user_message or "")
    assert diag[1] == ["run_diagnostic_pppoe"]
    assert offer[0].user_message == CONTINUITY_OFFER_MESSAGE
    assert offer[0].step == "done"
    assert offer[1] == []
    assert offer[2] == "bot"
    journey = get_journey(ctx)
    assert journey.get("continuity_pending") is True
    assert journey.get("continuity_offered_at")
    assert journey.get("resolved_ack") is True
    assert conv.estado == "bot"
    assert bucket["close"] == 0
    assert bucket["survey"] == 0


def test_t2_decline_closes_once_and_surveys(monkeypatch):
    out, _, conv, bucket = _play(
        monkeypatch,
        ["no tengo internet", "ya se solucionó", "no, gracias"],
    )
    assert out[2][0].user_message == ""
    assert out[2][0].reason_code == "explicit_conversation_close"
    assert out[2][1] == []
    assert conv.estado == "cerrado"
    assert bucket["close"] == 1
    assert bucket["survey"] == 1


def test_existing_decline_phrases_close_once(monkeypatch):
    phrases = (
        "no",
        "nop",
        "no gracias",
        "no por ahora",
        "nada más",
        "eso era todo",
        "no hace falta",
        "ya me lo dijiste",
        "solo quería",
    )
    for phrase in phrases:
        out, _, conv, bucket = _play(
            monkeypatch,
            ["no tengo internet", "ya se solucionó", phrase],
        )
        assert conv.estado == "cerrado", phrase
        assert out[2][0].user_message == "", phrase
        assert bucket["close"] == 1, phrase
        assert bucket["survey"] == 1, phrase


def test_t3_new_billing_intent_does_not_close(monkeypatch):
    out, ctx, conv, bucket = _play(
        monkeypatch,
        ["no tengo internet", "ya se solucionó", "sí, quiero consultar mi deuda"],
    )
    turn, runtime, estado, journey = out[2]
    assert turn.journey == "billing_self_service"
    assert journey.get("name") == "billing_self_service"
    assert journey.get("continuity_pending") is False
    assert estado == "bot"
    assert conv.estado == "bot"
    assert bucket["close"] == 0
    assert bucket["survey"] == 0
    assert "run_diagnostic_pppoe" not in runtime


def test_invoice_after_offer_does_not_close(monkeypatch):
    out, ctx, conv, bucket = _play(
        monkeypatch,
        ["no tengo internet", "ya se solucionó", "quiero ver mi factura"],
    )
    turn, runtime, estado, journey = out[2]
    assert turn.journey == "billing_self_service"
    assert journey.get("continuity_pending") is False
    assert "show_invoice" in runtime
    assert estado == "bot"
    assert bucket["close"] == 0
    assert bucket["survey"] == 0


def test_t4_problem_persists_stays_on_connectivity(monkeypatch):
    out, ctx, conv, bucket = _play(
        monkeypatch,
        ["no tengo internet", "ya se solucionó", "sigo teniendo problemas"],
    )
    turn, runtime, estado, journey = out[2]
    assert turn.journey == "internet_sin_conectividad"
    assert journey.get("name") == "internet_sin_conectividad"
    assert journey.get("continuity_pending") is False
    assert DIAG in (turn.user_message or "")
    assert runtime == ["run_diagnostic_pppoe"]
    assert estado == "bot"
    assert conv.estado == "bot"
    assert bucket["close"] == 0
    assert bucket["survey"] == 0


def test_t5_handoff_uses_existing_confirmation(monkeypatch):
    out, ctx, conv, bucket = _play(
        monkeypatch,
        ["no tengo internet", "ya se solucionó", "quiero hablar con una persona"],
    )
    turn, runtime, estado, journey = out[2]
    assert turn.data.get("handoff") is True
    assert turn.action == "create_ticket"
    assert turn.action_status == "needs_confirmation"
    assert journey.get("pending_confirmation") is True
    assert journey.get("continuity_pending") is False
    assert runtime == []
    assert estado == "bot"
    assert bucket["close"] == 0
    assert bucket["survey"] == 0


def test_t6_explicit_close_surveys_once(monkeypatch):
    out, _, conv, bucket = _play(
        monkeypatch,
        ["no tengo internet", "ya se solucionó", "cerrá la conversación"],
    )
    turn = out[2][0]
    assert turn.reason_code == "explicit_conversation_close"
    assert turn.user_message == ""
    assert turn.data.get("close_action") is True
    assert conv.estado == "cerrado"
    assert bucket["close"] == 1
    assert bucket["survey"] == 1


def test_t7_timeout_closes_only_expired_offer(db):
    session, org_id = db
    past = (datetime.now(UTC) - timedelta(minutes=31)).isoformat()
    fresh_at = datetime.now(UTC).isoformat()

    def _row(tel: str, offered_at: str, *, pending_confirmation: bool = False) -> ConversacionCanal:
        conv = ConversacionCanal(
            organizacion_id=org_id,
            canal="portal",
            telefono=tel,
            estado="bot",
        )
        session.add(conv)
        session.commit()
        session.refresh(conv)
        crepo.set_contexto(
            conv,
            {
                "eko_journey": {
                    "name": "internet_sin_conectividad",
                    "step": "done",
                    "continuity_pending": True,
                    "continuity_offered_at": offered_at,
                    "pending_confirmation": pending_confirmation,
                    "next_required_input": "",
                }
            },
        )
        session.commit()
        return conv

    expired = _row("2231000001", past)
    fresh = _row("2231000002", fresh_at)
    confirming = _row("2231000003", past, pending_confirmation=True)
    bucket = {"close": 0, "survey": 0}
    with _patch_close(bucket):
        closed = sweep_expired_continuity_offers(session)
    session.refresh(expired)
    session.refresh(fresh)
    session.refresh(confirming)
    assert closed == 1
    assert bucket["close"] == 1
    assert bucket["survey"] == 1
    assert expired.estado == "cerrado"
    assert fresh.estado == "bot"
    assert confirming.estado == "bot"
    assert crepo.get_contexto(expired)["eko_journey"]["continuity_pending"] is False
    assert crepo.get_contexto(fresh)["eko_journey"]["continuity_offered_at"] == fresh_at

    with _patch_close(bucket):
        closed_again = sweep_expired_continuity_offers(session)
    assert closed_again == 0
    assert bucket["close"] == 1
    assert bucket["survey"] == 1


def test_t8_courtesy_stays_silent_and_does_not_reset_clock(monkeypatch):
    for phrase in ("bien", "ok", "gracias", "muchas gracias"):
        out, _, conv, bucket = _play(
            monkeypatch,
            ["no tengo internet", "ya se solucionó", phrase],
        )
        offer_at = out[1][3].get("continuity_offered_at")
        turn, runtime, estado, journey = out[2]
        assert turn.user_message == "", phrase
        assert runtime == [], phrase
        assert estado == "bot", phrase
        assert conv.estado == "bot", phrase
        assert journey.get("continuity_pending") is True, phrase
        assert journey.get("continuity_offered_at") == offer_at, phrase
        assert journey.get("step") == "done", phrase
        assert bucket["close"] == 0, phrase
        assert bucket["survey"] == 0, phrase


def test_t9_negated_billing_intent_is_not_a_decline(monkeypatch):
    out, ctx, conv, bucket = _play(
        monkeypatch,
        ["no tengo internet", "ya se solucionó", "no, quiero consultar mi deuda"],
    )
    turn, runtime, estado, journey = out[2]
    assert turn.journey == "billing_self_service"
    assert journey.get("continuity_pending") is False
    assert estado == "bot"
    assert conv.estado == "bot"
    assert bucket["close"] == 0
    assert bucket["survey"] == 0
    assert "run_diagnostic_pppoe" not in runtime


def test_unrecognized_text_stays_silent(monkeypatch):
    out, _, conv, bucket = _play(
        monkeypatch,
        ["no tengo internet", "ya se solucionó", "asdf qwerty"],
    )
    turn, runtime, estado, journey = out[2]
    assert turn.user_message == ""
    assert runtime == []
    assert estado == "bot"
    assert journey.get("continuity_pending") is True
    assert journey.get("step") == "done"
    assert bucket["close"] == 0
    assert bucket["survey"] == 0
    assert conv.estado == "bot"


def test_bare_thanks_is_not_a_resolution_offer(monkeypatch):
    out, ctx, conv, bucket = _play(
        monkeypatch,
        ["no tengo internet", "gracias"],
    )
    assert out[1][0].user_message != CONTINUITY_OFFER_MESSAGE
    assert get_journey(ctx).get("continuity_pending") is not True
    assert conv.estado == "bot"
    assert bucket["close"] == 0


def _seed_pending_offer(
    session,
    org_id: str,
    tel: str,
    *,
    offered_at: str,
    estado: str = "bot",
    canal: str = "portal",
) -> ConversacionCanal:
    conv = ConversacionCanal(
        organizacion_id=org_id,
        canal=canal,
        telefono=tel,
        estado=estado,
        abonado_id="",
        ticket_id="",
    )
    session.add(conv)
    session.commit()
    session.refresh(conv)
    crepo.set_contexto(
        conv,
        {
            "eko_journey": {
                "name": "internet_sin_conectividad",
                "step": "done",
                "continuity_pending": True,
                "continuity_offered_at": offered_at,
                "resolved_ack": True,
                "pending_confirmation": False,
                "next_required_input": "",
                "last_action": "run_diagnostic_pppoe",
                "last_diagnostic_result": "pppoe_session_up",
                "intent": "internet",
                "domain": "internet",
                "correlation_id": "c-real",
            },
            "pppoe_informado": True,
        },
    )
    session.commit()
    return conv


def _assert_real_survey(session, conv: ConversacionCanal) -> None:
    session.refresh(conv)
    ctx = crepo.get_contexto(conv)
    assert conv.estado == "cerrado"
    assert ctx.get("encuesta_pendiente") is True
    assert ctx.get("encuesta_enviada") is True
    assert ctx.get("encuesta_origen")
    assert ctx.get("encuesta_enviada_at")
    texts = session.scalars(
        select(MensajeCanal.texto).where(MensajeCanal.conversacion_id == conv.id)
    ).all()
    assert sum(1 for texto in texts if PREGUNTA in (texto or "")) == 1


def _close_with_real_n1(
    monkeypatch, session, conv: ConversacionCanal, texto: str, *, canal: str = "portal"
) -> None:
    _enable(monkeypatch)
    ctx = crepo.get_contexto(conv)
    turn = maybe_handle_journey_turn(
        session, conv.organizacion_id, conv, None, texto, canal=canal, ctx=ctx
    )
    assert turn is not None
    assert turn.user_message == ""
    crepo.set_contexto(conv, ctx)
    session.commit()


def test_real_decline_keeps_survey(db, monkeypatch):
    session, org_id = db
    conv = _seed_pending_offer(
        session, org_id, "2233000001", offered_at=datetime.now(UTC).isoformat()
    )
    _close_with_real_n1(monkeypatch, session, conv, "no, gracias")
    _assert_real_survey(session, conv)


def test_real_explicit_close_keeps_survey(db, monkeypatch):
    session, org_id = db
    conv = _seed_pending_offer(
        session, org_id, "2233000002", offered_at=datetime.now(UTC).isoformat()
    )
    _close_with_real_n1(monkeypatch, session, conv, "cerrá la conversación")
    _assert_real_survey(session, conv)


def test_real_timeout_keeps_survey(db):
    session, org_id = db
    past = (datetime.now(UTC) - timedelta(minutes=31)).isoformat()
    conv = _seed_pending_offer(session, org_id, "2233000003", offered_at=past)
    closed = sweep_expired_continuity_offers(session)
    assert closed == 1
    _assert_real_survey(session, conv)
    assert crepo.get_contexto(conv)["eko_journey"]["continuity_pending"] is False
    closed_again = sweep_expired_continuity_offers(session)
    assert closed_again == 0
    _assert_real_survey(session, conv)
