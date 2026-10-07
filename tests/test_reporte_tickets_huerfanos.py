"""scripts/reporte_tickets_huerfanos.py: lista los tickets abiertos de Eko sin conversación ligada, sin datos personales y sin escribir."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, select

from app.estate.models import ConversacionCanal, Ticket

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "reporte_tickets_huerfanos.py"
_spec = importlib.util.spec_from_file_location("reporte_tickets_huerfanos", _SCRIPT)
rep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rep)

AHORA = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def _ticket(db, org_id, tid, *, origen="Portal", estado="Abierto", linea="2235551234", horas=5):
    t = Ticket(id=tid, organizacion_id=org_id, linea=linea, descripcion_falla="Sin internet", origen=origen, estado=estado,
               nivel="N2", destino="cooperativa", created_at=AHORA - timedelta(hours=horas))
    db.add(t)
    db.commit()
    return t


def _conv(db, org_id, *, ticket_id="", estado="espera_agente", tel="5492235559876"):
    c = ConversacionCanal(organizacion_id=org_id, canal="web", telefono=tel, estado=estado, ticket_id=ticket_id, wa_id=tel)
    db.add(c)
    db.commit()
    return c


def test_lista_solo_los_abiertos_de_eko_sin_conversacion(db):
    s, org = db
    _ticket(s, org, "IBOT-1", origen="Portal")                                   # huérfano
    _ticket(s, org, "IBOT-2", origen="App", horas=30)                            # huérfano
    _ticket(s, org, "IBOT-3", origen="WhatsApp")                                 # ligado
    _conv(s, org, ticket_id="IBOT-3")
    _ticket(s, org, "IBOT-4", origen="Portal", estado="Cerrado")                 # cerrado
    _ticket(s, org, "IBOT-5", origen="agente")                                   # no lo creó Eko
    r = rep.generar_reporte(s, ahora=AHORA)
    ids = [t["id"] for t in r["tickets_sin_conversacion"]]
    assert ids == ["IBOT-2", "IBOT-1"]  # más viejo primero
    t2 = r["tickets_sin_conversacion"][0]
    assert (t2["nivel"], t2["destino"], t2["estado"], t2["origen"], t2["antiguedad"]) == ("N2", "cooperativa", "Abierto", "App", "1d 6h 0m")
    assert t2["creado"].startswith("2026-10-06T06:00")


def test_sin_datos_personales(db):
    s, org = db
    _ticket(s, org, "IBOT-1", linea="2235551234")
    _conv(s, org, tel="5492235559876")
    r = rep.generar_reporte(s, ahora=AHORA)
    texto = rep.formatear(r)
    assert r["tickets_sin_conversacion"][0]["linea"] == "***234"
    assert r["conversaciones_activas_sin_ticket"][0]["telefono"] == "***876"
    assert "2235551234" not in texto and "5492235559876" not in texto


def test_conversaciones_activas_sin_ticket_es_informativo(db):
    s, org = db
    _conv(s, org, estado="espera_agente")
    _conv(s, org, estado="bot")
    _conv(s, org, estado="con_agente", ticket_id="IBOT-9")
    r = rep.generar_reporte(s, ahora=AHORA)
    assert [c["estado"] for c in r["conversaciones_activas_sin_ticket"]] == ["espera_agente"]


def test_filtra_por_organizacion_y_rechaza_una_desconocida(db):
    s, org = db
    _ticket(s, org, "IBOT-1")
    assert len(rep.generar_reporte(s, org_slug="coop-test", ahora=AHORA)["tickets_sin_conversacion"]) == 1
    with pytest.raises(SystemExit):
        rep.generar_reporte(s, org_slug="no-existe")


def test_solo_lectura_no_escribe_y_el_modo_query_only_lo_impide(db):
    s, org = db
    _ticket(s, org, "IBOT-1")
    antes = s.scalars(select(Ticket.id, Ticket.estado)).all()
    sentencias: list[str] = []
    event.listen(s.get_bind(), "before_cursor_execute", lambda _c, _cur, stmt, *_a: sentencias.append(stmt.strip().split()[0].upper()))
    rep.preparar_solo_lectura(s, 5)
    rep.generar_reporte(s, ahora=AHORA)
    s.rollback()
    assert set(sentencias) <= {"SELECT", "PRAGMA"}, sentencias
    assert s.scalars(select(Ticket.id, Ticket.estado)).all() == antes
    with pytest.raises(Exception, match="readonly|read-only"):
        s.execute(Ticket.__table__.update().values(estado="Cerrado"))
    s.rollback()


def test_el_script_no_contiene_escrituras():
    src = _SCRIPT.read_text().upper()
    for prohibido in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", ".COMMIT(", "DB.ADD("):
        assert prohibido not in src.replace("SET LOCAL", ""), prohibido
