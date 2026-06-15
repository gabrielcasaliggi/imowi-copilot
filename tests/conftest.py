"""Fixtures compartidas para tests con SQLite en memoria."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.estate.database import Base
from app.estate.models import NetworkElement, Organization, Ticket


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
