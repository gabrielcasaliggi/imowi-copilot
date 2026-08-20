"""Loop cliente hogareño: playbooks, destino N2, KB canal, personas P01–P08."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.domain.flujos_abonado import (
    PLAYBOOKS,
    destino_n2_canal,
    refinar_intencion_internet,
    refinar_playbook_internet,
)
from app.services.knowledge_unified import buscar_unificado
from main import app
from qa_bot.cliente_hogareno import PERSONAS, run_loop, run_persona

client = TestClient(app)


def test_destino_n2_hogareño_no_es_noc_movil():
    dest, prov = destino_n2_canal("internet_ftth")
    assert dest == "cooperativa"
    assert prov == "Cooperativa / campo"
    assert destino_n2_canal("wifi")[0] == "cooperativa"
    assert destino_n2_canal("internet_lento")[0] == "cooperativa"
    assert destino_n2_canal("internet_radio")[0] == "cooperativa"
    assert destino_n2_canal("movil_datos") == ("imowi_noc", "NOC")
    assert destino_n2_canal("movil")[0] == "imowi_noc"


def test_refinar_playbook_internet_sale_del_triaje():
    assert refinar_intencion_internet("tengo fibra, cajita blanca") == "internet_ftth"
    assert refinar_playbook_internet("es solo el wifi") == "wifi"
    assert refinar_playbook_internet("anda re lento") == "internet_lento"
    assert refinar_playbook_internet("se corta a cada rato") == "internet_intermitente"
    assert refinar_playbook_internet("no me carga nada") is None


def test_playbook_internet_no_es_triaje_de_tres_pasos():
    assert len(PLAYBOOKS["internet"]) >= 4
    ids = [p.id for p in PLAYBOOKS["internet"]]
    assert "tipo_acceso" in ids
    assert "confirmar_acceso" in ids


def test_canal_kb_omite_rag_global(db):
    session, org_id = db
    fake = MagicMock()
    fake.encontrado = True
    fake.bloque = MagicMock(titulo="KB-9999 ruido", id="KB-9999", contenido="chat de agente")
    fake.modo = "escalamiento"
    fake.puntaje = 9.0
    with patch("app.services.knowledge_unified.buscar_contexto", return_value=fake) as m:
        out = buscar_unificado(
            session,
            org_id,
            "no tengo internet fibra los",
            incluir_rag_global=False,
        )
        m.assert_not_called()
    assert out["rag"]["encontrado"] is False
    assert all(a.get("fuente") != "global" for a in out["articulos"])


def test_ticket_n2_ftth_destino_cooperativa(db_session):
    from sqlalchemy import select

    from app.estate import canal_repo as crepo
    from app.estate.models import Abonado, Organization, Ticket
    from app.services.canal_abonado import _crear_ticket_n2

    db = db_session
    org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
    assert org
    abo = db.scalar(select(Abonado).where(Abonado.dni == "28555666"))
    assert abo is not None
    conv = crepo.get_or_create_conversacion(
        db,
        org.id,
        telefono="5492235555678",
        canal="whatsapp",
        wa_id="wa-ftth-n2-destino",
    )
    conv.abonado_id = abo.id
    conv.ticket_id = ""
    conv.estado = "bot"
    db.commit()
    tid = _crear_ticket_n2(
        db,
        org.id,
        conv,
        abo,
        "Falla óptica N1: los_confirmada",
        intencion="internet_ftth",
        paso_idx=2,
    )
    t = db.get(Ticket, tid)
    assert t is not None
    assert t.nivel == "N2"
    assert t.destino == "cooperativa"
    assert t.proveedor == "Cooperativa / campo"


def test_loop_personas_n1_sin_n2_evitable():
    ids = ["P01", "P03", "P04", "P06", "P07", "P08", "P09", "P10", "P11", "P12"]
    results = run_loop(ids=ids, client=client)
    by_id = {r.persona_id: r for r in results}
    for pid in ids:
        r = by_id[pid]
        assert r.ok, f"{pid} fallas={r.fallas} ticket={r.ticket_id} intent={r.intencion_final}"
        assert not r.n2_evitable, pid


def test_playbook_ecolan_b2b_tiene_alcance():
    ids = [p.id for p in PLAYBOOKS["ecolan_b2b"]]
    assert "alcance_b2b" in ids
    assert "prueba_minima_b2b" in ids
    assert len(PLAYBOOKS["ecolan_b2b"]) >= 5


def test_kb_b2b_seed_articulos():
    from app.estate.seed import _articulos_kb_batan

    titles = {a.titulo for a in _articulos_kb_batan("org-test")}
    assert "B2B — triaje de alcance (1 usuario / sede / todos)" in titles
    assert "B2B — enlace dedicado / IP fija" in titles
    assert "B2B — VPN sucursal" in titles
    assert "B2B — VM/DC caída con impacto" in titles
    assert "N1 hogareño — adulto mayor y WhatsApp (línea OK)" in titles


def test_loop_p02_optica_legitima():
    p02 = next(p for p in PERSONAS if p.id == "P02")
    r = run_persona(client, p02)
    assert not r.n2_evitable, r.fallas
    assert r.ticket_creado, r.transcript
    assert r.n2_legitimo or r.ok
