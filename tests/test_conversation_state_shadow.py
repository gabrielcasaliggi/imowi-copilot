"""Fase 6: ConversationState v1 en sombra. No valida política conversacional nueva."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select

from app.domain.conversation_state import (
    CS_VERSION,
    ConversationState,
    DomainSlot,
    Fact,
    LastBotAct,
    PendingBot,
    PendingUser,
    hydrate_conversation_state,
    increment_user_turn,
    map_playbook_to_kind,
    project_legacy,
    push_domain_stack,
    upsert_fact,
    write_shadow_into_ctx,
)
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.services.canal_abonado import procesar_mensaje_entrante

_DNI = "30111222"
_CANAL = "whatsapp"


# ---------------------------------------------------------------------------
# A. Empty state
# ---------------------------------------------------------------------------


def test_hydrate_empty_ctx_creates_v1_and_one_domain():
    cs = hydrate_conversation_state({})
    assert cs.v == CS_VERSION == 1
    assert cs.turn == 0
    assert len(cs.domains) == 1
    slot = cs.domains[0]
    assert slot.status == "active"
    assert slot.kind in ("tecnico", "administrativo", "comercial")
    assert cs.active_domain_id == slot.id


def test_hydrate_uses_valid_cs_without_inventing_history():
    raw = {
        "cs": {
            "v": 1,
            "turn": 4,
            "active_domain_id": "tec-1",
            "domain_stack": ["tec-1"],
            "domains": [
                {
                    "id": "tec-1",
                    "kind": "tecnico",
                    "playbook": "wifi",
                    "status": "active",
                    "covered_steps": ["zona_wifi"],
                    "cursor": 1,
                    "opened_turn": 1,
                }
            ],
            "facts": [],
            "pending": {"bot": None, "user": None},
            "last_bot_act": None,
        }
    }
    cs = hydrate_conversation_state(raw)
    assert cs.turn == 4
    assert cs.domains[0].playbook == "wifi"
    assert cs.domains[0].covered_steps == ["zona_wifi"]
    assert cs.facts == []


def test_hydrate_invalid_cs_degrades_to_legacy(caplog):
    ctx = {
        "intencion": "wifi",
        "paso_idx": 2,
        "pasos_cubiertos": ["zona_wifi"],
        "cs": {"v": 1, "domains": "no-lista"},
    }
    with caplog.at_level(logging.WARNING, logger="operations_hub"):
        cs = hydrate_conversation_state(ctx)
    assert cs.v == 1
    assert cs.domains[0].playbook == "wifi"
    assert cs.domains[0].covered_steps == ["zona_wifi"]
    assert cs.domains[0].cursor == 2
    assert any("cs" in r.message.lower() or "shadow" in r.message.lower() for r in caplog.records)


def test_hydrate_unknown_version_degrades_to_legacy(caplog):
    ctx = {
        "intencion": "internet_ftth",
        "cs": {"v": 99, "turn": 1, "domains": []},
    }
    with caplog.at_level(logging.WARNING, logger="operations_hub"):
        cs = hydrate_conversation_state(ctx)
    assert cs.v == 1
    assert cs.domains[0].playbook == "internet_ftth"
    assert any("v=99" in r.message or "99" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# B. Round-trip
# ---------------------------------------------------------------------------


def test_round_trip_serialize_hydrate_equivalent():
    state = ConversationState(
        v=1,
        turn=3,
        active_domain_id="adm-1",
        domain_stack=["adm-1", "tec-1"],
        domains=[
            DomainSlot(
                id="tec-1",
                kind="tecnico",
                playbook="internet_ftth",
                status="paused",
                covered_steps=["energia_ont"],
                cursor=1,
                opened_turn=1,
            ),
            DomainSlot(
                id="adm-1",
                kind="administrativo",
                playbook="facturacion_reclamo",
                status="active",
                covered_steps=[],
                cursor=0,
                opened_turn=3,
            ),
        ],
        facts=[
            Fact(
                key="tecnologia_acceso",
                value="internet_ftth",
                domain_id="tec-1",
                source_turn=1,
                status="active",
            )
        ],
        pending_bot=PendingBot(
            act="ASK_FACT",
            step_id="triaje_motivo",
            referent="mes_monto",
            domain_id="adm-1",
            turn=3,
        ),
        pending_user=PendingUser(
            act="ASK_CAUSE",
            text="por qué subió",
            referent="factura",
            domain_id="adm-1",
            turn=3,
            status="open",
        ),
        last_bot_act=LastBotAct(
            act="PROVIDE_INFORMATION",
            referent="saldo_cuenta",
            domain_id="adm-1",
            turn=3,
        ),
    )
    payload = json.loads(json.dumps(state.to_dict(), ensure_ascii=False))
    restored = hydrate_conversation_state({"cs": payload})
    assert restored.to_dict() == state.to_dict()


# ---------------------------------------------------------------------------
# C. Legacy hydration
# ---------------------------------------------------------------------------


def _assert_legacy_slot(ctx: dict, playbook: str, kind: str):
    cs = hydrate_conversation_state(ctx)
    assert cs.v == 1
    assert len(cs.domains) >= 1
    active = next(d for d in cs.domains if d.id == cs.active_domain_id)
    assert active.playbook == playbook
    assert active.kind == kind
    assert active.status == "active"
    assert active.covered_steps == list(ctx.get("pasos_cubiertos") or [])
    assert active.cursor == int(ctx.get("paso_idx") or 0)
    hechos = ctx.get("hechos") if isinstance(ctx.get("hechos"), dict) else {}
    active_facts = {
        f.key: f.value for f in cs.facts if f.status == "active" and f.domain_id == active.id
    }
    assert active_facts == dict(hechos)
    assert all(f.status == "active" for f in cs.facts)


def test_hydrate_legacy_internet_ftth():
    _assert_legacy_slot(
        {
            "intencion": "internet_ftth",
            "paso_idx": 2,
            "pasos_cubiertos": ["energia_ont", "luces_los"],
            "hechos": {"tecnologia_acceso": "internet_ftth"},
        },
        "internet_ftth",
        "tecnico",
    )


def test_hydrate_legacy_wifi():
    _assert_legacy_slot(
        {
            "intencion": "wifi",
            "paso_idx": 6,
            "pasos_cubiertos": ["zona_wifi", "conexion_cableada"],
            "hechos": {"alcance_wifi": "uno", "dispositivo_afectado": "tablet"},
        },
        "wifi",
        "tecnico",
    )


def test_hydrate_legacy_facturacion_reclamo():
    _assert_legacy_slot(
        {
            "intencion": "facturacion_reclamo",
            "paso_idx": 0,
            "pasos_cubiertos": [],
            "hechos": {},
        },
        "facturacion_reclamo",
        "administrativo",
    )


def test_hydrate_legacy_alta_plan():
    _assert_legacy_slot(
        {
            "intencion": "alta_plan",
            "paso_idx": 2,
            "pasos_cubiertos": ["derivar_comercial"],
            "hechos": {},
        },
        "alta_plan",
        "comercial",
    )


def test_hydrate_intencion_tecnica_pendiente_paused_slot():
    cs = hydrate_conversation_state(
        {
            "intencion": "aviso_deuda",
            "intencion_tecnica_pendiente": "internet_ftth",
            "paso_idx": 0,
            "pasos_cubiertos": [],
        }
    )
    kinds = {d.kind: d for d in cs.domains}
    assert "administrativo" in kinds
    assert "tecnico" in kinds
    assert kinds["administrativo"].status == "active"
    assert kinds["administrativo"].playbook == "aviso_deuda"
    assert kinds["tecnico"].status == "paused"
    assert kinds["tecnico"].playbook == "internet_ftth"
    assert cs.active_domain_id == kinds["administrativo"].id


# ---------------------------------------------------------------------------
# D. Facts
# ---------------------------------------------------------------------------


def test_upsert_fact_statuses_and_history_cap():
    cs = hydrate_conversation_state({"intencion": "wifi"})
    did = cs.active_domain_id
    upsert_fact(cs, Fact(key="alcance_wifi", value="uno", domain_id=did, source_turn=1, status="active"))
    upsert_fact(
        cs,
        Fact(key="alcance_wifi", value="todos", domain_id=did, source_turn=2, status="active"),
        as_correction=True,
    )
    upsert_fact(
        cs,
        Fact(key="alcance_wifi", value="ninguno", domain_id=did, source_turn=3, status="active"),
        as_correction=True,
    )
    upsert_fact(
        cs,
        Fact(
            key="alcance_wifi",
            value="parcial",
            domain_id=did,
            source_turn=4,
            status="uncertain",
        ),
    )
    rows = [f for f in cs.facts if f.key == "alcance_wifi" and f.domain_id == did]
    assert len(rows) <= 3
    actives = [f for f in rows if f.status == "active"]
    assert len(actives) == 1
    assert actives[0].value == "ninguno"
    assert any(f.status == "superseded" for f in rows)
    assert any(f.status == "uncertain" for f in rows)


def test_one_active_fact_per_domain_key():
    cs = hydrate_conversation_state({"intencion": "wifi"})
    did = cs.active_domain_id
    upsert_fact(cs, Fact(key="zona_wifi", value="baño", domain_id=did, source_turn=1, status="active"))
    upsert_fact(cs, Fact(key="zona_wifi", value="living", domain_id=did, source_turn=2, status="active"))
    actives = [
        f
        for f in cs.facts
        if f.key == "zona_wifi" and f.domain_id == did and f.status == "active"
    ]
    assert len(actives) == 1
    assert actives[0].value == "living"


# ---------------------------------------------------------------------------
# E. Domain slots
# ---------------------------------------------------------------------------


def test_map_playbook_to_kind():
    assert map_playbook_to_kind("internet_ftth") == "tecnico"
    assert map_playbook_to_kind("wifi") == "tecnico"
    assert map_playbook_to_kind("facturacion_reclamo") == "administrativo"
    assert map_playbook_to_kind("aviso_deuda") == "administrativo"
    assert map_playbook_to_kind("alta_plan") == "comercial"
    assert map_playbook_to_kind("baja_servicio") == "comercial"


def test_one_slot_per_kind_max_three():
    ctx = {"intencion": "wifi"}
    cs = hydrate_conversation_state(ctx)
    write_shadow_into_ctx(ctx)
    ctx["intencion"] = "facturacion_reclamo"
    ctx["pasos_cubiertos"] = []
    ctx["paso_idx"] = 0
    write_shadow_into_ctx(ctx)
    ctx["intencion"] = "alta_plan"
    write_shadow_into_ctx(ctx)
    cs = hydrate_conversation_state(ctx)
    assert len(cs.domains) <= 3
    kinds = [d.kind for d in cs.domains]
    assert len(kinds) == len(set(kinds))
    assert set(kinds) <= {"tecnico", "administrativo", "comercial"}
    actives = [d for d in cs.domains if d.status == "active"]
    assert len(actives) == 1
    assert actives[0].kind == "comercial"


# ---------------------------------------------------------------------------
# F. Stack
# ---------------------------------------------------------------------------


def test_domain_stack_push_no_dupes_max_three():
    cs = hydrate_conversation_state({"intencion": "wifi"})
    tec = cs.active_domain_id
    push_domain_stack(cs, tec)
    push_domain_stack(cs, tec)
    assert cs.domain_stack.count(tec) == 1
    # slots de otros kinds
    cs.domains.append(
        DomainSlot(id="adm-1", kind="administrativo", playbook="facturacion", status="paused")
    )
    cs.domains.append(
        DomainSlot(id="com-1", kind="comercial", playbook="alta_plan", status="paused")
    )
    push_domain_stack(cs, "adm-1")
    push_domain_stack(cs, "com-1")
    push_domain_stack(cs, "ghost-1")  # no existe: ignorar
    assert "ghost-1" not in cs.domain_stack
    assert len(cs.domain_stack) <= 3
    assert all(any(d.id == i for d in cs.domains) for i in cs.domain_stack)


# ---------------------------------------------------------------------------
# G. Projection
# ---------------------------------------------------------------------------


def test_project_legacy_from_hydrated_state():
    ctx = {
        "intencion": "internet_ftth",
        "paso_idx": 2,
        "pasos_cubiertos": ["energia_ont", "luces_los"],
        "hechos": {"tecnologia_acceso": "internet_ftth"},
        "intencion_tecnica_pendiente": "",
    }
    cs = hydrate_conversation_state(ctx)
    proj = project_legacy(cs)
    assert proj["intencion"] == "internet_ftth"
    assert proj["hechos"] == {"tecnologia_acceso": "internet_ftth"}
    assert proj["pasos_cubiertos"] == ["energia_ont", "luces_los"]
    assert proj["paso_idx"] == 2
    assert not proj["intencion_tecnica_pendiente"]


def test_project_legacy_paused_tech_as_pendiente():
    cs = hydrate_conversation_state(
        {
            "intencion": "aviso_deuda",
            "intencion_tecnica_pendiente": "wifi",
        }
    )
    proj = project_legacy(cs)
    assert proj["intencion"] == "aviso_deuda"
    assert proj["intencion_tecnica_pendiente"] == "wifi"


# ---------------------------------------------------------------------------
# Dual-write / increment
# ---------------------------------------------------------------------------


def test_write_shadow_into_ctx_and_increment_turn_once():
    ctx = {"intencion": "wifi", "paso_idx": 0, "pasos_cubiertos": []}
    write_shadow_into_ctx(ctx)
    assert ctx["cs"]["v"] == 1
    t0 = ctx["cs"]["turn"]
    increment_user_turn(ctx)
    increment_user_turn(ctx)
    # dos incrementos deliberados: la API suma 1 cada llamada; el motor llama una vez
    assert ctx["cs"]["turn"] == t0 + 2
    write_shadow_into_ctx(ctx)
    assert ctx["cs"]["turn"] == t0 + 2


def test_write_shadow_does_not_overwrite_legacy_fields():
    ctx = {
        "intencion": "wifi",
        "paso_idx": 6,
        "pasos_cubiertos": ["zona_wifi"],
        "hechos": {"alcance_wifi": "uno"},
        "identificado": True,
        "dni": "30111222",
    }
    write_shadow_into_ctx(ctx)
    assert ctx["intencion"] == "wifi"
    assert ctx["paso_idx"] == 6
    assert ctx["pasos_cubiertos"] == ["zona_wifi"]
    assert ctx["hechos"] == {"alcance_wifi": "uno"}
    assert ctx["identificado"] is True
    assert ctx["dni"] == "30111222"


# ---------------------------------------------------------------------------
# H. Persistencia real (contexto_json)
# ---------------------------------------------------------------------------


def _org_abo():
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        abo = db.scalar(select(Abonado).where(Abonado.dni == _DNI))
        assert org and abo
        return org.id, abo.id


def test_persistencia_contexto_json_write_read_hydrate():
    org_id, abo_id = _org_abo()
    tel = "5492235610601"
    Session = get_session_factory()
    with Session() as db:
        for c in db.scalars(
            select(ConversacionCanal).where(ConversacionCanal.telefono.contains(tel[-10:]))
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
        db.commit()
        conv = crepo.get_or_create_conversacion(
            db, org_id, telefono=tel, canal=_CANAL, wa_id=tel
        )
        conv.estado = "bot"
        conv.abonado_id = abo_id
        crepo.set_contexto(
            conv,
            {
                "saludo": True,
                "identificado": True,
                "dni": _DNI,
                "intencion": "wifi",
                "paso_idx": 1,
                "pasos_cubiertos": ["zona_wifi"],
                "hechos": {"zona_wifi": "baño"},
            },
        )
        db.commit()
        cid = conv.id

    with Session() as db:
        conv = db.get(ConversacionCanal, cid)
        assert conv is not None
        ctx = crepo.get_contexto(conv)
        assert "cs" in ctx
        cs = hydrate_conversation_state(ctx)
        assert cs.v == 1
        assert cs.domains[0].playbook == "wifi"
        assert cs.domains[0].covered_steps == ["zona_wifi"]
        raw = json.loads(conv.contexto_json)
        assert raw["intencion"] == "wifi"
        assert raw["paso_idx"] == 1


# ---------------------------------------------------------------------------
# Replay Fase 4: misma respuesta, cs persistido
# ---------------------------------------------------------------------------


def _abrir(tel: str, *, extra: dict | None = None) -> str:
    org_id, abo_id = _org_abo()
    Session = get_session_factory()
    with Session() as db:
        for c in db.scalars(
            select(ConversacionCanal).where(ConversacionCanal.telefono.contains(tel[-10:]))
        ).all():
            c.estado = "cerrado"
            c.contexto_json = "{}"
            c.ticket_id = ""
            c.agente_id = ""
            c.abonado_id = ""
        db.commit()
        conv = crepo.get_or_create_conversacion(
            db, org_id, telefono=tel, canal=_CANAL, wa_id=tel
        )
        conv.estado = "bot"
        conv.abonado_id = abo_id
        conv.ticket_id = ""
        base = {"saludo": True, "identificado": True, "dni": _DNI}
        if extra:
            base.update(extra)
        crepo.set_contexto(conv, base)
        db.commit()
        return org_id, conv.id


def _msg(org_id: str, tel: str, texto: str) -> dict:
    Session = get_session_factory()
    with Session() as db:
        return procesar_mensaje_entrante(
            db, org_id, telefono=tel, texto=texto, canal=_CANAL, usar_llama=False
        )


def _load_ctx(conv_id: str) -> dict:
    Session = get_session_factory()
    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        assert conv is not None
        return crepo.get_contexto(conv)


def _replay(tel: str, mensajes: list[str]) -> tuple[list[str], dict]:
    org_id, conv_id = _abrir(tel)
    bots = []
    for texto in mensajes:
        out = _msg(org_id, tel, texto)
        bots.append(str(out.get("respuesta") or out.get("reply") or ""))
    ctx = _load_ctx(conv_id)
    return bots, ctx


def _assert_shadow_ok(ctx: dict) -> None:
    assert "cs" in ctx
    cs = hydrate_conversation_state(ctx)
    assert cs.v == 1
    assert len(cs.domains) <= 3
    kinds = [d.kind for d in cs.domains]
    assert len(kinds) == len(set(kinds))
    blob = json.dumps(ctx["cs"], ensure_ascii=False)
    assert len(blob) < 8000
    proj = project_legacy(cs)
    # Dual-write: proyección del activo coincide con legacy funcional
    if ctx.get("intencion"):
        assert proj["intencion"] == ctx.get("intencion")
    assert proj["pasos_cubiertos"] == list(ctx.get("pasos_cubiertos") or [])
    assert proj["paso_idx"] == int(ctx.get("paso_idx") or 0)
    hechos = ctx.get("hechos") if isinstance(ctx.get("hechos"), dict) else {}
    assert proj["hechos"] == dict(hechos)


def test_replay_ftth_01_shadow_no_cambia_respuesta():
    bots, ctx = _replay(
        "5492235610701",
        [
            "Internet anda mal",
            "es fibra",
            "la PON está verde",
            "la LOS está apagada",
            "reinicié",
            "sigue igual",
        ],
    )
    cs = hydrate_conversation_state(ctx)
    last = (bots[-1] or "").lower()
    # Fase 7: el referente de "sigue igual" es el reinicio, no luces/energía.
    assert "cajita blanca" not in last
    assert "luz pon" not in last
    slot = cs.active_slot()
    if slot:
        assert "energia_ont" not in last or "reinicio_ont" in (slot.covered_steps or [])
    _assert_shadow_ok(ctx)


def test_replay_t70_howto_shadow():
    bots, ctx = _replay(
        "5492235610702",
        [
            "no me anda el wifi en la tablet",
            "baño",
            "en los otros equipos funciona",
            "estoy al lado del router",
            "como conecto la tablet por cable de red?",
            "entonces, ¿qué hago?",
        ],
    )
    assert any("no se conectan por cable" in (b or "").lower() for b in bots)
    assert (bots[-1] or "").strip()
    _assert_shadow_ok(ctx)


def test_replay_wifi_03_shadow():
    bots, ctx = _replay(
        "5492235610703",
        [
            "No anda el WiFi en la tablet",
            "en el baño",
            "en los otros equipos funciona",
            "¿qué cosa?",
            "ya lo hice",
        ],
    )
    assert bots[-1]
    _assert_shadow_ok(ctx)


def test_replay_contra_01_shadow():
    _bots, ctx = _replay(
        "5492235610704",
        [
            "falla el wifi",
            "solo en la tablet",
            "también en la notebook",
            "no, me refería a todos los equipos",
        ],
    )
    _assert_shadow_ok(ctx)
    hechos = ctx.get("hechos") or {}
    # Fase 7: corrección explícita actualiza alcance; no queda congelado en el primero.
    assert hechos.get("alcance_wifi") == "todos"


def test_replay_switch_01_shadow():
    bots, ctx = _replay(
        "5492235610705",
        [
            "No tengo internet",
            "es fibra",
            "¿cuánto debo?",
            "ya pagué",
            "sigue sin internet",
        ],
    )
    assert bots[-1]
    _assert_shadow_ok(ctx)


def test_replay_switch_02_shadow():
    bots, ctx = _replay(
        "5492235610706",
        [
            "Me vino más cara la factura",
            "además no me anda el wifi en la tablet",
            "en el baño",
            "volvamos a la factura, por qué subió?",
        ],
    )
    cs = hydrate_conversation_state(ctx)
    assert cs.slot("adm-1") is not None
    assert cs.slot("tec-1") is not None
    assert cs.active_slot() is not None
    assert cs.active_slot().kind == "administrativo"
    assert cs.slot("tec-1").status == "paused"
    last = bots[-1] or ""
    assert last.strip()
    assert "reiniciaste el router" not in last.lower()
    _assert_shadow_ok(ctx)


def test_replay_t46_comercial_shadow():
    bots, ctx = _replay(
        "5492235610707",
        [
            "Quiero contratar internet fibra en Batán",
            "Alta nueva de internet fibra en Batán",
            "Batán centro",
            "Sí, pasame con comercial por favor",
        ],
    )
    assert "comercial" in (bots[-1] or "").lower()
    _assert_shadow_ok(ctx)
    assert ctx.get("intencion") == "alta_plan"
