"""Tests analytics ejecutivo."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.estate.database import Base
from app.estate.executive_analytics import executive_analytics
from app.estate.models import Organization, Ticket


def test_executive_analytics_resumen():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    org = Organization(id="org-b", nombre="Coop Test", slug="coop-test")
    db.add(org)
    db.flush()
    db.add(
        Ticket(
            id="JSC-2001",
            organizacion_id=org.id,
            linea="2235559999",
            estado="Abierto",
            categoria="Roaming",
            nivel="N2",
            created_at=datetime.now(UTC) - timedelta(hours=10),
        )
    )
    db.commit()

    data = executive_analytics(db, admin_global=True)
    assert "resumen_ejecutivo" in data
    assert len(data["resumen_ejecutivo"]) > 20
    assert data["ranking_riesgo"]
    assert data["ahorro_operativo"]["casos_n1_resueltos"] >= 0
    db.close()
