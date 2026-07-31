"""Tests de administración de cooperativas e importación CSV."""

from __future__ import annotations

import io
import uuid

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    r = client.post("/api/login", json={"usuario": "admin", "password": "admin"})
    assert r.status_code == 200
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_list_organizations():
    r = client.get("/api/v1/admin/organizations", headers=_admin_headers())
    assert r.status_code == 200
    orgs = r.json()["organizaciones"]
    assert any(o["slug"] == "coop-batan" for o in orgs)
    batan = next(o for o in orgs if o["slug"] == "coop-batan")
    assert "usuarios" in batan
    assert "tickets" in batan


def test_admin_create_cooperativa_and_import_csv():
    headers = _admin_headers()
    slug = f"coop-test-import-{uuid.uuid4().hex[:8]}"
    email = f"operador.test.{uuid.uuid4().hex[:8]}@import.com"

    r = client.post(
        "/api/v1/admin/organizations",
        headers=headers,
        json={"nombre": "Cooperativa Test Import", "slug": slug, "logo_label": "T"},
    )
    assert r.status_code == 200
    slug = r.json()["organizacion"]["slug"]

    csv_content = (
        "nombre,email,telefono,rol,linea_principal\n"
        f"Operador Test,{email},2235559999,cliente,2235599999\n"
    )
    r = client.post(
        f"/api/v1/admin/organizations/{slug}/import-csv",
        headers=headers,
        files={"file": ("usuarios.csv", io.BytesIO(csv_content.encode()), "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["creados"] == 1
    assert data["lineas_creadas"] == 1

    r = client.get(f"/api/v1/admin/organizations/{slug}/users", headers=headers)
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()["usuarios"]]
    assert email in emails

    r = client.post(
        "/api/login",
        json={"usuario": email, "password": "ClienteImport1"},
    )
    assert r.status_code == 200
    assert r.json()["org_slug"] == slug
    assert r.json().get("must_change_password") is True


def test_admin_forbidden_for_cooperativa():
    r = client.post("/api/login", json={"usuario": "batan", "password": "batan"})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    r = client.get("/api/v1/admin/organizations", headers=headers)
    assert r.status_code == 403


def test_admin_delete_cooperativa_cascades_users():
    headers = _admin_headers()
    slug = f"coop-del-{uuid.uuid4().hex[:8]}"
    email = f"del.user.{uuid.uuid4().hex[:8]}@test.com"

    r = client.post(
        "/api/v1/admin/organizations",
        headers=headers,
        json={"nombre": "Coop Delete Me", "slug": slug},
    )
    assert r.status_code == 200

    r = client.post(
        f"/api/v1/admin/organizations/{slug}/users",
        headers=headers,
        json={"email": email, "nombre": "Temp", "password": "TempPass12ab", "rol": "agente"},
    )
    assert r.status_code == 200, r.text

    users = client.get(f"/api/v1/admin/organizations/{slug}/users", headers=headers).json()["usuarios"]
    assert any(u["email"] == email for u in users)

    # sin confirm → 400
    bad = client.delete(f"/api/v1/admin/organizations/{slug}", headers=headers)
    assert bad.status_code == 400

    ok = client.delete(
        f"/api/v1/admin/organizations/{slug}?confirm_slug={slug}",
        headers=headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["eliminada"]["usuarios"] >= 1

    gone = client.get(f"/api/v1/admin/organizations/{slug}/users", headers=headers)
    assert gone.status_code == 404

    login = client.post("/api/login", json={"usuario": email, "password": "TempPass12ab"})
    assert login.status_code == 401


def test_admin_cannot_delete_imowi():
    headers = _admin_headers()
    r = client.delete(
        "/api/v1/admin/organizations/imowi?confirm_slug=imowi",
        headers=headers,
    )
    assert r.status_code == 400


def test_admin_user_create_edit_reset_password():
    headers = _admin_headers()
    slug = f"coop-usr-{uuid.uuid4().hex[:8]}"
    email = f"usr.{uuid.uuid4().hex[:8]}@test.com"

    assert (
        client.post(
            "/api/v1/admin/organizations",
            headers=headers,
            json={"nombre": "Coop Users", "slug": slug},
        ).status_code
        == 200
    )

    # Alta sin password → temporary_password
    created = client.post(
        f"/api/v1/admin/organizations/{slug}/users",
        headers=headers,
        json={"email": email, "nombre": "Operador Uno", "rol": "agente"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["usuario"]["email"] == email
    tmp = body.get("temporary_password")
    assert tmp and len(tmp) >= 10

    user_id = body["usuario"]["id"]

    # Editar rol
    patched = client.patch(
        f"/api/v1/admin/organizations/{slug}/users/{user_id}",
        headers=headers,
        json={"rol": "supervisor", "nombre": "Operador Uno Edit"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["usuario"]["rol"] == "supervisor"
    assert patched.json()["usuario"]["nombre"] == "Operador Uno Edit"

    # Login con temp
    login = client.post("/api/login", json={"usuario": email, "password": tmp})
    assert login.status_code == 200

    # Reset desde admin hub
    reset = client.post(
        f"/api/v1/admin/organizations/{slug}/users/{user_id}/reset-password",
        headers=headers,
    )
    assert reset.status_code == 200, reset.text
    new_tmp = reset.json()["temporary_password"]
    assert new_tmp and new_tmp != tmp

    assert client.post("/api/login", json={"usuario": email, "password": tmp}).status_code == 401
    assert client.post("/api/login", json={"usuario": email, "password": new_tmp}).status_code == 200

    # Baja
    baja = client.patch(
        f"/api/v1/admin/organizations/{slug}/users/{user_id}",
        headers=headers,
        json={"activo": False},
    )
    assert baja.status_code == 200
    assert baja.json()["usuario"]["activo"] is False
