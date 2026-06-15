"""Tests de administración de cooperativas e importación CSV."""

from __future__ import annotations

import io

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
    slug = "coop-test-import-py"

    r = client.post(
        "/api/v1/admin/organizations",
        headers=headers,
        json={"nombre": "Cooperativa Test Import", "slug": slug, "logo_label": "T"},
    )
    assert r.status_code == 200
    slug = r.json()["organizacion"]["slug"]

    csv_content = (
        "nombre,email,telefono,rol,linea_principal\n"
        "Operador Test,operador.test@import.com,2235559999,cliente,2235599999\n"
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
    assert "operador.test@import.com" in emails

    r = client.post(
        "/api/login",
        json={"usuario": "operador.test@import.com", "password": "cliente"},
    )
    assert r.status_code == 200
    assert r.json()["org_slug"] == slug


def test_admin_forbidden_for_cooperativa():
    r = client.post("/api/login", json={"usuario": "batan", "password": "batan"})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    r = client.get("/api/v1/admin/organizations", headers=headers)
    assert r.status_code == 403
