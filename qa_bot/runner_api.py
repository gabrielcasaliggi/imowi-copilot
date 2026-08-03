"""Runner API — misma lógica de producción vía /api/v1/portal/*."""

from __future__ import annotations

import time
from typing import Any

import httpx

from qa_bot.analyzer import AnalisisEscenario, analizar_escenario, analizar_turno
from qa_bot.scenarios import ESCENARIOS, Escenario

DEFAULT_BASE = "https://ibot.ecolan.com"


def _extract_bot_text(payload: dict[str, Any]) -> str:
    """Extrae la respuesta del bot desde distintas formas del payload."""
    for key in ("respuesta", "reply", "mensaje_bot", "bot_message"):
        if payload.get(key):
            return str(payload[key]).strip()

    mensajes = payload.get("mensajes") or payload.get("messages") or []
    outs: list[str] = []
    for m in mensajes:
        if not isinstance(m, dict):
            continue
        direccion = (m.get("direccion") or m.get("direction") or "").lower()
        autor = (m.get("autor") or m.get("role") or m.get("from") or "").lower()
        texto = m.get("texto") or m.get("text") or m.get("contenido") or m.get("body") or ""
        if not texto:
            continue
        if direccion in ("out", "outbound", "bot") or autor in ("bot", "asistente", "assistant"):
            outs.append(str(texto))
    if outs:
        return outs[-1].strip()

    for nest in ("result", "data", "respuesta_bot"):
        inner = payload.get(nest)
        if isinstance(inner, dict):
            t = _extract_bot_text(inner)
            if t:
                return t
        elif isinstance(inner, str) and inner.strip():
            return inner
    return ""


class PortalClient:
    def __init__(self, base_url: str = DEFAULT_BASE, timeout: float = 120.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)
        self.token: str | None = None
        self.conversacion_id: str | None = None

    def close(self) -> None:
        self.client.close()

    def guest_session(self, org_slug: str = "coop-batan") -> dict[str, Any]:
        r = self.client.post(
            f"{self.base}/api/v1/portal/session",
            json={"org_slug": org_slug},
        )
        r.raise_for_status()
        data = r.json()
        self.token = data.get("portal_token")
        conv = data.get("conversacion") or {}
        self.conversacion_id = conv.get("id") or data.get("conversacion_id")
        return data

    def send(self, texto: str) -> tuple[dict[str, Any], int]:
        assert self.token, "Sin sesión portal"
        t0 = time.perf_counter()
        r = self.client.post(
            f"{self.base}/api/v1/portal/messages",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"texto": texto},
        )
        ms = int((time.perf_counter() - t0) * 1000)
        r.raise_for_status()
        return r.json(), ms

    def conversation(self) -> dict[str, Any]:
        assert self.token and self.conversacion_id
        r = self.client.get(
            f"{self.base}/api/v1/portal/conversations/{self.conversacion_id}",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        r.raise_for_status()
        return r.json()


def run_escenario_api(esc: Escenario, base_url: str = DEFAULT_BASE) -> AnalisisEscenario:
    client = PortalClient(base_url)
    try:
        client.guest_session()
        analisis = []
        prev_respuestas: list[str] = []
        for turno in esc.turnos:
            payload, ms = client.send(turno.usuario)
            bot = _extract_bot_text(payload)
            if not bot:
                # fallback: refrescar conversación
                try:
                    conv = client.conversation()
                    bot = _extract_bot_text(conv)
                except Exception:
                    bot = ""
            a = analizar_turno(
                turno.usuario,
                bot,
                espera_autodiagnostico=turno.espera_autodiagnostico,
                espera_resolucion_directa=turno.espera_resolucion_directa,
                no_debe_ticket_prematuro=turno.no_debe_ticket_prematuro,
                ticket_aceptable=turno.ticket_aceptable,
                respuestas_previas=prev_respuestas,
                latency_ms=ms,
            )
            analisis.append(a)
            if bot:
                prev_respuestas.append(bot)
        return analizar_escenario(
            esc.id,
            esc.nombre,
            esc.categoria,
            analisis,
            resolucion_n1_esperada=esc.resolucion_n1_esperada,
        )
    finally:
        client.close()


def run_matriz_api(
    base_url: str = DEFAULT_BASE,
    scenario_ids: list[str] | None = None,
) -> list[AnalisisEscenario]:
    selected = ESCENARIOS
    if scenario_ids:
        wanted = set(scenario_ids)
        selected = [e for e in ESCENARIOS if e.id in wanted]
    results: list[AnalisisEscenario] = []
    for esc in selected:
        print(f"[API] {esc.id} — {esc.nombre}…", flush=True)
        try:
            results.append(run_escenario_api(esc, base_url))
            last = results[-1]
            print(
                f"  score={last.score_n1} resolutivo={last.resolutivo_autonomo} "
                f"ticket_prem={last.ticket_prematuro} fallas={len(last.resumen_fallas)}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {exc}", flush=True)
            results.append(
                analizar_escenario(
                    esc.id,
                    esc.nombre,
                    esc.categoria,
                    [
                        analizar_turno(
                            "(error de ejecución)",
                            f"ERROR: {exc}",
                            no_debe_ticket_prematuro=True,
                        )
                    ],
                    resolucion_n1_esperada=esc.resolucion_n1_esperada,
                )
            )
    return results
