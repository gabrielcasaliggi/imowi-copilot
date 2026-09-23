"""Eko 2.2B — resolución determinística service_id ↔ login.

LLM puede proponer referencias; la aceptación solo ocurre contra catálogo confiable.
No ejecuta probes ni EFFECT.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger("operations_hub")

SelectionStatus = Literal[
    "selected",
    "needs_input",
    "denied",
    "unavailable",
    "no_match",
]


@dataclass(frozen=True)
class ServiceRef:
    """Selección efectiva única (comercial + técnico asociado)."""

    service_id: str
    login: str
    service_type: str
    client_number: str
    label: str = ""
    product: str = ""
    active: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_id": self.service_id,
            "login": self.login,
            "service_type": self.service_type,
            "client_number": self.client_number,
            "label": self.label,
            "product": self.product,
            "active": self.active,
        }


@dataclass
class SelectionResult:
    status: SelectionStatus
    ref: ServiceRef | None = None
    reason_code: str | None = None
    message: str = ""
    options: list[dict[str, Any]] | None = None


def ref_from_row(row: dict[str, Any], *, client_number: str) -> ServiceRef:
    return ServiceRef(
        service_id=str(row.get("id") or "").strip(),
        login=str(row.get("login") or "").strip(),
        service_type=str(row.get("type") or "").strip(),
        client_number=str(client_number or "").strip(),
        label=str(row.get("label") or "").strip(),
        product=str(row.get("product") or "").strip(),
        active=bool(row.get("active")) if "active" in row else None,
    )


def option_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "service_id": str(row.get("id") or "").strip(),
        "login": str(row.get("login") or "").strip(),
        "type": str(row.get("type") or "").strip(),
        "label": str(row.get("label") or row.get("product") or "").strip(),
        "product": str(row.get("product") or "").strip(),
        "active": bool(row.get("active")),
    }


def format_selection_options(options: list[dict[str, Any]]) -> str:
    if not options:
        return "No tengo servicios para elegir en tu cuenta."
    lines = ["¿Cuál servicio querés usar? Respondé con el número:"]
    for i, opt in enumerate(options, start=1):
        name = str(opt.get("product") or opt.get("label") or opt.get("type") or "Servicio")
        tip = str(opt.get("type") or "")
        prefix = f"{tip}: " if tip and tip.lower() not in name.lower() else ""
        lines.append(f"{i}) {prefix}{name}")
    return "\n".join(lines)


def _normalize_options(raw: list[Any] | None) -> list[dict[str, Any]]:
    """Acepta opciones estructuradas o logins legacy (str)."""
    out: list[dict[str, Any]] = []
    for item in raw or []:
        if isinstance(item, dict):
            sid = str(item.get("service_id") or item.get("id") or "").strip()
            login = str(item.get("login") or "").strip()
            if not sid and not login:
                continue
            out.append(
                {
                    "service_id": sid,
                    "login": login,
                    "type": str(item.get("type") or "").strip(),
                    "label": str(item.get("label") or item.get("product") or "").strip(),
                    "product": str(item.get("product") or "").strip(),
                    "active": bool(item.get("active", True)),
                }
            )
        else:
            login = str(item or "").strip()
            if login:
                out.append(
                    {
                        "service_id": "",
                        "login": login,
                        "type": "",
                        "label": login,
                        "product": "",
                        "active": True,
                    }
                )
    return out


def _ordinal_index(texto: str) -> int | None:
    t = (texto or "").lower().strip()
    # Solo dígito / "el N"
    m = re.fullmatch(r"(?:el\s+|la\s+)?(\d{1,2})", t)
    if m:
        n = int(m.group(1))
        if n >= 1:
            return n - 1
    mapping = (
        (("primer", "primero", "primera", "uno"), 0),
        (("segund", "segundo", "segunda", "dos"), 1),
        (("tercer", "tercero", "tercera", "tres"), 2),
        (("cuart", "cuarto", "cuarta", "cuatro"), 3),
    )
    for keys, idx in mapping:
        if any(k in t for k in keys):
            return idx
    return None


def _extract_service_id(texto: str) -> str:
    t = (texto or "").strip()
    # UUID-like or numeric id explícito
    m = re.search(
        r"(?:service[_ ]?id|id)\s*[:=]?\s*([A-Za-z0-9-]{2,64})",
        t,
        re.I,
    )
    if m:
        return m.group(1).strip()
    # bare longish token that looks like an id (not INT login)
    m2 = re.fullmatch(r"[0-9]{4,}|[a-f0-9-]{8,}", t.strip(), re.I)
    if m2 and not t.upper().startswith("INT"):
        return t.strip()
    return ""


def _extract_login(texto: str) -> str:
    # Excluye la palabra "internet"; logins reales INT* (INTA, INT123, …).
    m = re.search(r"\b(INT(?!ERNET)[\w.-]+)\b", texto or "", re.I)
    if m:
        return m.group(1)
    return ""


def _natural_matches(texto: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    t = (texto or "").lower().strip()
    if not t:
        return []
    hits: list[dict[str, Any]] = []

    type_hints = (
        (("sensa", "tv", "tele", "iptv"), "tv"),
        (("imowi", "imovi", "móvil", "movil", "celular", "línea móvil", "linea movil"), "movil"),
        (("fibra", "internet", "wifi", "pppoe", "intfo", "megas", "mb"), "internet"),
        (("teléfono", "telefono", "voip", "fija"), "telefonia"),
    )
    want_types: set[str] = set()
    for keys, tip in type_hints:
        if any(k in t for k in keys):
            want_types.add(tip)

    # megas / velocidad en texto
    megas = re.search(r"(\d+)\s*megas?", t)
    speed = megas.group(1) if megas else ""

    for row in rows:
        blob = " ".join(
            [
                str(row.get("product") or ""),
                str(row.get("label") or ""),
                str(row.get("type") or ""),
                str(row.get("login") or ""),
                str(row.get("line_msisdn") or ""),
            ]
        ).lower()
        tip = str(row.get("type") or "")
        score = 0
        if want_types and tip in want_types:
            score += 2
        if speed and speed in blob:
            score += 3
        # substring product/label
        prod = str(row.get("product") or "").lower()
        lab = str(row.get("label") or "").lower()
        if prod and prod in t:
            score += 4
        if lab and lab in t:
            score += 3
        if tip == "tv" and "sensa" in t:
            score += 2
        if tip == "movil" and any(k in t for k in ("imowi", "móvil", "movil", "celular")):
            score += 2
        if tip == "internet" and any(k in t for k in ("internet", "fibra", "megas")):
            score += 1
        if score > 0:
            hits.append(row)

    if not hits and want_types:
        hits = [r for r in rows if str(r.get("type") or "") in want_types]
    return hits


def _normalize_ref_text(texto: str) -> str:
    t = (texto or "").lower().strip()
    t = re.sub(r"[¿?¡!.,;:]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _is_fijo_reference(texto: str) -> bool:
    """2.5D-2: referencia acotada a fijo/fija (no NLP general)."""
    t = _normalize_ref_text(texto)
    if not t:
        return False
    if t in ("el fijo", "la fija", "fijo", "fija", "al fijo", "a la fija", "del fijo", "de la fija"):
        return True
    return bool(re.search(r"\b(?:el\s+|la\s+|al\s+|del\s+|de\s+la\s+)?fij[oa]\b", t))


def _is_otro_reference(texto: str) -> bool:
    """2.5D-2: referencia relativa 'el otro' / 'la otra' (no 'otra vez')."""
    t = _normalize_ref_text(texto)
    if not t:
        return False
    if re.search(r"\botra\s+vez\b", t) or re.search(r"\botro\s+d[ií]a\b", t):
        return False
    if t in ("el otro", "la otra", "otro", "otra", "al otro", "a la otra"):
        return True
    return bool(
        re.search(
            r"\b(?:me\s+refiero\s+(?:a|al)\s+)?(?:el\s+otro|la\s+otra|al\s+otro)\b",
            t,
        )
    )


def _row_matches_ref(row: dict[str, Any], ref: ServiceRef) -> bool:
    sid = str(row.get("id") or "").strip()
    login = str(row.get("login") or "").strip().lower()
    if ref.service_id and sid and sid == ref.service_id:
        return True
    if ref.login and login and login == ref.login.lower():
        return True
    return False


def _fijo_phone_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in rows if str(r.get("type") or "").strip().lower() == "telefonia"]


def _fijo_internet_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Internet fijo = type internet (móvil es type movil, no entra)."""
    return [r for r in rows if str(r.get("type") or "").strip().lower() == "internet"]


def resolve_fijo_reference(
    *,
    texto: str,
    catalog: list[dict[str, Any]],
    client_number: str,
) -> SelectionResult:
    """2.5D-2: 'el fijo' / 'la fija' → un candidato inequívoco o NEEDS_INPUT."""
    cn = str(client_number or "").strip()
    rows = [r for r in catalog if isinstance(r, dict) and str(r.get("id") or "").strip()]
    phone = _fijo_phone_rows(rows)
    inet = _fijo_internet_rows(rows)

    if len(phone) == 1 and len(inet) == 0:
        return SelectionResult(
            status="selected",
            ref=ref_from_row(phone[0], client_number=cn),
            reason_code="fijo_unique_telefonia",
        )
    if len(inet) == 1 and len(phone) == 0:
        return SelectionResult(
            status="selected",
            ref=ref_from_row(inet[0], client_number=cn),
            reason_code="fijo_unique_internet",
        )
    # Ambiguity: phone + internet, or multiple of either, or none
    candidates = phone + inet
    if not candidates:
        return SelectionResult(
            status="needs_input",
            reason_code="fijo_no_compatible",
            message="No encuentro un servicio fijo (telefonía o Internet) en tu cuenta.",
            options=[option_from_row(r) for r in rows],
        )
    options = [option_from_row(r) for r in candidates]
    return SelectionResult(
        status="needs_input",
        reason_code="fijo_ambiguous",
        message=format_selection_options(options),
        options=options,
    )


def resolve_otro_reference(
    *,
    texto: str,
    catalog: list[dict[str, Any]],
    client_number: str,
    current_ref: ServiceRef | None,
) -> SelectionResult:
    """2.5D-2: 'el otro' relativo a selected_service_ref canónico."""
    cn = str(client_number or "").strip()
    rows = [r for r in catalog if isinstance(r, dict) and str(r.get("id") or "").strip()]
    if current_ref is None:
        return SelectionResult(
            status="needs_input",
            reason_code="otro_missing_current",
            message=format_selection_options([option_from_row(r) for r in rows]),
            options=[option_from_row(r) for r in rows],
        )
    in_catalog = [r for r in rows if _row_matches_ref(r, current_ref)]
    if not in_catalog:
        return SelectionResult(
            status="needs_input",
            reason_code="otro_current_not_in_catalog",
            message=format_selection_options([option_from_row(r) for r in rows]),
            options=[option_from_row(r) for r in rows],
        )
    others = [r for r in rows if not _row_matches_ref(r, current_ref)]
    if len(others) == 1:
        return SelectionResult(
            status="selected",
            ref=ref_from_row(others[0], client_number=cn),
            reason_code="otro_unique_alternate",
        )
    if not others:
        return SelectionResult(
            status="needs_input",
            reason_code="otro_no_alternate",
            message="Solo veo un servicio seleccionado; no hay «otro» para elegir.",
            options=[option_from_row(r) for r in rows],
        )
    options = [option_from_row(r) for r in others]
    return SelectionResult(
        status="needs_input",
        reason_code="otro_ambiguous",
        message=format_selection_options(options),
        options=options,
    )


def resolve_service_reference(
    *,
    texto: str,
    catalog: list[dict[str, Any]],
    client_number: str,
    current_ref: ServiceRef | None = None,
    pending_options: list[Any] | None = None,
    proposed_service_id: str = "",
    proposed_login: str = "",
) -> SelectionResult:
    """2.5D-2 alias: same contract as :func:`resolve_service_selection`."""
    return resolve_service_selection(
        texto=texto,
        catalog=catalog,
        client_number=client_number,
        current_ref=current_ref,
        pending_options=pending_options,
        proposed_service_id=proposed_service_id,
        proposed_login=proposed_login,
    )


def resolve_service_selection(
    *,
    texto: str,
    catalog: list[dict[str, Any]],
    client_number: str,
    pending_options: list[Any] | None = None,
    proposed_service_id: str = "",
    proposed_login: str = "",
    current_ref: ServiceRef | None = None,
) -> SelectionResult:
    """Resuelve una referencia a exactamente un servicio del catálogo confiable."""
    cn = str(client_number or "").strip()
    if not cn:
        return SelectionResult(
            status="needs_input",
            reason_code="missing_client_number",
            message="No tengo el número de cuenta para seleccionar un servicio.",
        )
    rows = [r for r in catalog if isinstance(r, dict) and str(r.get("id") or "").strip()]
    if not rows:
        return SelectionResult(
            status="no_match",
            reason_code="empty_catalog",
            message="No encuentro servicios en tu cuenta para seleccionar.",
        )

    opts = _normalize_options(pending_options)

    # 1) Propuesta explícita (p.ej. LLM) — solo si está en catálogo
    sid_prop = str(proposed_service_id or "").strip()
    login_prop = str(proposed_login or "").strip()

    # 2) Extraer del texto
    sid_txt = _extract_service_id(texto)
    login_txt = _extract_login(texto)
    sid = sid_prop or sid_txt
    login = login_prop or login_txt

    if sid:
        matches = [r for r in rows if str(r.get("id") or "").strip() == sid]
        if len(matches) == 1:
            return SelectionResult(
                status="selected",
                ref=ref_from_row(matches[0], client_number=cn),
            )
        return SelectionResult(
            status="denied",
            reason_code="foreign_or_unknown_service_id",
            message="Ese servicio no pertenece a tu cuenta.",
        )

    if login:
        matches = [
            r
            for r in rows
            if str(r.get("login") or "").strip().lower() == login.lower()
        ]
        if len(matches) == 1:
            return SelectionResult(
                status="selected",
                ref=ref_from_row(matches[0], client_number=cn),
            )
        # Login legacy options (connectivity) may only have login string
        if opts:
            opt_hits = [
                o
                for o in opts
                if str(o.get("login") or "").strip().lower() == login.lower()
            ]
            if len(opt_hits) == 1 and opt_hits[0].get("service_id"):
                sid_o = opt_hits[0]["service_id"]
                matches2 = [r for r in rows if str(r.get("id") or "") == sid_o]
                if len(matches2) == 1:
                    return SelectionResult(
                        status="selected",
                        ref=ref_from_row(matches2[0], client_number=cn),
                    )
            if len(opt_hits) == 1 and not opt_hits[0].get("service_id"):
                # Login-only option (connectivity path): accept login if in catalog
                pass
        return SelectionResult(
            status="denied",
            reason_code="foreign_or_unknown_login",
            message="Esa cuenta de Internet no está en tus servicios.",
        )

    # 3) Ordinal contra opciones pendientes (o catálogo completo)
    ordinal = _ordinal_index(texto)
    pool = opts if opts else [option_from_row(r) for r in rows]
    if ordinal is not None:
        if 0 <= ordinal < len(pool):
            chosen = pool[ordinal]
            sid_c = str(chosen.get("service_id") or "").strip()
            login_c = str(chosen.get("login") or "").strip()
            if sid_c:
                matches = [r for r in rows if str(r.get("id") or "") == sid_c]
            elif login_c:
                matches = [
                    r
                    for r in rows
                    if str(r.get("login") or "").lower() == login_c.lower()
                ]
            else:
                matches = []
            if len(matches) == 1:
                return SelectionResult(
                    status="selected",
                    ref=ref_from_row(matches[0], client_number=cn),
                )
            if len(matches) == 0 and login_c and not sid_c:
                # Conectividad: opción era solo login y está en catálogo selection
                return SelectionResult(
                    status="denied",
                    reason_code="unresolved_option",
                    message="No pude asociar esa opción a un servicio de tu cuenta.",
                )
        return SelectionResult(
            status="needs_input",
            reason_code="invalid_option_index",
            message=format_selection_options(pool),
            options=pool,
        )

    # 4) Un solo servicio en catálogo + referencia genérica ("ese", "el servicio")
    #    NO ampliar a "fijo"/"otro" aquí — van en 4b/4c (2.5D-2).
    t_low = _normalize_ref_text(texto)
    if len(rows) == 1 and (
        not t_low
        or t_low in ("ese", "esa", "ese servicio", "el servicio", "ese mismo", "ok", "dale")
        or "único" in t_low
        or "unico" in t_low
    ):
        return SelectionResult(
            status="selected",
            ref=ref_from_row(rows[0], client_number=cn),
        )

    # 4b) Relative "el otro" — requires canonical current_ref (2.5D-2)
    if _is_otro_reference(texto):
        return resolve_otro_reference(
            texto=texto,
            catalog=rows,
            client_number=cn,
            current_ref=current_ref,
        )

    # 4c) "el fijo" / "la fija" (2.5D-2) — before generic natural match
    if _is_fijo_reference(texto):
        return resolve_fijo_reference(
            texto=texto,
            catalog=rows,
            client_number=cn,
        )

    # 5) Lenguaje natural
    nat = _natural_matches(texto, rows)
    if len(nat) == 1:
        return SelectionResult(
            status="selected",
            ref=ref_from_row(nat[0], client_number=cn),
        )
    if len(nat) > 1:
        options = [option_from_row(r) for r in nat]
        return SelectionResult(
            status="needs_input",
            reason_code="ambiguous_reference",
            message=format_selection_options(options),
            options=options,
        )

    # 6) Sin referencia útil: multi → NEEDS_INPUT; no auto-elegir tras fallo
    options = [option_from_row(r) for r in rows]
    return SelectionResult(
        status="needs_input",
        reason_code="service_selection_required",
        message=format_selection_options(options),
        options=options,
    )


def selection_changed(prev: ServiceRef | None, new: ServiceRef) -> bool:
    if prev is None:
        return False
    if prev.service_id and new.service_id:
        return prev.service_id != new.service_id
    if prev.login or new.login:
        return (prev.login or "").lower() != (new.login or "").lower()
    return prev.service_id != new.service_id


def get_selected_ref(ctx: dict[str, Any] | None) -> ServiceRef | None:
    """2.5D-1 — canonical READ SoT for the currently selected service.

    Reads **only** ``eko_journey.selected_service_ref``.

    Does **not** fall back to ``selected_service`` or ``ctx.login_seleccionado``
    (those remain write-side projections / legacy shadow only).

    Pure read: no inference, no catalog lookup, no LLM, no state mutation.
    """
    st_raw = (ctx or {}).get("eko_journey")
    st = dict(st_raw) if isinstance(st_raw, dict) else {}
    raw = st.get("selected_service_ref")
    if isinstance(raw, dict) and (
        str(raw.get("service_id") or "").strip() or str(raw.get("login") or "").strip()
    ):
        return ServiceRef(
            service_id=str(raw.get("service_id") or "").strip(),
            login=str(raw.get("login") or "").strip(),
            service_type=str(raw.get("service_type") or "").strip(),
            client_number=str(raw.get("client_number") or "").strip(),
            label=str(raw.get("label") or "").strip(),
            product=str(raw.get("product") or "").strip(),
            active=raw.get("active") if isinstance(raw.get("active"), bool) else None,
        )
    return None


def get_selected_service_ref(ctx: dict[str, Any] | None) -> ServiceRef | None:
    """Alias canónico 2.5D-1 de :func:`get_selected_ref`."""
    return get_selected_ref(ctx)


_NON_DIAGNOSTICABLE_TYPES = frozenset(
    {
        "tv",
        "sensa",
        "movil",
        "móvil",
        "telefonia",
        "telefonía",
        "voip",
        "telefono",
        "teléfono",
    }
)


def is_fixed_internet_diagnosticable(ref: ServiceRef | None) -> bool:
    """Internet fijo con login técnico — única capacidad de diagnóstico conocida.

    No inventa probes para Sensa/IMOWI/VoIP. No asume probes por type==internet
    sin login.
    """
    if ref is None:
        return False
    tip = (ref.service_type or "").strip().lower()
    if tip in _NON_DIAGNOSTICABLE_TYPES:
        return False
    login = (ref.login or "").strip()
    if not login:
        return False
    if tip and tip not in ("internet", "fibra", "radio", "adsl", ""):
        return False
    return True


def ownership_matches_ref(ref: ServiceRef | None, client_number: str) -> bool:
    """True si el ref no declara CN ajeno. CN vacío en ref = legado (solo login)."""
    cn = str(client_number or "").strip()
    if not cn or ref is None:
        return False
    ref_cn = str(ref.client_number or "").strip()
    if ref_cn and ref_cn != cn:
        return False
    return True


def looks_like_selection_utterance(texto: str) -> bool:
    t = (texto or "").lower().strip()
    if not t:
        return False
    if re.fullmatch(r"(?:el\s+|la\s+)?\d{1,2}", t):
        return True
    if re.search(r"\bINT(?!ERNET)[\w.-]+\b", t, re.I):
        return True
    if t in (
        "ese",
        "esa",
        "ese servicio",
        "el servicio",
        "ese mismo",
        "el único",
        "el unico",
    ):
        return True
    # 2.5D-2 reference phrases (same selection path; does not change "ese" rules)
    if _is_fijo_reference(texto) or _is_otro_reference(texto):
        return True
    if any(
        k in t
        for k in (
            "el de ",
            "la de ",
            "megas",
            "sensa",
            "imowi",
            "imovi",
            "la fibra",
            "el internet",
            "mi internet",
            "la línea",
            "la linea",
            "el móvil",
            "el movil",
            "quiero el",
            "quiero la",
            "revisar el",
            "revisá el",
            "revisa el",
            "el primero",
            "el segundo",
            "el tercero",
            "ese servicio",
            "seleccion",
            "selección",
            "elegir",
        )
    ):
        return True
    return False
