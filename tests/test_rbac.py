"""Tests del catálogo RBAC y autorización por rol/tenant."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.rbac import (
    catalogo_roles,
    normalizar_rol_consola,
    permisos_para_rol,
    puede,
    roles_alta_permitidos,
)
from main import app

client = TestClient(app)


def _login(usuario: str, password: str) -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": usuario, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_normalizar_roles_legacy():
    assert normalizar_rol_consola("admin_sistema", "imowi") == "admin"
    assert normalizar_rol_consola("ingeniero_noc", "imowi") == "admin"
    assert normalizar_rol_consola("ingeniero_noc", "coop-batan") == "supervisor"
    assert normalizar_rol_consola("admin_org") == "supervisor"
    assert normalizar_rol_consola("cliente") == "agente"
    assert normalizar_rol_consola("ejecutivo") == "ejecutivo"


def test_matriz_permisos_basica():
    assert puede("admin", "orgs.manage")
    assert puede("admin", "bot.configure")
    assert puede("supervisor", "tickets.reassign")
    assert puede("supervisor", "users.manage_agents")
    assert not puede("supervisor", "bot.configure")
    assert puede("ejecutivo", "stats.bot")
    assert puede("ejecutivo", "reports.export")
    assert not puede("ejecutivo", "tickets.queue.view")
    assert puede("agente", "tickets.queue.view")
    assert puede("agente", "agent.availability")
    assert not puede("agente", "stats.agents")
    assert "orgs.manage" not in permisos_para_rol("agente")
    assert len(catalogo_roles()) == 4


def test_roles_alta_supervisor_solo_agente():
    assert roles_alta_permitidos(actor_rol="supervisor", org_slug="coop-batan") == frozenset({"agente"})
    assert "supervisor" in roles_alta_permitidos(actor_rol="admin", org_slug="coop-batan")
    assert "admin" in roles_alta_permitidos(actor_rol="admin", org_slug="imowi")


def test_login_roles_distintos_en_jwt():
    for user, pwd, rol in (
        ("admin", "admin", "admin"),
        ("supervisor", "supervisor", "supervisor"),
        ("ejecutivo", "ejecutivo", "ejecutivo"),
        ("batan", "batan", "agente"),
    ):
        r = client.post("/api/login", json={"usuario": user, "password": pwd})
        assert r.status_code == 200, r.text
        assert r.json()["rol"] == rol
        me = client.get("/api/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
        assert me.status_code == 200
        body = me.json()
        assert body["rol"] == rol
        assert isinstance(body.get("permisos"), list)
        assert len(body["permisos"]) > 0


def test_ejecutivo_no_ve_cola_si_ve_stats_bot():
    headers = _login("ejecutivo", "ejecutivo")
    r = client.get("/api/v1/tickets", headers=headers)
    assert r.status_code == 403
    r = client.get("/api/v1/analytics/executive", headers=headers)
    assert r.status_code == 200
    assert r.json()["alcance"] == "organizacion"


def test_agente_ve_cola_no_stats_global():
    headers = _login("batan", "batan")
    r = client.get("/api/v1/tickets", headers=headers)
    assert r.status_code == 200
    r = client.get("/api/v1/analytics/executive", headers=headers)
    assert r.status_code == 403


def test_supervisor_lista_y_crea_agentes_org():
    headers = _login("supervisor", "supervisor")
    r = client.get("/api/v1/org/users", headers=headers)
    assert r.status_code == 200
    email = f"agente.rbac.{uuid.uuid4().hex[:8]}@coopbatan.com"
    r = client.post(
        "/api/v1/org/users",
        headers=headers,
        json={"email": email, "nombre": "Agente RBAC", "password": "Secreto123!", "rol": "agente"},
    )
    assert r.status_code == 200, r.text
    user_id = r.json()["usuario"]["id"]
    assert r.json()["usuario"]["rol"] == "agente"

    # No puede crear ejecutivo
    r = client.post(
        "/api/v1/org/users",
        headers=headers,
        json={
            "email": f"ejec.{uuid.uuid4().hex[:8]}@coopbatan.com",
            "nombre": "Ejec",
            "password": "Secreto123!",
            "rol": "ejecutivo",
        },
    )
    assert r.status_code == 403

    r = client.patch(
        f"/api/v1/org/users/{user_id}",
        headers=headers,
        json={"activo": False},
    )
    assert r.status_code == 200
    assert r.json()["usuario"]["activo"] is False


def test_admin_rbac_catalog_and_user_patch():
    headers = _login("admin", "admin")
    r = client.get("/api/v1/rbac/roles", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["roles"]) == 4
    r = client.get("/api/v1/rbac/permissions", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["permisos"]) >= 10

    email = f"sup.rbac.{uuid.uuid4().hex[:8]}@coopbatan.com"
    r = client.post(
        "/api/v1/admin/organizations/coop-batan/users",
        headers=headers,
        json={"email": email, "nombre": "Sup Test", "password": "Secreto123!", "rol": "supervisor"},
    )
    assert r.status_code == 200, r.text
    uid = r.json()["usuario"]["id"]
    r = client.patch(
        f"/api/v1/admin/organizations/coop-batan/users/{uid}",
        headers=headers,
        json={"activo": False},
    )
    assert r.status_code == 200
    assert r.json()["usuario"]["activo"] is False


def test_agente_availability():
    headers = _login("batan", "batan")
    r = client.patch(
        "/api/v1/me/availability",
        headers=headers,
        json={"disponibilidad": "ausente"},
    )
    assert r.status_code == 200
    assert r.json()["disponibilidad"] == "ausente"
