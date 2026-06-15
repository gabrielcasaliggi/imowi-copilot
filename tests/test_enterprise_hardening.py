"""Tests de hardening enterprise: seguridad, SLA y auditoría."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.estate import repository as repo
from app.estate.models import Ticket, User
from app.estate.security import hash_password, is_hashed, valid_password, verify_password
from app.estate.sla_engine import apply_sla_to_ticket, compute_sla, resolve_policy
from main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_password_hash_and_verify():
    hashed = hash_password("secreto123")
    assert is_hashed(hashed)
    assert verify_password("secreto123", hashed)
    assert not verify_password("otra", hashed)
    assert not valid_password("abc")


def test_login_migra_password_plano(db_session: Session):
    org = repo.get_org_by_slug(db_session, "coop-batan")
    assert org
    email = f"legacy.plain.{uuid.uuid4().hex[:8]}@test.com"
    user = User(
        organizacion_id=org.id,
        email=email,
        nombre="Legacy Plain",
        password="legacyplain",
        rol="cliente",
    )
    db_session.add(user)
    db_session.commit()

    r = client.post("/api/login", json={"usuario": email, "password": "legacyplain"})
    assert r.status_code == 200

    db_session.refresh(user)
    assert is_hashed(user.password)
    assert user.last_login_at is not None


def test_create_user_rechaza_clave_corta():
    headers = _admin_headers()
    r = client.post(
        "/api/v1/admin/organizations/coop-batan/users",
        headers=headers,
        json={"email": "corto@test.com", "nombre": "Corto", "password": "123"},
    )
    assert r.status_code == 400


def test_sla_politicas_por_nivel():
    t_n1 = Ticket(id="JSC-T1", organizacion_id="x", nivel="N1", categoria="General")
    policy, hours = resolve_policy(t_n1)
    assert policy == "n1_standard"
    assert hours == 24

    t_n2 = Ticket(id="JSC-T2", organizacion_id="x", nivel="N2")
    _, hours_n2 = resolve_policy(t_n2)
    assert hours_n2 == 8

    t_crit = Ticket(id="JSC-T3", organizacion_id="x", proveedor="JSC Core")
    _, hours_crit = resolve_policy(t_crit)
    assert hours_crit == 4


def test_sla_vencido(db_session: Session):
    org = repo.get_org_by_slug(db_session, "coop-batan")
    assert org
    t = Ticket(
        id="JSC-SLA-TEST",
        organizacion_id=org.id,
        nivel="N2",
        estado="Abierto",
        created_at=datetime.now(UTC) - timedelta(hours=10),
    )
    apply_sla_to_ticket(t, now=datetime.now(UTC))
    sla = compute_sla(t, now=datetime.now(UTC))
    assert sla["vencido"] is True
    assert sla["estado_sla"] == "Vencido"
    assert "Vencido hace" in sla["label"]


def test_auditoria_usuario_y_ticket(db_session: Session):
    headers = _admin_headers()
    slug = f"coop-audit-{uuid.uuid4().hex[:8]}"
    email = f"audit.user.{uuid.uuid4().hex[:8]}@test.com"

    r = client.post(
        "/api/v1/admin/organizations",
        headers=headers,
        json={"nombre": "Coop Audit", "slug": slug},
    )
    assert r.status_code == 200

    r = client.post(
        f"/api/v1/admin/organizations/{slug}/users",
        headers=headers,
        json={"email": email, "nombre": "Audit User", "password": "cliente123"},
    )
    assert r.status_code == 200

    org = repo.get_org_by_slug(db_session, slug)
    assert org
    t = repo.create_ticket(
        db_session,
        org.id,
        linea="2235000000",
        dispositivo="Test",
        descripcion_falla="SLA audit",
        origen="Test",
        nivel="N1",
    )

    r = client.put(
        f"/api/v1/tickets/{t.id}",
        headers=headers,
        json={"estado": "En progreso"},
    )
    assert r.status_code == 200

    r = client.get("/api/v1/admin/audit", headers=headers)
    assert r.status_code == 200
    acciones = {e["accion"] for e in r.json()["eventos"]}
    assert "cooperativa_alta" in acciones
    assert "usuario_alta" in acciones
    assert "ticket_actualizacion" in acciones
