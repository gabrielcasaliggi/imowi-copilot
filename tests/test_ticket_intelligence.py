"""Tests del motor de inteligencia operativa por ticket."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.estate.models import Ticket
from app.estate.ticket_intelligence import (
    calcular_prioridad,
    inferir_causa_probable,
    ordenar_por_riesgo,
    proxima_mejor_accion,
)


def _ticket(**kwargs) -> Ticket:
    defaults = {
        "id": "JSC-1001",
        "organizacion_id": "org-1",
        "linea": "2235551234",
        "estado": "Abierto",
        "categoria": "Roaming",
        "descripcion_falla": "Sin roaming en Brasil",
        "nivel": "N1",
        "created_at": datetime.now(UTC) - timedelta(hours=6),
    }
    defaults.update(kwargs)
    return Ticket(**defaults)


def test_prioridad_n2_sla_y_antiguedad():
    t = _ticket(nivel="N2", estado_sla="Vencido", proveedor="Movistar")
    intel = calcular_prioridad(t, pool=[t])
    assert intel["priority_score"] >= 55
    assert intel["risk_level"] in ("alto", "critico")
    assert any("N2" in r for r in intel["risk_reasons"])


def test_causa_probable_roaming():
    t = _ticket(descripcion_falla="No registra en red en Brasil")
    assert "Roaming" in inferir_causa_probable(t)


def test_proxima_accion_n2():
    t = _ticket(nivel="N2")
    assert "NOC" in proxima_mejor_accion(t)


def test_ordenar_por_riesgo():
    bajo = _ticket(id="JSC-1", nivel="N1", created_at=datetime.now(UTC))
    alto = _ticket(id="JSC-2", nivel="N2", estado_sla="Crítico", proveedor="Core")
    ordered = ordenar_por_riesgo([bajo, alto], pool=[bajo, alto])
    assert ordered[0][0].id == "JSC-2"
    assert ordered[0][1]["priority_score"] > ordered[1][1]["priority_score"]


def test_ticket_cerrado_score_cero():
    t = _ticket(estado="Cerrado")
    intel = calcular_prioridad(t)
    assert intel["priority_score"] == 0
    assert intel["risk_level"] == "cerrado"
