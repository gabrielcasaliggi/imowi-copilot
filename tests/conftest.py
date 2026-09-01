"""Fixtures compartidas. Fuerza SQLite de tests y arranca lifespan (seed)."""

from __future__ import annotations

import os
from pathlib import Path

# Antes de importar app.* — load_dotenv no pisa vars ya definidas.
_TEST_DB = Path(__file__).resolve().parent.parent / "data" / "test_estate.db"
_TEST_DB.parent.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DISABLE_DEMO_USERS", "false")
os.environ.pop("BILLTRACK_DATABASE_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.estate.database import Base  # noqa: E402
from app.estate.models import NetworkElement, Organization, Ticket  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_seeded_app():
    """Dispara lifespan de FastAPI → aplicar_schema + seed estate."""
    from main import app

    with TestClient(app):
        yield


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    org = Organization(id="org-test", nombre="Coop Test", slug="coop-test")
    session.add(org)
    session.commit()
    try:
        yield session, org.id
    finally:
        session.close()


def add_ticket(db, org_id: str, **kwargs) -> Ticket:
    t = Ticket(
        id=kwargs.get("id", "TK-TEST-001"),
        organizacion_id=org_id,
        linea=kwargs.get("linea", "2235402690"),
        dispositivo=kwargs.get("dispositivo", "Samsung A22"),
        descripcion_falla=kwargs.get("descripcion_falla", "Sin datos móviles"),
        origen=kwargs.get("origen", "chat"),
        estado=kwargs.get("estado", "Abierto"),
        categoria=kwargs.get("categoria", "General"),
        creado_por=kwargs.get("creado_por", "operador"),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture
def db_session():
    from app.estate.database import get_session_factory

    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def add_network_element(db, org_id: str, **kwargs) -> NetworkElement:
    el = NetworkElement(
        organizacion_id=org_id,
        elemento_red=kwargs.get("elemento_red", "Celda-Test"),
        metrica=kwargs.get("metrica", "perdida_paquetes"),
        valor_actual=kwargs.get("valor_actual", "ALERTA"),
        estado_actual=kwargs.get("estado_actual", "Anomalía Predictiva"),
    )
    if kwargs.get("ultima_actualizacion"):
        el.ultima_actualizacion = kwargs["ultima_actualizacion"]
    db.add(el)
    db.commit()
    db.refresh(el)
    return el
