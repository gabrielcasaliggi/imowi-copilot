"""Fase 7: discurso, pending y motor conversacional común.

El significado del turno no depende de paso_idx / idx+1.
"""

from __future__ import annotations

from sqlalchemy import select

from app.domain.conversation_motor import (
    ACT_ANSWER_USER,
    ACT_ASK_NEXT_STEP,
    ACT_RESTATE_PENDING,
    USER_ASK_CAUSE,
    USER_ASK_CLARIFY,
    USER_ASK_FOLLOWUP,
    USER_CONFIRM_ACTION,
    USER_CORRECT_FACT,
    USER_REPORT_PERSISTENCE,
    interpret_turn,
    interpretation_from_ia,
    process_turn,
)
from app.domain.conversation_state import (
    ConversationState,
    DomainSlot,
    Fact,
    LastBotAct,
    PendingBot,
    PendingUser,
    hydrate_conversation_state,
)
from app.domain.flujos_abonado import MSG_WIFI_SIN_CABLE_MOVIL, PLAYBOOKS
from app.estate import canal_repo as crepo
from app.estate.database import get_session_factory
from app.estate.models import Abonado, ConversacionCanal, Organization
from app.services.canal_abonado import procesar_mensaje_entrante

_DNI = "30111222"
_CANAL = "whatsapp"


def _ftth_cs(
    *,
    covered: list[str] | None = None,
    pending_step: str = "reinicio_ont",
    pending_act: str = "ASK_ACTION",
    facts: list[Fact] | None = None,
    last_act: str = "ASK_ACTION",
    turn: int = 5,
    pending_user: PendingUser | None = None,
) -> ConversationState:
    covered = list(covered or ["energia_ont", "luces_los"])
    return ConversationState(
        v=1,
        turn=turn,
        active_domain_id="tec-1",
        domain_stack=["tec-1"],
        domains=[
            DomainSlot(
                id="tec-1",
                kind="tecnico",
                playbook="internet_ftth",
                status="active",
                covered_steps=covered,
                cursor=2,
                opened_turn=1,
            )
        ],
        facts=list(facts or []),
        pending_bot=PendingBot(
            act=pending_act,
            step_id=pending_step,
            referent=pending_step,
            domain_id="tec-1",
            turn=turn,
        ),
        pending_user=pending_user,
        last_bot_act=LastBotAct(
            act=last_act,
            referent=pending_step,
            domain_id="tec-1",
            step_id=pending_step,
            turn=turn,
        ),
    )


def _pasos_ftth():
    return list(PLAYBOOKS["internet_ftth"])


# ---------------------------------------------------------------------------
# T1 — ya lo hice
# ---------------------------------------------------------------------------


def test_t1_ya_lo_hice_confirma_pending_action():
    cs = _ftth_cs()
    interp = interpret_turn("Ya lo hice.", cs, {})
    assert interp.user_act == USER_CONFIRM_ACTION
    assert (interp.referenced or {}).get("step_id") == "reinicio_ont"
    result = process_turn(cs, interp, {}, playbook_steps=_pasos_ftth())
    slot = result.state.active_slot()
    assert slot is not None
    assert "reinicio_ont" in slot.covered_steps
    assert result.state.pending_bot is None
    assert result.action.type == ACT_ASK_NEXT_STEP
    assert result.action.step_id != "reinicio_ont"
    assert result.action.step_id == "cable_fibra"
    assert slot.cursor == 2  # el cursor no es la semántica; no se usó idx+1 para cubrir


# ---------------------------------------------------------------------------
# T2 — sigue igual
# ---------------------------------------------------------------------------


def test_t2_sigue_igual_referente_reinicio_no_luces():
    cs = _ftth_cs()
    interp = interpret_turn("Sigue igual.", cs, {})
    assert interp.user_act == USER_REPORT_PERSISTENCE
    assert (interp.referenced or {}).get("step_id") == "reinicio_ont"
    assert (interp.referenced or {}).get("step_id") not in ("luces_los", "energia_ont")
    result = process_turn(cs, interp, {}, playbook_steps=_pasos_ftth())
    assert "reinicio_ont" in (result.state.active_slot().covered_steps or [])
    assert result.action.referent == "reinicio_ont"
    assert result.action.step_id not in ("luces_los", "energia_ont")
    valores = {f.key: f.value for f in result.state.facts if f.status == "active"}
    assert valores.get("resultado_accion") == "sin_mejora"


# ---------------------------------------------------------------------------
# T3 — qué cosa
# ---------------------------------------------------------------------------


def test_t3_que_cosa_restate_pending_reinicio():
    cs = _ftth_cs(pending_act="ASK_ACTION", last_act="ASK_ACTION")
    interp = interpret_turn("¿Qué cosa?", cs, {})
    assert interp.user_act == USER_ASK_CLARIFY
    assert (interp.referenced or {}).get("step_id") == "reinicio_ont"
    result = process_turn(cs, interp, {}, playbook_steps=_pasos_ftth())
    assert result.action.type == ACT_RESTATE_PENDING
    assert result.action.step_id == "reinicio_ont"
    assert result.state.pending_bot is not None
    assert result.state.pending_bot.step_id == "reinicio_ont"
    slot = result.state.active_slot()
    assert "reinicio_ont" not in (slot.covered_steps or [])


# ---------------------------------------------------------------------------
# T4 — entonces qué hago
# ---------------------------------------------------------------------------


def test_t4_entonces_que_hago_sigue_instruccion():
    cs = ConversationState(
        v=1,
        turn=8,
        active_domain_id="tec-1",
        domain_stack=["tec-1"],
        domains=[
            DomainSlot(
                id="tec-1",
                kind="tecnico",
                playbook="wifi",
                status="active",
                covered_steps=["conexion_cableada", "otros_dispositivos_wifi", "zona_wifi"],
                cursor=5,
            )
        ],
        facts=[
            Fact(key="dispositivo_sin_ethernet", value=True, domain_id="tec-1", status="active"),
            Fact(key="alcance_wifi", value="uno", domain_id="tec-1", status="active"),
        ],
        pending_user=PendingUser(
            act="ASK_HOW_TO",
            text="como conecto la tablet por cable",
            referent="conexion_cableada_tablet",
            domain_id="tec-1",
            turn=7,
            status="open",
        ),
        last_bot_act=LastBotAct(
            act="PROVIDE_INSTRUCTION",
            referent="conexion_cableada_tablet",
            domain_id="tec-1",
            step_id="conexion_cableada",
            turn=7,
        ),
    )
    interp = interpret_turn("Entonces qué hago?", cs, {})
    assert interp.user_act == USER_ASK_FOLLOWUP
    assert (interp.referenced or {}).get("referent") == "conexion_cableada_tablet"
    result = process_turn(cs, interp, {}, playbook_steps=list(PLAYBOOKS["wifi"]))
    assert result.action.type == ACT_ANSWER_USER
    assert result.action.referent == "conexion_cableada_tablet"
    assert result.action.type != ACT_ASK_NEXT_STEP
    assert result.action.step_id != "reinicio_router_wifi"


# ---------------------------------------------------------------------------
# T5 — corrección de alcance wifi
# ---------------------------------------------------------------------------


def test_t5_correccion_alcance_no_deja_dos_activos():
    cs = ConversationState(
        v=1,
        turn=2,
        active_domain_id="tec-1",
        domain_stack=["tec-1"],
        domains=[DomainSlot(id="tec-1", kind="tecnico", playbook="wifi", status="active")],
        facts=[
            Fact(key="alcance_wifi", value="uno", domain_id="tec-1", source_turn=1, status="active"),
        ],
    )
    interp = interpret_turn("También falla la notebook.", cs, {"hechos": {"alcance_wifi": "uno"}})
    assert interp.user_act == USER_CORRECT_FACT
    result = process_turn(cs, interp, {"hechos": {"alcance_wifi": "uno"}})
    rows = [f for f in result.state.facts if f.key == "alcance_wifi"]
    actives = [f for f in rows if f.status == "active"]
    assert len(actives) == 1
    assert actives[0].value == "todos"
    assert any(f.status == "superseded" and f.value == "uno" for f in rows)

    interp2 = interpret_turn("Ninguno funciona.", result.state, {})
    result2 = process_turn(result.state, interp2, {})
    actives2 = [
        f for f in result2.state.facts if f.key == "alcance_wifi" and f.status == "active"
    ]
    assert len(actives2) == 1
    assert actives2[0].value == "todos"


# ---------------------------------------------------------------------------
# T6 — persistencia con hecho previo PON rojo
# ---------------------------------------------------------------------------


def test_t6_persistencia_conserva_pon_y_avanza_real():
    cs = _ftth_cs(
        covered=["energia_ont", "luces_los"],
        facts=[
            Fact(key="luces_ont", value="pon_rojo", domain_id="tec-1", source_turn=2, status="active"),
        ],
    )
    r1 = process_turn(
        cs,
        interpret_turn("Ya la reinicié.", cs, {}),
        {},
        playbook_steps=_pasos_ftth(),
    )
    r2 = process_turn(
        r1.state,
        interpret_turn("Sigue igual.", r1.state, {}),
        {},
        playbook_steps=_pasos_ftth(),
    )
    valores = {f.key: f.value for f in r2.state.facts if f.status == "active"}
    assert valores.get("luces_ont") == "pon_rojo"
    assert valores.get("accion_reinicio_ont") in ("realizada", "realizada_sin_mejora")
    assert valores.get("resultado_accion") == "sin_mejora"
    assert "reinicio_ont" in (r2.state.active_slot().covered_steps or [])
    assert r2.action.step_id == "cable_fibra"
    assert r2.action.step_id not in ("energia_ont", "luces_los")


# ---------------------------------------------------------------------------
# Adapter IA
# ---------------------------------------------------------------------------


def test_adapter_ia_no_cubre_paso_sugerido_por_llm():
    cs = _ftth_cs()
    ia = {"accion": "ask", "paso_cubierto": "luces_los", "mensaje": "¿La PON está verde?"}
    interp = interpretation_from_ia(ia, "Ya lo hice.", cs, {})
    assert interp.user_act == USER_CONFIRM_ACTION
    assert interp.ia_suggested_step == "luces_los"
    result = process_turn(cs, interp, {}, playbook_steps=_pasos_ftth())
    covered = result.state.active_slot().covered_steps
    assert "reinicio_ont" in covered
    # el LLM no puede cubrir luces por su cuenta en este turno
    assert result.action.referent == "reinicio_ont"


# ---------------------------------------------------------------------------
# Helpers E2E
# ---------------------------------------------------------------------------


def _abrir_hilo(tel: str, *, ctx: dict | None = None, historial_bot: str = "") -> str:
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org
        abo = db.scalar(select(Abonado).where(Abonado.dni == _DNI))
        assert abo is not None
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
            db, org.id, telefono=tel, canal=_CANAL, wa_id=tel
        )
        conv.estado = "bot"
        conv.abonado_id = abo.id
        conv.ticket_id = ""
        base = {"saludo": True, "identificado": True, "dni": _DNI}
        if ctx:
            base.update(ctx)
        crepo.set_contexto(conv, base)
        if historial_bot:
            crepo.add_mensaje(
                db,
                org.id,
                conv.id,
                direccion="out",
                autor="bot",
                texto=historial_bot,
            )
        db.commit()
        return org.id


def _msg(org_id: str, tel: str, texto: str) -> dict:
    Session = get_session_factory()
    with Session() as db:
        return procesar_mensaje_entrante(
            db,
            org_id,
            telefono=tel,
            texto=texto,
            canal=_CANAL,
            usar_llama=False,
        )


def _ctx(conv_id: str) -> dict:
    Session = get_session_factory()
    with Session() as db:
        conv = db.get(ConversacionCanal, conv_id)
        assert conv is not None
        return crepo.get_contexto(conv)


def _cs_seed_reinicio() -> dict:
    cs = _ftth_cs(
        facts=[
            Fact(
                key="tecnologia_acceso",
                value="internet_ftth",
                domain_id="tec-1",
                source_turn=1,
                status="active",
            )
        ]
    )
    return cs.to_dict()


# ---------------------------------------------------------------------------
# T1-T3 integración
# ---------------------------------------------------------------------------


def test_t1_e2e_ya_lo_hice_cubre_reinicio():
    tel = "5492235610801"
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "internet_ftth",
            "paso_idx": 2,
            "pasos_cubiertos": ["energia_ont", "luces_los"],
            "hechos": {"tecnologia_acceso": "internet_ftth"},
            "cs": _cs_seed_reinicio(),
        },
        historial_bot=(
            "Desenchufá ONT y router 30 segundos; prendé primero la ONT. ¿Volvió?"
        ),
    )
    r = _msg(org_id, tel, "Ya lo hice.")
    ctx = _ctx(r["conversacion_id"])
    cs = hydrate_conversation_state(ctx)
    slot = cs.active_slot()
    assert slot is not None
    assert "reinicio_ont" in slot.covered_steps
    assert "reinicio_ont" in (ctx.get("pasos_cubiertos") or [])
    last = (r.get("respuesta") or "").lower()
    assert "cajita blanca" not in last
    assert "luz pon" not in last


def test_t3_e2e_que_cosa_reexplica():
    tel = "5492235610802"
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "internet_ftth",
            "paso_idx": 2,
            "pasos_cubiertos": ["energia_ont", "luces_los"],
            "hechos": {"tecnologia_acceso": "internet_ftth"},
            "cs": _cs_seed_reinicio(),
        },
        historial_bot="¿Reiniciaste la ONT?",
    )
    r = _msg(org_id, tel, "¿Qué cosa?")
    ctx = _ctx(r["conversacion_id"])
    cs = hydrate_conversation_state(ctx)
    assert cs.pending_bot is not None
    assert cs.pending_bot.step_id == "reinicio_ont"
    resp = (r.get("respuesta") or "").lower()
    assert "reinici" in resp or "ont" in resp
    assert "ticket" not in resp


# ---------------------------------------------------------------------------
# T7 — FTTH → factura preserva técnico
# ---------------------------------------------------------------------------


def test_t7_ftth_a_factura_preserva_dominio_tecnico():
    tel = "5492235610803"
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "internet_ftth",
            "paso_idx": 2,
            "pasos_cubiertos": ["energia_ont", "luces_los"],
            "hechos": {
                "tecnologia_acceso": "internet_ftth",
                "luces_ont": "pon_rojo",
            },
            "cs": _cs_seed_reinicio(),
        },
        historial_bot="Desenchufá ONT y router 30 segundos. ¿Volvió?",
    )
    r = _msg(org_id, tel, "¿cuánto debo?")
    ctx = _ctx(r["conversacion_id"])
    cs = hydrate_conversation_state(ctx)
    tech = cs.slot_by_kind("tecnico")
    assert tech is not None
    if cs.active_slot() and cs.active_slot().kind != "tecnico":
        assert tech.status == "paused"
    assert any(
        f.key in ("tecnologia_acceso", "luces_ont") and f.status == "active"
        for f in cs.facts
        if f.domain_id == "tec-1"
    )


# ---------------------------------------------------------------------------
# T8 — factura → FTTH no destruye hechos
# ---------------------------------------------------------------------------


def test_t8_vuelve_a_ftth_sin_destruir_hechos():
    tel = "5492235610804"
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "internet_ftth",
            "paso_idx": 2,
            "pasos_cubiertos": ["energia_ont", "luces_los"],
            "hechos": {
                "tecnologia_acceso": "internet_ftth",
                "luces_ont": "pon_rojo",
            },
            "cs": _cs_seed_reinicio(),
        },
    )
    r1 = _msg(org_id, tel, "¿cuánto debo?")
    r2 = _msg(org_id, tel, "Sigo sin internet.")
    ctx = _ctx(r2["conversacion_id"] or r1["conversacion_id"])
    cs = hydrate_conversation_state(ctx)
    tech = cs.slot_by_kind("tecnico")
    assert tech is not None
    assert any(
        f.key in ("tecnologia_acceso", "luces_ont") and f.status == "active"
        for f in cs.facts
        if f.domain_id == tech.id
    )


# ---------------------------------------------------------------------------
# T9 — T70 how-to tablet
# ---------------------------------------------------------------------------


def test_t9_t70_howto_tablet_no_reinicio():
    tel = "5492235610805"
    ids = [p.id for p in PLAYBOOKS["wifi"]]
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "wifi",
            "paso_idx": ids.index("repetidor_cable_ap"),
            "diag_turnos": 6,
            "pasos_cubiertos": [
                "conexion_cableada",
                "otros_dispositivos_wifi",
                "zona_wifi",
            ],
            "hechos": {
                "dispositivo_afectado": "tablet",
                "dispositivo_sin_ethernet": True,
                "alcance_wifi": "uno",
                "zona_wifi": "baño",
            },
        },
        historial_bot="Si podés, conectar el repetidor al router con cable de red. ¿Lo probaste?",
    )
    r = _msg(org_id, tel, "como conecto la tablet por cable de red?")
    ctx = _ctx(r["conversacion_id"])
    cs = hydrate_conversation_state(ctx)
    resp = (r.get("respuesta") or "").lower()
    assert r.get("respuesta") == MSG_WIFI_SIN_CABLE_MOVIL
    assert "reiniciaste el router" not in resp
    assert cs.pending_user is not None
    assert cs.pending_user.act == "ASK_HOW_TO"
    assert cs.last_bot_act is not None
    assert cs.last_bot_act.act == "PROVIDE_INSTRUCTION"


# ---------------------------------------------------------------------------
# T10 — WIFI-03 referente explícito
# ---------------------------------------------------------------------------


def test_t10_wifi03_que_cosa_luego_ya_lo_hice():
    tel = "5492235610806"
    ids = [p.id for p in PLAYBOOKS["wifi"]]
    cs_raw = ConversationState(
        v=1,
        turn=6,
        active_domain_id="tec-1",
        domain_stack=["tec-1"],
        domains=[
            DomainSlot(
                id="tec-1",
                kind="tecnico",
                playbook="wifi",
                status="active",
                covered_steps=["zona_wifi", "conexion_cableada", "otros_dispositivos_wifi"],
                cursor=ids.index("clave_wifi_etiqueta"),
            )
        ],
        facts=[
            Fact(key="alcance_wifi", value="uno", domain_id="tec-1", status="active"),
            Fact(key="dispositivo_sin_ethernet", value=True, domain_id="tec-1", status="active"),
        ],
        pending_bot=PendingBot(
            act="ASK_FACT",
            step_id="clave_wifi_etiqueta",
            referent="clave_wifi_etiqueta",
            domain_id="tec-1",
            turn=6,
        ),
        last_bot_act=LastBotAct(
            act="ASK_FACT",
            referent="clave_wifi_etiqueta",
            domain_id="tec-1",
            step_id="clave_wifi_etiqueta",
            turn=6,
        ),
    )
    org_id = _abrir_hilo(
        tel,
        ctx={
            "intencion": "wifi",
            "paso_idx": ids.index("clave_wifi_etiqueta"),
            "pasos_cubiertos": [
                "zona_wifi",
                "conexion_cableada",
                "otros_dispositivos_wifi",
            ],
            "hechos": {
                "alcance_wifi": "uno",
                "dispositivo_afectado": "tablet",
                "dispositivo_sin_ethernet": True,
            },
            "cs": cs_raw.to_dict(),
        },
        historial_bot="En la etiqueta del módem está la clave. ¿Pudiste entrar?",
    )
    r1 = _msg(org_id, tel, "¿Qué cosa?")
    ctx1 = _ctx(r1["conversacion_id"])
    cs1 = hydrate_conversation_state(ctx1)
    assert cs1.pending_bot is not None
    assert cs1.pending_bot.step_id == "clave_wifi_etiqueta"
    assert cs1.pending_bot.referent
    r2 = _msg(org_id, tel, "Ya lo hice.")
    ctx2 = _ctx(r2["conversacion_id"])
    cs2 = hydrate_conversation_state(ctx2)
    covered = cs2.active_slot().covered_steps if cs2.active_slot() else []
    assert "clave_wifi_etiqueta" in covered
    if cs2.pending_bot:
        assert cs2.pending_bot.step_id != "clave_wifi_etiqueta"
        assert cs2.pending_bot.referent


def _wifi_adm_paused_cs() -> ConversationState:
    return ConversationState(
        v=1,
        turn=6,
        active_domain_id="tec-1",
        domain_stack=["tec-1", "adm-1"],
        domains=[
            DomainSlot(
                id="tec-1",
                kind="tecnico",
                playbook="wifi",
                status="active",
                covered_steps=["zona_wifi"],
                cursor=3,
                pending_bot=PendingBot(
                    act="ASK_ACTION",
                    step_id="reinicio_router_wifi",
                    referent="reinicio_router_wifi",
                    domain_id="tec-1",
                    turn=5,
                ),
            ),
            DomainSlot(
                id="adm-1",
                kind="administrativo",
                playbook="facturacion",
                status="paused",
                covered_steps=[],
                cursor=0,
            ),
        ],
        pending_bot=PendingBot(
            act="ASK_ACTION",
            step_id="reinicio_router_wifi",
            referent="reinicio_router_wifi",
            domain_id="tec-1",
            turn=5,
        ),
        last_bot_act=LastBotAct(
            act="ASK_ACTION",
            step_id="reinicio_router_wifi",
            referent="reinicio_router_wifi",
            domain_id="tec-1",
            turn=5,
        ),
    )


def test_ds8_compound_domain_signal_and_ask_cause():
    cs = _wifi_adm_paused_cs()
    interp = interpret_turn("Volvamos a la factura, por qué subió?", cs, {})
    assert interp.domain_signal == "administrativo"
    assert interp.user_act == USER_ASK_CAUSE


def test_ds6_porque_without_domain_signal_stays_cause():
    cs = _wifi_adm_paused_cs()
    interp = interpret_turn("¿Por qué?", cs, {})
    assert interp.domain_signal is None
    assert interp.user_act == USER_ASK_CAUSE


def test_ds5_cause_on_active_admin_no_tech_signal():
    cs = _wifi_adm_paused_cs()
    cs.active_domain_id = "adm-1"
    cs.domains[0].status = "paused"
    cs.domains[1].status = "active"
    cs.pending_bot = None
    interp = interpret_turn("¿Por qué subió?", cs, {})
    assert interp.domain_signal is None
    assert interp.user_act == USER_ASK_CAUSE


def test_correction_without_kind_change_stays_tech():
    cs = _wifi_adm_paused_cs()
    interp = interpret_turn("También falla la notebook.", cs, {"hechos": {"alcance_wifi": "uno"}})
    assert interp.user_act == USER_CORRECT_FACT
    assert interp.domain_signal is None
