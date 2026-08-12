"""Alerta única al primer SLA breach."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.estate import repository as repo
from app.estate.models import TicketNotification, User
from app.estate.sla_engine import apply_sla_to_ticket
from app.services.email import clear_outbox
from app.services.sla_notify import notify_sla_breach
from tests.conftest import add_ticket


def _seed_supervisor(session, org_id: str) -> User:
    u = User(
        organizacion_id=org_id,
        email="sup@coop-test.local",
        nombre="Supervisor Test",
        rol="supervisor",
        activo="Sí",
        disponibilidad="disponible",
    )
    session.add(u)
    session.commit()
    return u


def test_sla_breach_notifica_una_vez(db):
    session, org_id = db
    clear_outbox()
    _seed_supervisor(session, org_id)

    past = datetime.now(UTC) - timedelta(hours=48)
    t = add_ticket(session, org_id, id="TK-SLA-001", estado="Abierto")
    t.created_at = past
    t.sla_due_at = past + timedelta(hours=8)
    t.sla_breached_at = None
    t.estado_sla = "En plazo"
    t.nivel = "N2"
    session.commit()

    was = bool(t.sla_breached_at)
    apply_sla_to_ticket(t)
    session.commit()
    assert t.sla_breached_at is not None

    n1 = notify_sla_breach(session, t, was_breached=was)
    assert n1 >= 1
    count = (
        session.query(TicketNotification)
        .filter(
            TicketNotification.ticket_id == t.id,
            TicketNotification.canal == "sla_breach",
        )
        .count()
    )
    assert count >= 1

    # Segundo llamado con was_breached=True no duplica vía notify
    n2 = notify_sla_breach(session, t, was_breached=True)
    assert n2 == 0


def test_refresh_tickets_sla_dispara_notify(db):
    session, org_id = db
    clear_outbox()
    _seed_supervisor(session, org_id)
    past = datetime.now(UTC) - timedelta(days=2)
    t = add_ticket(session, org_id, id="TK-SLA-002", estado="Abierto")
    t.created_at = past
    t.sla_due_at = past + timedelta(hours=4)
    t.sla_breached_at = None
    session.commit()

    repo.refresh_tickets_sla(session, [t])
    session.refresh(t)
    assert t.sla_breached_at is not None
    assert (
        session.query(TicketNotification)
        .filter(TicketNotification.canal == "sla_breach", TicketNotification.ticket_id == t.id)
        .count()
        >= 1
    )

    # Segundo refresh no duplica (was_breached ya True)
    before = (
        session.query(TicketNotification)
        .filter(TicketNotification.canal == "sla_breach", TicketNotification.ticket_id == t.id)
        .count()
    )
    repo.refresh_tickets_sla(session, [t])
    after = (
        session.query(TicketNotification)
        .filter(TicketNotification.canal == "sla_breach", TicketNotification.ticket_id == t.id)
        .count()
    )
    assert after == before
