"""Loop QA — cliente corporativo Ecolan B2B (preguntar, escuchar, aprender, repregunta).

Personas con hechos ocultos. Mide N2 evitables (cotización / VPN un usuario)
vs. legítimos (enlace sede / VM DC con impacto).

Uso:

    .venv/bin/python -m qa_bot.cliente_corporativo
    .venv/bin/python -m qa_bot.cliente_corporativo --personas C01,C03
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


@dataclass
class HechosCorp:
    tipo: str = ""  # cotizacion | vpn | enlace | vm
    alcance: str = ""  # un_usuario | sede | todos
    impacto: str = ""  # cotizacion | caido
    hotspot_ok: bool | None = None
    cpe_reinicio: bool = False
    apertura: str = ""


@dataclass
class PersonaCorp:
    id: str
    nombre: str
    descripcion: str
    hechos: HechosCorp
    n2_esperado: str  # nunca | legitimo
    max_turnos: int = 10
    dni: str = "26444555"  # Pedro Ecolan — internet demo


@dataclass
class TurnoLoop:
    usuario: str
    respuesta: str
    estado: str = ""
    ticket_id: str = ""
    intencion: str = ""


@dataclass
class ResultadoPersona:
    persona_id: str
    nombre: str
    n2_esperado: str
    ticket_creado: bool
    ticket_id: str
    estado_final: str
    intencion_final: str
    turnos: int
    n2_evitable: bool
    n2_legitimo: bool
    ok: bool
    fallas: list[str] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)


PERSONAS: list[PersonaCorp] = [
    PersonaCorp(
        id="C01",
        nombre="Cotización enlace",
        descripcion="Quiere precio de enlace dedicado; no hay caída. Sin N2 técnico.",
        n2_esperado="nunca",
        hechos=HechosCorp(
            tipo="cotizacion",
            alcance="sede",
            impacto="cotizacion",
            apertura="Hola, necesito una cotización de enlace dedicado Ecolan para una sucursal",
        ),
    ),
    PersonaCorp(
        id="C02",
        nombre="VPN un usuario",
        descripcion="VPN falla a un usuario; hotspot OK. N1, no planta.",
        n2_esperado="nunca",
        hechos=HechosCorp(
            tipo="vpn",
            alcance="un_usuario",
            impacto="caido",
            hotspot_ok=True,
            apertura="No me conecta la VPN de la sucursal Ecolan, solo a mí",
        ),
    ),
    PersonaCorp(
        id="C03",
        nombre="Enlace sede caída",
        descripcion="Enlace dedicado caído en toda la sede. N2 Ecolan legítimo.",
        n2_esperado="legitimo",
        max_turnos=12,
        hechos=HechosCorp(
            tipo="enlace",
            alcance="sede",
            impacto="caido",
            hotspot_ok=True,
            cpe_reinicio=True,
            apertura="Se nos cayó el enlace dedicado de la sucursal, no hay internet en toda la oficina",
        ),
    ),
    PersonaCorp(
        id="C04",
        nombre="VM DC impacto",
        descripcion="VM en datacenter caída, impacto productivo. N2 legítimo.",
        n2_esperado="legitimo",
        hechos=HechosCorp(
            tipo="vm",
            alcance="todos",
            impacto="caido",
            apertura="Tenemos una VM en el data center de Ecolan que no responde, impacto productivo",
        ),
    ),
]


def responder_como_cliente(
    pregunta_bot: str,
    persona: PersonaCorp,
    *,
    turno: int,
    ya_dijo_apertura: bool,
    ticket_ya: bool,
) -> str | None:
    if ticket_ya:
        return None
    if not ya_dijo_apertura:
        return persona.hechos.apertura

    h = persona.hechos
    q = (pregunta_bot or "").lower()

    # Orden: impacto / alcance / prueba / derivación antes que "tipo"
    # (la pregunta de impacto menciona "cotización" y no debe matchear tipo).
    if any(k in q for k in ("caído ahora", "caido ahora", "impacto", "sin urgencia", "urgencia", "operativo")):
        if h.impacto == "cotizacion":
            return "Es solo cotización, no hay urgencia ni caída"
        return "Sí, está caído ahora y hay impacto operativo"

    if any(k in q for k in ("usuario", "sede", "sucursal", "todos", "alcance", "sitios")) and (
        "afecta" in q or "alcance" in q or "sitios" in q or "solo" in q
    ):
        if h.alcance == "un_usuario":
            return "Solo a un usuario, el resto anda"
        if h.alcance == "sede":
            return "A toda la sede / sucursal"
        if h.alcance == "todos":
            return "Afecta el servicio en producción"
        return "Una sede"

    if any(k in q for k in ("hotspot", "otro enlace", "reiniciar", "cpe", "probaste")):
        if h.tipo == "vpn" and h.hotspot_ok:
            return (
                "Desde el hotspot del celular la VPN ya funciona; "
                "solo falla en mi PC, el resto de la oficina anda"
            )
        if h.tipo == "enlace":
            return "Reinicié el CPE y sigue caído en toda la oficina; por hotspot celular sí salgo"
        if h.tipo == "vm":
            return "No es tema de WiFi de casa, es la VM en el DC"
        return "Ya probé y sigue igual"

    if any(k in q for k in ("agente", "deriv", "ticket", "especialista", "comercial", "te derivo")):
        if persona.n2_esperado == "legitimo" and turno >= 2:
            return "Sí, derivame con Ecolan por favor"
        if h.impacto == "cotizacion":
            return "No abras ticket técnico; pasame contacto comercial si podés"
        return "Prefiero seguir acá un poco más"

    if any(
        k in q
        for k in (
            "¿es pbx",
            "es pbx",
            "cloud/vm",
            "housing",
            "vpn de sucursal",
            "cotización/consulta",
            "cotizacion/consulta",
            "tipo",
        )
    ) or ("pbx" in q and "enlace" in q):
        if h.tipo == "cotizacion":
            return "Es una cotización de enlace dedicado, no hay nada caído"
        if h.tipo == "vpn":
            return "Es la VPN de sucursal"
        if h.tipo == "enlace":
            return "Enlace dedicado / IP fija de la sede"
        if h.tipo == "vm":
            return "Cloud / VM en el datacenter"
        return "Enlace dedicado"

    if any(k in q for k in ("internet", "móvil", "movil", "factura", "en qué te", "en que te")):
        return "Es un tema Ecolan B2B / empresa"

    if h.tipo == "cotizacion":
        return "Solo necesito presupuesto del enlace"
    if h.tipo == "vpn":
        return "Solo me pasa a mí con la VPN"
    if h.tipo == "enlace":
        return "Toda la oficina sin el enlace dedicado"
    return "Sigue el problema en el datacenter"


def _identificar_portal(client: Any, dni: str) -> str:
    from qa_bot.cliente_hogareno import _reset_hilo_n1

    start = client.post(
        "/api/v1/portal/auth/start",
        json={"dni": dni, "org_slug": "coop-batan"},
    )
    start.raise_for_status()
    body = start.json()
    otp = body.get("debug_otp")
    if not otp:
        raise RuntimeError("Sin debug_otp: requiere APP_ENV=development")
    verify = client.post(
        "/api/v1/portal/auth/verify",
        json={
            "challenge_id": body["challenge_id"],
            "otp": otp,
            "org_slug": "coop-batan",
        },
    )
    verify.raise_for_status()
    data = verify.json()
    _reset_hilo_n1(data["conversacion"]["id"])
    return data["portal_token"]


def _enviar(client: Any, token: str, texto: str) -> dict[str, Any]:
    r = client.post(
        "/api/v1/portal/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"texto": texto},
    )
    r.raise_for_status()
    return r.json()


def _ticket_en_payload(payload: dict[str, Any]) -> str:
    tid = str(payload.get("ticket_id") or "").strip()
    if tid:
        return tid
    estado = str(payload.get("estado") or "")
    modo = str(payload.get("modo") or "")
    if estado in ("espera_agente", "con_agente") or modo == "espera_agente":
        return "cola"
    return ""


def evaluar_resultado(persona: PersonaCorp, turnos: list[TurnoLoop]) -> ResultadoPersona:
    ticket_id = next((t.ticket_id for t in turnos if t.ticket_id), "")
    ticket = bool(ticket_id)
    estado = turnos[-1].estado if turnos else ""
    intent = ""
    for t in reversed(turnos):
        if t.intencion:
            intent = t.intencion
            break
    fallas: list[str] = []
    n2_evitable = False
    n2_legitimo = False
    turno_ticket = next((i for i, t in enumerate(turnos) if t.ticket_id), None)

    if persona.n2_esperado == "nunca":
        if ticket:
            n2_evitable = True
            fallas.append("N2 evitable: cotización/VPN un usuario no debía abrir ticket técnico")
    elif persona.n2_esperado == "legitimo":
        if ticket:
            n2_legitimo = True
            if turno_ticket is not None and turno_ticket == 0:
                n2_evitable = True
                n2_legitimo = False
                fallas.append("N2 en el primer turno (prematuro)")
        elif len(turnos) >= persona.max_turnos:
            fallas.append("No ofreció handoff Ecolan al agotar turnos")

    ok = not n2_evitable and not fallas
    if persona.n2_esperado == "legitimo" and ticket and not n2_evitable:
        ok = True
        fallas = [f for f in fallas if "handoff" not in f]

    transcript = []
    for t in turnos:
        transcript.append({"rol": "usuario", "texto": t.usuario})
        transcript.append({"rol": "bot", "texto": t.respuesta, "estado": t.estado})

    return ResultadoPersona(
        persona_id=persona.id,
        nombre=persona.nombre,
        n2_esperado=persona.n2_esperado,
        ticket_creado=ticket,
        ticket_id=ticket_id,
        estado_final=estado,
        intencion_final=intent,
        turnos=len(turnos),
        n2_evitable=n2_evitable,
        n2_legitimo=n2_legitimo,
        ok=ok,
        fallas=fallas,
        transcript=transcript,
    )


def run_persona(client: Any, persona: PersonaCorp, *, usar_llama: bool = False) -> ResultadoPersona:
    from app.domain.flujos_abonado import PLAYBOOKS

    with (
        patch("app.api.v1.portal.resolve_canal_usar_llama", return_value=usar_llama),
        patch("app.services.canal_abonado.playbooks_as_pasos", return_value=PLAYBOOKS),
    ):
        token = _identificar_portal(client, persona.dni)
        turnos: list[TurnoLoop] = []
        last_bot = ""
        dijo_apertura = False
        ticket = ""

        for i in range(persona.max_turnos):
            msg = responder_como_cliente(
                last_bot,
                persona,
                turno=i,
                ya_dijo_apertura=dijo_apertura,
                ticket_ya=bool(ticket),
            )
            if not msg:
                break
            dijo_apertura = True
            payload = _enviar(client, token, msg)
            bot = str(payload.get("respuesta") or payload.get("reply") or "").strip()
            ticket = ticket or _ticket_en_payload(payload)
            t = TurnoLoop(
                usuario=msg,
                respuesta=bot,
                estado=str(payload.get("estado") or ""),
                ticket_id=ticket,
                intencion=str(payload.get("intencion") or ""),
            )
            turnos.append(t)
            last_bot = bot
            if t.ticket_id:
                break
            if t.estado in ("espera_agente", "con_agente", "cerrado"):
                break
        return evaluar_resultado(persona, turnos)


def run_loop(
    *,
    ids: list[str] | None = None,
    client: Any | None = None,
) -> list[ResultadoPersona]:
    os.environ.pop("BILLTRACK_DATABASE_URL", None)

    selected = PERSONAS
    if ids:
        wanted = set(ids)
        selected = [p for p in PERSONAS if p.id in wanted]
    own_client = client is None
    if own_client:
        os.environ.setdefault("APP_ENV", "development")
        os.environ.setdefault("DISABLE_DEMO_USERS", "false")
        from fastapi.testclient import TestClient

        from main import app

        client = TestClient(app)
    results: list[ResultadoPersona] = []
    try:
        for p in selected:
            print(f"[CORP] {p.id} — {p.nombre}…", flush=True)
            r = run_persona(client, p)
            results.append(r)
            flag = "OK" if r.ok else "FAIL"
            print(
                f"  {flag} n2={r.ticket_creado} evitable={r.n2_evitable} "
                f"legitimo={r.n2_legitimo} intent={r.intencion_final} "
                f"fallas={r.fallas}",
                flush=True,
            )
    finally:
        if own_client and hasattr(client, "close"):
            try:
                client.close()
            except Exception:
                pass
    return results


def resumen(results: list[ResultadoPersona]) -> dict[str, Any]:
    total = len(results) or 1
    return {
        "personas": len(results),
        "ok": sum(1 for r in results if r.ok),
        "n2_evitables": sum(1 for r in results if r.n2_evitable),
        "n2_legitimos": sum(1 for r in results if r.n2_legitimo),
        "tasa_ok": round(sum(1 for r in results if r.ok) / total, 3),
        "detalle": [asdict(r) for r in results],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Loop QA cliente corporativo Ecolan")
    parser.add_argument("--personas", default="", help="IDs C01,C02,…")
    args = parser.parse_args(argv)
    ids = [s.strip() for s in args.personas.split(",") if s.strip()] or None
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    results = run_loop(ids=ids)
    payload = resumen(results)
    out = ARTIFACTS / "resultados_corporativo.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nJSON: {out}", flush=True)
    print(
        f"ok={payload['ok']}/{payload['personas']} "
        f"n2_evitables={payload['n2_evitables']} n2_legitimos={payload['n2_legitimos']}",
        flush=True,
    )
    return 0 if payload["n2_evitables"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
