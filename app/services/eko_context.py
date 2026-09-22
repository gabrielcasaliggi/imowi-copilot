"""Eko Context Adapter — facts comerciales para N1 (Fases 3A/3B).

Fuente factual canónica del prompt N1. No llama Radius/BCM/UISP.
Conversation State y Technical Observations se inyectan por separado (extras).
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger("operations_hub")

# Claves de observación técnica / sesión que pueden venir en extras tras diagnóstico.
_TECH_KEYS = frozenset(
    {
        "pppoe_resumen",
        "pppoe_triage",
        "pppoe_estado",
        "pppoe_login",
        "pppoe_tipo",
        "pppoe_ip",
        "pppoe_uptime",
        "pppoe_nas",
        "pppoe_producto",
        "pppoe_plan_mbps",
        "uisp_resumen",
        "uisp_triage",
        "uisp_estado",
        "uisp_login",
        "uisp_sitio",
        "uisp_senal",
        "uisp_modelo",
        "uisp_signal_dbm",
        "uisp_calidad_senal",
        "bcm_resumen",
        "bcm_triage",
        "bcm_estado",
        "bcm_serial",
        "bcm_olt",
        "bcm_rx",
        "bcm_modelo",
        "ont_estado",
        "olt_huawei",
    }
)

_OV_KEYS = frozenset(
    {
        "ov_url_pagar",
        "ov_url_my",
        "ov_handoff_mode",
        "ov_handoff_reason",
        "celular_ov",
        "celulares_ov",
    }
)

_STATE_KEYS = frozenset(
    {
        "canal",
        "tecnologia_acceso",
        "pago_qr_reciente",
        "cortes_zona",
    }
)


def billing_capabilities_hint(*, ov_available: bool = True) -> dict[str, bool]:
    """Metadata de qué puede responder Eko hoy (MVP 2.1). No autoriza mutaciones."""
    return {
        "can_answer_balance": True,
        "can_answer_invoice_fields": False,
        "can_answer_payment_history": False,
        "can_navigate_ov": bool(ov_available),
    }


def build_eko_facts(
    abonado: Any | None,
    *,
    db: Session | None = None,
    org_id: str = "",
) -> dict[str, Any]:
    """Hechos comerciales/identidad para N1. Sin technical probes.

    Dominios: customer, account, services, billing, tickets, ov, meta.
    tickets/ov usan readers estables; OV solo links públicos (auth externa).
    """
    _ = org_id
    ov_block = load_ov_facts(db=db)
    ov_ok = bool(ov_block.get("available"))
    hints = billing_capabilities_hint(ov_available=ov_ok)

    if abonado is None:
        return {
            "customer": None,
            "account": None,
            "services": {"status": "empty", "items": [], "reason_code": None},
            "billing": {
                "status": "unavailable",
                "balance": None,
                "reason_code": "missing_identity",
                "capabilities_hint": {
                    **hints,
                    "can_answer_balance": False,
                },
            },
            "tickets": {
                "status": "omitted",
                "items": [],
                "reason_code": "missing_identity_or_db",
            },
            "ov": ov_block,
            "meta": {"source": "eko_context", "probes": False},
        }

    customer = {
        "id": str(getattr(abonado, "id", "") or ""),
        "display_name": str(getattr(abonado, "nombre", "") or "").strip(),
        "organization_id": str(getattr(abonado, "organizacion_id", "") or ""),
        "line_msisdn": str(getattr(abonado, "linea_msisdn", "") or "").strip(),
    }
    account = {
        "client_number": str(getattr(abonado, "client_number", "") or "").strip(),
        "status": str(getattr(abonado, "estado", "") or "").strip(),
        "plan": str(getattr(abonado, "plan", "") or "").strip(),
        "servicio_agregado": str(getattr(abonado, "servicio", "") or "").strip(),
    }
    amount = str(getattr(abonado, "deuda_monto", "") or "0").strip() or "0"
    billing = {
        "status": "stale",
        "balance": {
            "amount": amount,
            "currency": "ARS",
            "as_of": None,
            "freshness": "snapshot",
        },
        "reason_code": "stale_snapshot",
        "capabilities_hint": hints,
    }

    services_block: dict[str, Any] = {
        "status": "empty",
        "items": [],
        "reason_code": None,
    }
    if db is not None:
        try:
            from app.services.portal_services import evaluar_servicios_portal

            raw = evaluar_servicios_portal(db, abonado=abonado)
            st = str(raw.get("status") or "")
            items = list(raw.get("services") or [])
            if st == "unavailable":
                services_block = {
                    "status": "unavailable",
                    "items": [],
                    "reason_code": str(raw.get("reason_code") or "source_unavailable"),
                }
            elif not items:
                services_block = {
                    "status": "empty",
                    "items": [],
                    "reason_code": None,
                }
            else:
                services_block = {
                    "status": "ok",
                    "items": items,
                    "reason_code": None,
                    "checked_at": raw.get("checked_at"),
                }
        except Exception:
            logger.exception("eko_context: services reader falló")
            services_block = {
                "status": "unavailable",
                "items": [],
                "reason_code": "source_unavailable",
            }

    from app.services.abonado_tickets import load_ticket_facts

    tickets_block = load_ticket_facts(abonado, db=db, org_id=org_id)

    return {
        "customer": customer,
        "account": account,
        "services": services_block,
        "billing": billing,
        "tickets": tickets_block,
        "ov": ov_block,
        "meta": {"source": "eko_context", "probes": False},
    }


def load_ov_facts(*, db: Session | None = None) -> dict[str, Any]:
    """Links públicos OV ya soportados. Sin JSAT, sid, tsid ni cookies.

    Auth permanece externa (usuario se autentica en OV).
    """
    try:
        from app.services.ov_batan import resolve_ov_batan
        from app.services.ov_handoff import DEFAULT_AUDIENCE, public_url_for_destination

        cfg = resolve_ov_batan(db)
        public_base = str(cfg.get("public_url") or DEFAULT_AUDIENCE).rstrip("/")
        links = {
            "pay": public_url_for_destination("pagar", public_base=public_base),
            "invoice": public_url_for_destination("my", public_base=public_base),
            "payment_slip": public_url_for_destination(
                "talon-de-pago", public_base=public_base
            ),
        }
        return {
            "available": True,
            "links": links,
            "auth": "external",
        }
    except Exception:
        logger.exception("eko_context: ov facts falló")
        return {
            "available": False,
            "links": {},
            "auth": "external",
            "reason_code": "source_unavailable",
        }


# --- Accesores factuales (3C): consumers N1 leen Facts, no ORM directo ---

_CORTADO_COMERCIAL = frozenset({"corte", "cortado", "suspendido", "suspendida"})


def account_status(facts: dict[str, Any]) -> str:
    """Estado comercial de cuenta (≠ conectividad técnica)."""
    account = facts.get("account") or {}
    return str(account.get("status") or "").strip().lower()


def account_plan(facts: dict[str, Any]) -> str:
    account = facts.get("account") or {}
    return str(account.get("plan") or "").strip()


def account_client_number(facts: dict[str, Any]) -> str:
    account = facts.get("account") or {}
    return str(account.get("client_number") or "").strip()


def servicio_agregado(facts: dict[str, Any]) -> str:
    """Agregado legacy internet/movil/ambos — desde Facts, no ORM."""
    account = facts.get("account") or {}
    return str(account.get("servicio_agregado") or "").strip().lower()


def billing_status(facts: dict[str, Any]) -> str:
    billing = facts.get("billing") or {}
    return str(billing.get("status") or "").strip().lower()


def billing_amount_str(facts: dict[str, Any]) -> str | None:
    """Monto de deuda desde Facts.

    - ``None`` si billing unavailable (no inventar $0).
    - string amount si hay balance (incluye ``\"0\"``).
    """
    billing = facts.get("billing") or {}
    if billing.get("status") == "unavailable" and billing.get("balance") is None:
        return None
    bal = billing.get("balance") or {}
    if not bal or bal.get("amount") is None:
        return None
    return str(bal.get("amount") or "0").strip() or "0"


def has_positive_debt(facts: dict[str, Any]) -> bool:
    """True si el padrón indica deuda. Misma semántica que legacy ``_deuda_positiva``.

    unavailable / amount no parseable + estado no cortado → False.
    amount no parseable + corte/suspendido → True (fallback comercial).
    """
    from app.services.eco_voice import parse_monto

    amount = billing_amount_str(facts)
    if amount is None:
        return False
    m = parse_monto(amount)
    if m is None:
        return account_status(facts) in ("corte", "suspendido")
    return m > 0


def is_commercially_cut(facts: dict[str, Any]) -> bool:
    """Corte/suspensión comercial (no implica offline técnico)."""
    return account_status(facts) in _CORTADO_COMERCIAL


def service_types_present(facts: dict[str, Any]) -> set[str]:
    """Tipos comerciales en catálogo tipado; vacío si no hay items ok."""
    services = facts.get("services") or {}
    if services.get("status") != "ok":
        return set()
    out: set[str] = set()
    for it in services.get("items") or []:
        tip = str(it.get("type") or "").strip().lower()
        if tip:
            out.add(tip)
    return out


def extract_technical_observations(extras: dict[str, str] | None) -> dict[str, str]:
    """Solo claves técnicas presentes en extras (post-diagnóstico). No probes."""
    out: dict[str, str] = {}
    for k, v in (extras or {}).items():
        if k in _TECH_KEYS and str(v or "").strip():
            out[k] = str(v).strip()
    return out


def _etiqueta_servicios_agregado(servicio: str) -> str:
    """Misma semántica que eco_voice._etiqueta_servicios (sin import circular)."""
    from app.domain.flujos_abonado import productos_contratados

    s = (servicio or "").strip().lower()
    if s == "movil":
        return "móvil IMOWI (sin internet fijo)"
    if s == "internet":
        return "internet fijo (sin móvil IMOWI)"
    if s == "ambos":
        return "internet fijo y móvil IMOWI"
    prods = productos_contratados(s)
    if not prods:
        return "(sin dato de productos en padrón)"
    labels: list[str] = []
    if "internet" in prods:
        labels.append("internet fijo")
    if "movil" in prods:
        labels.append("móvil IMOWI")
    if "tv" in prods:
        labels.append("Sensa/TV")
    if labels == ["móvil IMOWI"]:
        return "móvil IMOWI (sin internet fijo)"
    if labels == ["internet fijo"]:
        return "internet fijo (sin móvil IMOWI)"
    if len(labels) == 2:
        return f"{labels[0]} y {labels[1]}"
    return ", ".join(labels[:-1]) + " y " + labels[-1]


def _servicios_contratados_label(facts: dict[str, Any]) -> str:
    """Preferir catálogo tipado; fallback a agregado legacy."""
    services = facts.get("services") or {}
    items = services.get("items") or []
    if services.get("status") == "ok" and items:
        types: list[str] = []
        for it in items:
            tip = str(it.get("type") or "").strip().lower()
            if tip == "internet" and "internet fijo" not in types:
                types.append("internet fijo")
            elif tip == "movil" and "móvil IMOWI" not in types:
                types.append("móvil IMOWI")
            elif tip == "tv" and "TV/Sensa" not in types:
                types.append("TV/Sensa")
            elif tip == "telefonia" and "telefonía fija" not in types:
                types.append("telefonía fija")
        if types:
            return ", ".join(types)
    account = facts.get("account") or {}
    return _etiqueta_servicios_agregado(str(account.get("servicio_agregado") or ""))


def format_n1_contexto(
    facts: dict[str, Any],
    *,
    extras: dict[str, str] | None = None,
    dni_enmascarado: str = "",
) -> str:
    """Render CONTEXTO_ABONADO desde Eko Facts + extras (OV/state/observations).

    Separación semántica en secciones. No ejecuta probes.
    """
    extras = dict(extras or {})
    tech = extract_technical_observations(extras)
    customer = facts.get("customer")
    account = facts.get("account") or {}
    billing = facts.get("billing") or {}
    bal = billing.get("balance") or {}
    services = facts.get("services") or {}

    if customer is None:
        lines = [
            "CONTEXTO_ABONADO:",
            "## CUSTOMER FACTS",
            "- modo: invitado (sin cuenta identificada)",
            "- nombre: (sin dato)",
            "- nro_asociado: (sin dato)",
            "## ACCOUNT FACTS",
            "- estado_servicio: (sin dato)",
            "## BILLING",
            "- deuda: (sin dato)",
            "- billing_status: unavailable",
            "## TECHNICAL OBSERVATIONS",
            f"- ont_estado: {tech.get('ont_estado') or '(sin dato — integrar NMS)'}",
            f"- olt_huawei: {tech.get('olt_huawei') or '(sin dato — integrar NMS)'}",
            f"- pago_qr_reciente: {extras.get('pago_qr_reciente') or '(sin dato — integrar Fiserv)'}",
            f"- cortes_zona: {extras.get('cortes_zona') or '(sin dato — integrar operaciones)'}",
            f"- pppoe: {tech.get('pppoe_resumen') or '(sin dato — integrar Radius/NAS)'}",
            f"- uisp: {tech.get('uisp_resumen') or '(sin dato — integrar UISP)'}",
            f"- bcm: {tech.get('bcm_resumen') or '(sin dato — integrar BCM)'}",
            "- Regla: no inventes saldos, ONT/OLT, PPPoE, UISP, BCM ni pagos. Pedí DNI/N.º de socio si hace falta la cuenta.",
        ]
        for ov_k in sorted(_OV_KEYS):
            ov_v = (extras.get(ov_k) or "").strip()
            if ov_v:
                lines.insert(-1, f"- {ov_k}: {ov_v}")
        canal = (extras.get("canal") or "").strip()
        if canal:
            lines.insert(-1, f"- canal: {canal}")
        return "\n".join(lines)

    nombre = str(customer.get("display_name") or "").strip() or "(sin dato)"
    nro = str(account.get("client_number") or "").strip() or "(sin dato — integrar asociados)"
    plan = str(account.get("plan") or "").strip() or "(sin dato)"
    estado = str(account.get("status") or "").strip() or "(sin dato)"
    servicio_agg = str(account.get("servicio_agregado") or "").strip() or "(sin dato)"
    linea = str(customer.get("line_msisdn") or "").strip() or "(sin dato)"
    deuda = "0"
    if bal and bal.get("amount") is not None:
        deuda = str(bal.get("amount") or "0").strip() or "0"
    elif billing.get("status") == "unavailable" and not bal:
        deuda = "(sin dato)"

    from app.services.velocidad_plan import extraer_mbps_plan, formatear_mbps

    plan_mbps = extraer_mbps_plan(
        tech.get("pppoe_plan_mbps") or "",
        tech.get("pppoe_producto") or "",
        plan,
        tech.get("pppoe_resumen") or "",
    )
    if plan_mbps is None and (tech.get("pppoe_plan_mbps") or "").strip():
        try:
            plan_mbps = float(str(tech.get("pppoe_plan_mbps")).replace(",", "."))
        except (TypeError, ValueError):
            plan_mbps = None

    contratados = _servicios_contratados_label(facts)

    lines: list[str] = [
        "CONTEXTO_ABONADO (datos reales del sistema; usalos solo si aportan):",
        "## CUSTOMER FACTS",
        "- modo: identificado",
        f"- nombre: {nombre}",
        f"- dni_enmascarado: {dni_enmascarado or '(sin dato)'}",
        f"- linea: {linea}",
        "## ACCOUNT FACTS",
        f"- nro_asociado: {nro}",
        f"- estado_servicio: {estado}",
        f"- plan: {plan}",
        f"- servicio: {servicio_agg}",
        f"- servicios_contratados: {contratados}",
    ]
    if plan_mbps is not None:
        lines.append(f"- plan_contratado: {formatear_mbps(plan_mbps)} Mbps")
        lines.append(f"- plan_mbps: {plan_mbps:g}")

    lines.append("## SERVICES")
    items = services.get("items") or []
    if services.get("status") == "ok" and items:
        parts = []
        for it in items[:20]:
            tip = str(it.get("type") or "other")
            lab = str(it.get("label") or it.get("product") or tip).strip()
            act = "activo" if it.get("active") else "no_activo"
            parts.append(f"{tip}:{lab}({act})")
        lines.append(f"- servicios_catalogo: {'; '.join(parts)}")
        lines.append(
            "- Nota: active en catálogo es comercial, no implica Internet técnicamente operativo."
        )
    elif services.get("status") == "unavailable":
        lines.append("- servicios_catalogo: (fuente no disponible)")
    else:
        lines.append("- servicios_catalogo: (vacío o no consultado)")

    lines.append("## BILLING")
    lines.append(f"- deuda_monto: {deuda}")
    lines.append(f"- billing_status: {billing.get('status') or 'stale'}")
    if bal.get("freshness"):
        lines.append(f"- billing_freshness: {bal.get('freshness')}")
    if bal.get("currency"):
        lines.append(f"- billing_currency: {bal.get('currency')}")
    if bal.get("as_of") is None:
        lines.append("- billing_as_of: (sin dato)")
    else:
        lines.append(f"- billing_as_of: {bal.get('as_of')}")

    # TICKETS (factual, ownership-scoped)
    tickets = facts.get("tickets") or {}
    lines.append("## TICKETS")
    t_items = tickets.get("items") or []
    if tickets.get("status") == "ok" and t_items:
        parts = []
        for it in t_items[:10]:
            tid = str(it.get("id") or "")[:12]
            st = str(it.get("state") or "")
            cat = str(it.get("category") or "")
            parts.append(f"{tid}:{st}/{cat}".strip(":"))
        lines.append(f"- tickets_abiertos_resumen: {'; '.join(parts)}")
        lines.append(f"- tickets_count: {len(t_items)}")
    elif tickets.get("status") == "unavailable":
        lines.append("- tickets: (fuente no disponible)")
    elif tickets.get("status") == "omitted":
        lines.append("- tickets: (no consultados)")
    else:
        lines.append("- tickets: (ninguno visible)")

    # SUPPORT / OV: facts públicos + handoff del turno (extras) si existe
    ov_facts = facts.get("ov") or {}
    ov_links = ov_facts.get("links") or {}
    ov_present = any(str(extras.get(k) or "").strip() for k in _OV_KEYS)
    if ov_facts.get("available") or ov_present or ov_links:
        lines.append("## SUPPORT / OV")
        if ov_facts.get("available"):
            lines.append("- ov_available: true")
            lines.append(f"- ov_auth: {ov_facts.get('auth') or 'external'}")
            if ov_links.get("pay"):
                lines.append(f"- ov_link_pay: {ov_links['pay']}")
            if ov_links.get("invoice"):
                lines.append(f"- ov_link_invoice: {ov_links['invoice']}")
            if ov_links.get("payment_slip"):
                lines.append(f"- ov_link_payment_slip: {ov_links['payment_slip']}")
        for ov_k in (
            "ov_url_pagar",
            "ov_url_my",
            "ov_handoff_mode",
            "ov_handoff_reason",
            "celular_ov",
            "celulares_ov",
        ):
            ov_v = (extras.get(ov_k) or "").strip()
            if ov_v:
                lines.append(f"- {ov_k}: {ov_v}")

    # CONVERSATION STATE hints mínimos relevantes al prompt
    state_bits = []
    for sk in ("canal", "tecnologia_acceso"):
        sv = (extras.get(sk) or "").strip()
        if sv:
            state_bits.append(f"- {sk}: {sv}")
    if state_bits:
        lines.append("## CONVERSATION STATE")
        lines.extend(state_bits)

    lines.append("## TECHNICAL OBSERVATIONS")
    lines.append(
        f"- ont_estado: {tech.get('ont_estado') or '(sin dato — integrar NMS)'}"
    )
    lines.append(
        f"- olt_huawei: {tech.get('olt_huawei') or '(sin dato — integrar NMS)'}"
    )
    lines.append(
        f"- pago_qr_reciente: {extras.get('pago_qr_reciente') or '(sin dato — integrar Fiserv)'}"
    )
    lines.append(
        f"- cortes_zona: {extras.get('cortes_zona') or '(sin dato — integrar operaciones)'}"
    )
    lines.append(
        f"- pppoe: {tech.get('pppoe_resumen') or '(sin dato — integrar Radius/NAS)'}"
    )
    if tech.get("pppoe_triage"):
        lines.append(f"- pppoe_triage: {tech['pppoe_triage']}")
    lines.append(f"- uisp: {tech.get('uisp_resumen') or '(sin dato — integrar UISP)'}")
    if tech.get("uisp_triage"):
        lines.append(f"- uisp_triage: {tech['uisp_triage']}")
    lines.append(f"- bcm: {tech.get('bcm_resumen') or '(sin dato — integrar BCM)'}")
    if tech.get("bcm_triage"):
        lines.append(f"- bcm_triage: {tech['bcm_triage']}")

    lines.extend(
        [
            "- Regla: si un campo dice '(sin dato)', no lo completes de memoria.",
            "- Los montos de deuda/factura/saldo son SIEMPRE pesos argentinos (ARS). "
            "Nunca digas dólares, USD ni 'dollar'. Preferí «pesos» o «$ … pesos».",
            "- Si billing_status es stale o unavailable, NO digas «cuenta al día» "
            "solo por falta de dato; usá deuda_monto solo si está presente.",
            "- Ofrecé SOLO los servicios_contratados. No preguntes por internet/fibra/Wi‑Fi "
            "si no figura internet fijo, ni por móvil IMOWI si no figura móvil.",
            "- Si no tiene internet fijo y dice 'no tengo internet', NO es un corte: "
            "no tiene ese producto contratado. No inicies diagnóstico de Wi‑Fi ni ONT.",
            "- Si pppoe indica conectado/desconectado, usá pppoe_triage: no contradigas "
            "el dato real ni pidas reinicio de ONT si triage dice linea_ok. "
            "Si triage=sin_sesion_ppp, no pidas speedtest.",
            "- Si uisp indica CPE radio, usá uisp_triage: no contradigas el estado de la antena. "
            "CPE fuera de línea → PoE/energía; si sigue offline, visita. Señal mala (< -75 dBm) → "
            "visita para alinear/revisar antena. Enlace OK → Wi‑Fi/router.",
            "- Si bcm indica ONU/ONT, usá bcm_triage: no contradigas el estado óptico. "
            "ONU fuera de línea → luces PON/LOS; potencia mala (< -27 dBm) → cable amarillo y visita. "
            "Enlace OK → Wi‑Fi/router; NO pidas reinicio de ONT como primer paso.",
            "- Si hay plan_mbps, esa es la velocidad CONTRATADA. Un test ≥70% de ese valor "
            "es NORMAL: no digas que está 'por debajo' ni derives a técnico. "
            "«10M»/«10Mb» ES un resultado de test; no vuelvas a preguntar cuánto dio.",
        ]
    )
    return "\n".join(lines)


def facts_prompt_lines(facts: dict[str, Any]) -> list[str]:
    """Compat: subset de líneas (tests 3A). Preferir format_n1_contexto."""
    billing = facts.get("billing") or {}
    bal = billing.get("balance") or {}
    lines: list[str] = []
    if billing.get("status"):
        lines.append(f"- billing_status: {billing.get('status')}")
    if bal.get("freshness"):
        lines.append(f"- billing_freshness: {bal.get('freshness')}")
    if bal.get("as_of") is None and billing.get("status") == "stale":
        lines.append("- billing_as_of: (sin dato)")
    services = facts.get("services") or {}
    items = services.get("items") or []
    if services.get("status") == "ok" and items:
        parts = []
        for it in items[:20]:
            tip = str(it.get("type") or "other")
            lab = str(it.get("label") or it.get("product") or tip).strip()
            act = "activo" if it.get("active") else "no_activo"
            parts.append(f"{tip}:{lab}({act})")
        if parts:
            lines.append(f"- servicios_catalogo: {'; '.join(parts)}")
    elif services.get("status") == "unavailable":
        lines.append("- servicios_catalogo: (fuente no disponible)")
    return lines


def semantic_alignment_with_summary_shape(facts: dict[str, Any]) -> dict[str, Any]:
    """Proyección mínima alineada al contrato Customer Summary (sin HTTP)."""
    customer = facts.get("customer") or {}
    account = facts.get("account") or {}
    billing = facts.get("billing") or {}
    bal = billing.get("balance") or {}
    services = facts.get("services") or {}
    tickets = facts.get("tickets") or {}
    ov = facts.get("ov") or {}
    return {
        "customer": {
            "id": customer.get("id"),
            "display_name": customer.get("display_name"),
            "organization_id": customer.get("organization_id"),
        },
        "account": {
            "client_number": account.get("client_number"),
            "status": account.get("status"),
            "plan": account.get("plan"),
        },
        "billing": {
            "status": billing.get("status"),
            "balance": {
                "amount": bal.get("amount") if bal else None,
                "currency": bal.get("currency") if bal else "ARS",
                "freshness": bal.get("freshness") if bal else None,
                "as_of": bal.get("as_of") if bal else None,
            },
        },
        "services": {
            "status": services.get("status"),
            "items": [
                {
                    "id": it.get("id"),
                    "type": it.get("type"),
                    "active": it.get("active"),
                    "label": it.get("label"),
                }
                for it in (services.get("items") or [])
            ],
        },
        "tickets": {
            "status": tickets.get("status"),
            "items": [
                {
                    "id": it.get("id"),
                    "state": it.get("state"),
                    "category": it.get("category"),
                }
                for it in (tickets.get("items") or [])
            ],
        },
        "ov": {
            "available": ov.get("available"),
            "links": dict(ov.get("links") or {}),
            "auth": ov.get("auth"),
        },
    }


def internet_logins_count(db: Session | None, abonado: Any | None) -> int:
    """Cantidad de logins INT*. No selecciona."""
    if db is None or abonado is None:
        return 0
    from app.services import billtrack as bt

    dni = str(getattr(abonado, "dni", "") or "").strip()
    cn = str(getattr(abonado, "client_number", "") or "").strip()
    try:
        if cn:
            svcs = bt.lookup_servicios_conectividad(client_number=cn, db=db)
        elif dni:
            svcs = bt.lookup_servicios_conectividad_por_dni(dni=dni, db=db)
        else:
            return 0
        return len(bt.listar_logins_conectividad(svcs))
    except Exception:
        logger.exception("eko_context: internet_logins_count falló")
        return 0
