"""Runner Playwright — ingreso portal como Invitado + chat UI."""

from __future__ import annotations

import re
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from qa_bot.analyzer import AnalisisEscenario, analizar_escenario, analizar_turno
from qa_bot.scenarios import ESCENARIOS, Escenario

DEFAULT_PORTAL = "https://ibot.ecolan.com/portal"
ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def _login_guest(page: Page) -> None:
    page.goto(DEFAULT_PORTAL, wait_until="domcontentloaded", timeout=60_000)
    btn = page.get_by_role(
        "button", name=re.compile(r"Continuar como invitado", re.I)
    )
    btn.click()
    page.get_by_placeholder(re.compile(r"Escribí tu consulta|Tu mensaje|consulta", re.I)).wait_for(
        state="visible", timeout=60_000
    )
    # Esperar saludo del bot
    page.wait_for_timeout(800)


def _logout(page: Page) -> None:
    salir = page.get_by_role("button", name=re.compile(r"Salir", re.I))
    if salir.count():
        salir.first.click()
        page.wait_for_timeout(600)


def _collect_bot_bubbles(page: Page) -> list[str]:
    """Heurística: textos visibles del chat que no son el input."""
    # Prefer data attributes if present
    for sel in [
        "[data-role='bot']",
        "[data-autor='bot']",
        ".msg-bot",
        ".message-bot",
        "[class*='bot']",
    ]:
        nodes = page.locator(sel)
        if nodes.count() > 0:
            texts = [n.inner_text().strip() for n in nodes.all() if n.inner_text().strip()]
            if texts:
                return texts

    # Fallback: body text parse is fragile; use accessibility-ish scan
    body = page.inner_text("body")
    return [body]


def _last_bot_reply(page: Page, previous: set[str], user_text: str) -> str:
    """Espera una nueva respuesta del bot distinta a las previas."""
    input_box = page.get_by_placeholder(
        re.compile(r"Escribí tu consulta|Tu mensaje|consulta|Esperá", re.I)
    )
    # Esperar a que deje de estar "Enviando" / readonly
    deadline = time.time() + 120
    last_seen = ""
    while time.time() < deadline:
        # input habilitado suele indicar respuesta lista
        ph = ""
        try:
            ph = input_box.get_attribute("placeholder") or ""
        except Exception:
            pass
        busy = "Esperá" in ph or "armando" in (page.inner_text("body").lower())
        if not busy:
            # tomar el texto más reciente que parezca respuesta bot
            body = page.inner_text("body")
            # Particionar por líneas/bloques conocidos
            candidates = []
            for block in re.split(r"\n{2,}", body):
                b = block.strip()
                if not b or b == user_text:
                    continue
                if b in previous:
                    continue
                if "Modo invitado" in b or "Soporte Batán" in b or "Soporte batan" in b:
                    continue
                if b.startswith("Tu mensaje") or "Escribí tu consulta" in b:
                    continue
                if "Cooperativa Batán" in b:
                    continue
                if len(b) < 20:
                    continue
                candidates.append(b)
            if candidates:
                # La última candidata sustancial suele ser la respuesta
                last_seen = candidates[-1]
                # A veces el bloque incluye user+bot; tomar última oración larga
                if user_text in last_seen:
                    parts = last_seen.split(user_text)
                    last_seen = parts[-1].strip()
                if last_seen and last_seen not in previous and len(last_seen) > 15:
                    return last_seen
        page.wait_for_timeout(500)
    return last_seen or "(sin respuesta / timeout)"


def _send_message(page: Page, texto: str) -> None:
    box = page.get_by_role("textbox", name=re.compile(r"Tu mensaje|mensaje", re.I))
    if not box.count():
        box = page.get_by_placeholder(re.compile(r"Escribí|consulta|mensaje", re.I))
    box.fill(texto)
    page.get_by_role("button", name=re.compile(r"Enviar", re.I)).click()


def run_escenario_playwright(
    page: Page,
    esc: Escenario,
    *,
    screenshot_dir: Path | None = None,
) -> AnalisisEscenario:
    _logout(page)
    _login_guest(page)
    if screenshot_dir:
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot_dir / f"{esc.id}_guest.png"), full_page=True)

    analisis = []
    prev_respuestas: list[str] = []
    known: set[str] = set()
    # Capturar saludo inicial para no confundirlo
    try:
        body0 = page.inner_text("body")
        for line in body0.splitlines():
            if "modo invitado" in line.lower() or "¿en qué podemos ayudarte" in line.lower():
                known.add(line.strip())
                prev_respuestas.append(line.strip())
    except Exception:
        pass

    for i, turno in enumerate(esc.turnos, 1):
        t0 = time.perf_counter()
        _send_message(page, turno.usuario)
        bot = _last_bot_reply(page, known, turno.usuario)
        ms = int((time.perf_counter() - t0) * 1000)
        known.add(bot)
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
        if screenshot_dir and i == len(esc.turnos):
            page.screenshot(path=str(screenshot_dir / f"{esc.id}_final.png"), full_page=True)

    return analizar_escenario(
        esc.id,
        esc.nombre,
        esc.categoria,
        analisis,
        resolucion_n1_esperada=esc.resolucion_n1_esperada,
    )


def run_matriz_playwright(
    scenario_ids: list[str] | None = None,
    headless: bool = True,
) -> list[AnalisisEscenario]:
    selected = ESCENARIOS
    if scenario_ids:
        wanted = set(scenario_ids)
        selected = [e for e in ESCENARIOS if e.id in wanted]

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    shots = ARTIFACTS / "screenshots"
    results: list[AnalisisEscenario] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        # Smoke: login guest
        print("[PW] Smoke login invitado…", flush=True)
        _login_guest(page)
        page.screenshot(path=str(shots / "smoke_guest.png"), full_page=True)
        print("[PW] Login invitado OK", flush=True)

        for esc in selected:
            print(f"[PW] {esc.id} — {esc.nombre}…", flush=True)
            try:
                res = run_escenario_playwright(page, esc, screenshot_dir=shots)
                results.append(res)
                print(
                    f"  score={res.score_n1} resolutivo={res.resolutivo_autonomo} "
                    f"ticket_prem={res.ticket_prematuro}",
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
                                "(error Playwright)",
                                f"ERROR: {exc}",
                                no_debe_ticket_prematuro=True,
                            )
                        ],
                        resolucion_n1_esperada=esc.resolucion_n1_esperada,
                    )
                )
        browser.close()
    return results
