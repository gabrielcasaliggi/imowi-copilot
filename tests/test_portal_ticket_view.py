"""Portal — eventos del ticket que ve el abonado (H-APP-2, privacidad).

Los eventos se generan con los escritores reales (create_ticket, update_ticket, notas, SLA),
que escriben textos pensados para agentes. La respuesta del portal no debe dejar pasar
ninguno de esos datos internos.

Sin variables de entorno propias: solo la base SQLite de tests que fija conftest.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.estate import repository as repo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.services.eko_ticket_proactive import (
    emit_customer_sla_breach_event,
    emit_ticket_customer_note,
)
from main import app
from tests.conftest import add_ticket

client = TestClient(app)

AGENTE = "agente.prueba@coop.test"
NOTA_AGENTE = "Mañana pasa un técnico por tu domicilio entre las 9 y las 13."
NOTA_ABONADO = "Sigo sin servicio, quedo atento."

# Textos internos que el sistema escribe para agentes y nunca deben llegar al abonado.
PROHIBIDOS = (
    "Proveedor",
    "proveedor=",
    "Regla",
    "Destino",
    "Origen:",
    "N2",
    "@",
    "nivel=",
    "asignado_a",
)
ISO_FECHA = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")

CLAVES_EVENTO = {"id", "titulo", "detalle", "estado", "created_at"}

def _ok_send(tokens, *, title, body, data=None):
    return {
        "ok": True,
        "sent": len(tokens),
        "error_category": "ok",
        "retryable": False,
        "provider_message_ids": ["m1"],
        "invalid_tokens": [],
        "invalid_token_fps": [],
    }


def _org_id(slug: str = "coop-batan") -> str:
    db = get_session_factory()()
    try:
        return db.query(Organization).filter(Organization.slug == slug).one().id
    finally:
        db.close()


def _sesion(slug: str = "coop-batan") -> dict:
    """Abonado de prueba + token de portal identificado, sin login OTP ni padrón externo.

    El login real consulta BillTrack con la configuración del entorno; acá el abonado se
    crea en la base de tests y el token se firma con el mismo emisor que usa el login.
    """
    from app.api.v1.portal import _crear_portal_token

    org_id = _org_id(slug)
    sufijo = uuid.uuid4().int % 10**7
    linea = f"223{sufijo:07d}"
    db = get_session_factory()()
    try:
        abo = Abonado(
            organizacion_id=org_id,
            dni=f"9{sufijo:07d}",
            nombre="Abonado Prueba",
            telefono_e164=linea,
            linea_msisdn=linea,
            servicio="internet",
            estado="activo",
        )
        db.add(abo)
        db.commit()
        db.refresh(abo)
        conv = ConversacionCanal(
            organizacion_id=org_id,
            canal="app",
            telefono=linea,
            abonado_id=abo.id,
            estado="bot",
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        token = _crear_portal_token(
            org_id=org_id,
            org_slug=slug,
            conversacion_id=conv.id,
            telefono=linea,
            abonado_id=abo.id,
            identified=True,
            canal="app",
        )
        return {"org_id": org_id, "abonado_id": abo.id, "linea": linea, "token": token}
    finally:
        db.close()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Canal": "app"}


def _vincular(db, org_id: str, abonado_id: str, ticket_id: str) -> None:
    """Conversación propia del abonado ligada al ticket (misma regla de pertenencia que prod)."""
    db.add(
        ConversacionCanal(
            organizacion_id=org_id,
            canal="app",
            telefono="",
            abonado_id=abonado_id,
            ticket_id=ticket_id,
            estado="bot",
        )
    )
    db.commit()


def _ticket_con_historia(sess: dict) -> str:
    """Ticket N2 escalado con todos los tipos de evento que existen hoy, en orden real."""
    org_id, abo_id = sess["org_id"], sess["abonado_id"]
    db = get_session_factory()()
    try:
        with patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send):
            t = repo.create_ticket(
                db,
                org_id,
                linea="2235999001",
                dispositivo="Canal abonado",
                descripcion_falla="[ORIGEN: Eko] Escalamiento N2 interno",
                origen="App",
                categoria="Movil Llamadas",
                creado_por="bot:2235999001",
                nivel="N2",
                destino="carrier",
                proveedor="Carrier de prueba",
                motivo_escalamiento="motivo interno",
                regla_clasificacion="canal_abonado_n2",
            )
            _vincular(db, org_id, abo_id, t.id)

            t.sla_breached_at = datetime.now(UTC)
            db.commit()
            emit_customer_sla_breach_event(db, t)

            emit_ticket_customer_note(
                db, org_id, t.id, NOTA_AGENTE, actor=AGENTE, agent_authorized=True
            )
            abo = db.get(Abonado, abo_id)
            emit_ticket_customer_note(
                db, org_id, t.id, NOTA_ABONADO, abonado=abo, actor=f"abonado:{abo_id}"
            )

            # Internos: nunca visibles, aunque alguno tenga el flag en "Sí" (históricos).
            repo.add_ticket_event(
                db, org_id, t.id, tipo="nota_interna", titulo="Nota interna",
                detalle="SECRETO-INTERNO-1", actor=AGENTE, visible_cliente="Sí",
            )
            repo.add_ticket_event(
                db, org_id, t.id, tipo="reasignacion", titulo="Ticket reasignado",
                detalle="SECRETO-INTERNO-2", actor=AGENTE, visible_cliente="Sí",
            )
            repo.add_ticket_event(
                db, org_id, t.id, tipo="actualizacion", titulo="Ticket actualizado",
                detalle="SECRETO-INTERNO-3", estado="Abierto", actor=AGENTE,
                visible_cliente="Sí",
            )
            repo.update_ticket(db, org_id, t.id, nivel="N3", actor=AGENTE)

            # Cierre con cambios internos en la misma edición: el detalle crudo los lista.
            repo.update_ticket(
                db,
                org_id,
                t.id,
                estado="Cerrado",
                nivel="N2",
                destino="carrier",
                proveedor="Carrier de prueba",
                ticket_externo_id="EXT-123",
                asignado_a=AGENTE,
                actor=AGENTE,
            )
        return t.id
    finally:
        db.close()


def _eventos(token: str, tid: str) -> list[dict]:
    r = client.get(f"/api/v1/portal/tickets/{tid}", headers=_headers(token))
    assert r.status_code == 200, r.text
    return r.json()["eventos"]


def _texto(ev: dict) -> str:
    return f"{ev['titulo']}\n{ev['detalle']}"


# --- Privacidad del texto ---


def test_eventos_sin_datos_internos():
    sess = _sesion()
    eventos = _eventos(sess["token"], _ticket_con_historia(sess))
    assert eventos
    for ev in eventos:
        texto = _texto(ev)
        for prohibido in PROHIBIDOS:
            assert prohibido not in texto, (prohibido, ev)
        assert not ISO_FECHA.search(texto), ev


def test_eventos_con_textos_fijos_en_orden():
    sess = _sesion()
    eventos = _eventos(sess["token"], _ticket_con_historia(sess))
    assert [(e["titulo"], e["detalle"]) for e in eventos] == [
        ("Recibimos tu reclamo", ""),
        ("Tu reclamo está demorando más de lo previsto", ""),
        ("Novedad del equipo", NOTA_AGENTE),
        ("Tu comentario", NOTA_ABONADO),
        ("Tu reclamo se cerró", ""),
    ]


def test_post_reclamo_devuelve_evento_de_creacion_fijo():
    sess = _sesion()
    with (
        patch("app.services.app_push.enviar_push_expo", side_effect=_ok_send),
        patch("app.services.ticket_bridge.es_mirror_supabase_activo", return_value=False),
    ):
        r = client.post(
            "/api/v1/portal/tickets",
            headers=_headers(sess["token"]),
            json={"motivo": "Internet sin servicio", "descripcion": "Sin conexión desde ayer."},
        )
    assert r.status_code == 201, r.text
    eventos = r.json()["eventos"]
    assert [(e["titulo"], e["detalle"]) for e in eventos] == [("Recibimos tu reclamo", "")]


# --- Claves, internos y notas ---


def test_eventos_mantienen_las_claves_actuales():
    sess = _sesion()
    eventos = _eventos(sess["token"], _ticket_con_historia(sess))
    assert eventos
    for ev in eventos:
        assert set(ev) == CLAVES_EVENTO
        assert isinstance(ev["detalle"], str)


def test_notas_internas_y_reasignaciones_no_aparecen():
    sess = _sesion()
    eventos = _eventos(sess["token"], _ticket_con_historia(sess))
    texto = "\n".join(_texto(e) for e in eventos)
    assert "SECRETO-INTERNO" not in texto
    assert "reasignado" not in texto.lower()
    assert "Nota interna" not in texto


def test_texto_de_las_notas_aparece():
    sess = _sesion()
    eventos = _eventos(sess["token"], _ticket_con_historia(sess))
    detalles = [e["detalle"] for e in eventos]
    assert NOTA_AGENTE in detalles
    assert NOTA_ABONADO in detalles


# --- Pertenencia: siempre el mismo 404 ---


def _ticket_ajeno() -> str:
    otro = _sesion()
    db = get_session_factory()()
    try:
        tid = f"TK-AJ-{uuid.uuid4().hex[:10]}"
        add_ticket(db, otro["org_id"], id=tid, linea=otro["linea"], categoria="Privado")
        _vincular(db, otro["org_id"], otro["abonado_id"], tid)
        return tid
    finally:
        db.close()


def _ticket_otra_org(sess: dict) -> str:
    """Ticket de otra organización con la misma línea que el abonado de la sesión."""
    db = get_session_factory()()
    try:
        tid = f"TK-OO-{uuid.uuid4().hex[:10]}"
        add_ticket(db, _org_id("coop-viamonte"), id=tid, linea=sess["linea"], categoria="Privado")
        return tid
    finally:
        db.close()


def test_pertenencia_404_identico():
    sess = _sesion()
    headers = _headers(sess["token"])
    ids = [
        _ticket_ajeno(),
        _ticket_otra_org(sess),
        "TK-NO-EXISTE-0000",
        "TK' OR '1'='1",
        "TK-1;DROP TABLE tickets_estate",
        "...",
        "TK-..-1",
        "%00",
        "ñ💥",
        "X" * 500,
    ]
    respuestas = []
    for tid in ids:
        r = client.get(f"/api/v1/portal/tickets/{tid}", headers=headers)
        respuestas.append((tid, r.status_code, r.json()))
    esperado = (404, {"detail": "Ticket no encontrado"})
    for tid, status, body in respuestas:
        assert (status, body) == esperado, (tid, status, body)


def test_lista_no_incluye_ajenos_ni_otra_org():
    sess = _sesion()
    ajeno = _ticket_ajeno()
    otra = _ticket_otra_org(sess)
    r = client.get("/api/v1/portal/tickets", headers=_headers(sess["token"]))
    assert r.status_code == 200, r.text
    ids = {i["id"] for i in r.json()["items"]}
    assert ajeno not in ids
    assert otra not in ids


# --- Proyección pura (sin base) ---


def _ev(tipo: str, *, detalle: str = "", estado: str = "Abierto", actor: str = "sistema",
        visible: str = "Sí"):
    return SimpleNamespace(
        id="ev-1",
        tipo=tipo,
        titulo="Título interno N2",
        detalle=detalle,
        estado=estado,
        actor=actor,
        visible_cliente=visible,
        created_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )


def test_vista_textos_fijos_por_tipo():
    from app.api.v1.portal_ticket_view import evento_cliente

    interno = "Origen: App | Destino: carrier | Proveedor sugerido: X | Regla: r"
    casos = [
        (_ev("creacion", detalle=interno), ("Recibimos tu reclamo", "")),
        (_ev("actualizacion", detalle="estado=Cerrado; asignado_a=a@b", estado="Cerrado"),
         ("Tu reclamo se cerró", "")),
        (_ev("sla_breach", detalle="sla_breached_at=2026-10-01T12:00:00"),
         ("Tu reclamo está demorando más de lo previsto", "")),
        (_ev("nota", detalle="  Hola  ", actor="ops@coop"), ("Novedad del equipo", "Hola")),
        (_ev("nota", detalle="Gracias", actor="abonado:abc"), ("Tu comentario", "Gracias")),
    ]
    for ev, esperado in casos:
        out = evento_cliente(ev)
        assert out is not None, ev.tipo
        assert (out["titulo"], out["detalle"]) == esperado
        assert set(out) == CLAVES_EVENTO
        assert out["created_at"] == "2026-10-01T12:00:00+00:00"


def test_vista_descarta_lo_que_no_esta_en_la_lista_blanca():
    from app.api.v1.portal_ticket_view import evento_cliente, eventos_cliente

    descartados = [
        _ev("creacion", visible="No"),
        _ev("actualizacion", estado="Abierto"),
        _ev("nota_interna", detalle="x"),
        _ev("reasignacion", detalle="x"),
        _ev("paso_operativo", detalle="x"),
        _ev("tipo_nuevo_sin_mapear", detalle="x"),
        _ev("", detalle="x"),
        _ev("nota", detalle="   "),
    ]
    for ev in descartados:
        assert evento_cliente(ev) is None, ev.tipo
    assert eventos_cliente(descartados) == []


def test_vista_nota_recortada_a_800():
    from app.api.v1.portal_ticket_view import evento_cliente

    out = evento_cliente(_ev("nota", detalle="a" * 2000, actor="ops@coop"))
    assert out is not None
    assert len(out["detalle"]) == 800
