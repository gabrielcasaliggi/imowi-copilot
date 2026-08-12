"""Notificaciones al pasar conversación a espera_agente."""

from __future__ import annotations

from app.estate import canal_repo as crepo
from app.estate.models import TicketNotification, User
from app.services.email import clear_outbox, get_outbox
from app.services.handoff_notify import notify_espera_agente


def _seed_agent(session, org_id: str) -> User:
    u = User(
        organizacion_id=org_id,
        email="agente@coop-test.local",
        nombre="Agente Test",
        rol="agente",
        activo="Sí",
        disponibilidad="disponible",
    )
    session.add(u)
    session.commit()
    return u


def test_notify_espera_agente_crea_notif_y_es_idempotente(db):
    session, org_id = db
    clear_outbox()
    _seed_agent(session, org_id)

    conv = crepo.get_or_create_conversacion(
        session, org_id, telefono="5491111222333", canal="web", wa_id="5491111222333"
    )
    conv.estado = "bot"
    session.commit()

    assert notify_espera_agente(session, conv, prev_estado="bot") == 0

    conv.estado = "espera_agente"
    session.commit()
    n2 = notify_espera_agente(session, conv, prev_estado="bot")
    assert n2 >= 1

    notifs = (
        session.query(TicketNotification)
        .filter(
            TicketNotification.organizacion_id == org_id,
            TicketNotification.canal == "inbox_handoff",
        )
        .all()
    )
    assert len(notifs) >= 1
    assert any(n.destinatario == "agente@coop-test.local" for n in notifs)
    assert get_outbox()

    assert notify_espera_agente(session, conv, prev_estado="espera_agente") == 0
    count_after = (
        session.query(TicketNotification)
        .filter(
            TicketNotification.organizacion_id == org_id,
            TicketNotification.canal == "inbox_handoff",
        )
        .count()
    )
    assert count_after == len(notifs)


def test_notify_no_spam_si_ya_en_cola(db):
    session, org_id = db
    clear_outbox()
    _seed_agent(session, org_id)
    conv = crepo.get_or_create_conversacion(
        session, org_id, telefono="5499999888777", canal="whatsapp", wa_id="5499999888777"
    )
    conv.estado = "espera_agente"
    session.commit()
    assert notify_espera_agente(session, conv, prev_estado="espera_agente") == 0
    assert (
        session.query(TicketNotification)
        .filter(TicketNotification.canal == "inbox_handoff")
        .count()
        == 0
    )
