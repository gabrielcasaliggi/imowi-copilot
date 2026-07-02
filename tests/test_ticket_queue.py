"""Tests de filtrado de cola operativa."""

from app.estate.models import Ticket
from app.services.ticket_queue import filtrar_tickets


def _ticket(**kwargs) -> Ticket:
    t = Ticket(
        id=kwargs.get("id", "T-1"),
        organizacion_id="org-1",
        linea=kwargs.get("linea", "2235551234"),
        descripcion_falla=kwargs.get("descripcion_falla", "Sin señal"),
        estado=kwargs.get("estado", "Abierto"),
        nivel=kwargs.get("nivel", "N1"),
        categoria=kwargs.get("categoria", "Señal"),
        creado_por="op@test",
        proveedor=kwargs.get("proveedor", ""),
        destino="cooperativa",
    )
    return t


def test_filtrar_por_estado_y_q():
    tickets = [
        _ticket(id="A", estado="Abierto", linea="223111"),
        _ticket(id="B", estado="Cerrado", linea="223222"),
    ]
    out = filtrar_tickets(tickets, estado="Abierto", q="223111")
    assert len(out) == 1
    assert out[0].id == "A"


def test_solo_abiertos():
    tickets = [
        _ticket(id="A", estado="Abierto"),
        _ticket(id="B", estado="Cerrado"),
    ]
    out = filtrar_tickets(tickets, solo_abiertos=True)
    assert len(out) == 1
    assert out[0].id == "A"
