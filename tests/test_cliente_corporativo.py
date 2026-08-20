"""Loop cliente corporativo Ecolan B2B."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.domain.flujos_abonado import PLAYBOOKS, clasificar_intencion, destino_n2_canal
from main import app
from qa_bot.cliente_corporativo import PERSONAS, run_loop, run_persona

client = TestClient(app)


def test_destino_n2_b2b_es_ecolan():
    dest, prov = destino_n2_canal("ecolan_b2b")
    assert dest == "cooperativa"
    assert "Ecolan" in prov


def test_clasifica_b2b_cotizacion_y_vpn():
    assert clasificar_intencion("cotización de enlace dedicado Ecolan") == "ecolan_b2b"
    assert clasificar_intencion("VPN de la sucursal Ecolan no conecta") == "ecolan_b2b"
    assert clasificar_intencion("VM en el data center de Ecolan caída") == "ecolan_b2b"


def test_playbook_b2b_triaje_antes_de_derivar():
    ids = [p.id for p in PLAYBOOKS["ecolan_b2b"]]
    assert ids.index("alcance_b2b") < ids.index("derivar_ecolan")
    assert ids.index("impacto_sla") < ids.index("derivar_ecolan")


def test_loop_corp_sin_n2_evitable():
    results = run_loop(ids=["C01", "C02"], client=client)
    by_id = {r.persona_id: r for r in results}
    for pid in ("C01", "C02"):
        r = by_id[pid]
        assert r.ok, f"{pid} fallas={r.fallas} ticket={r.ticket_id} transcript={r.transcript}"
        assert not r.n2_evitable, pid


def test_loop_corp_n2_legitimo():
    for pid in ("C03", "C04"):
        p = next(x for x in PERSONAS if x.id == pid)
        r = run_persona(client, p)
        assert not r.n2_evitable, f"{pid} {r.fallas}"
        assert r.ticket_creado, f"{pid} debía handoff: {r.transcript}"
        assert r.n2_legitimo or r.ok
