"""Smoke Playwright — login consola + portal visitante (Fase C rápida)."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def smoke_console(base_url: str, user: str, password: str, *, headed: bool = False) -> None:
    from playwright.sync_api import sync_playwright

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    login_url = base_url.rstrip("/") + "/login"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page()
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)
            page.locator("#login-usuario").fill(user)
            page.locator("#login-password").fill(password)
            page.get_by_role("button", name=re.compile(r"Ingresar|Entrar", re.I)).click()
            page.wait_for_url(re.compile(r"/(inbox|soporte|tickets|change-password)"), timeout=60_000)
            page.screenshot(path=str(ARTIFACTS / "smoke_console_ok.png"), full_page=True)
            print("OK console login →", page.url)
        except Exception:
            page.screenshot(path=str(ARTIFACTS / "smoke_console_fail.png"), full_page=True)
            raise
        finally:
            browser.close()


def smoke_portal_guest(base_url: str, *, headed: bool = False) -> None:
    from playwright.sync_api import sync_playwright

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    portal = base_url.rstrip("/") + "/portal"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        page = browser.new_page()
        try:
            page.goto(portal, wait_until="domcontentloaded", timeout=60_000)
            btn = page.get_by_role(
                "button",
                name=re.compile(
                    r"(Continuar como invitado|No soy abonado|consulta general)",
                    re.I,
                ),
            )
            if btn.count() == 0:
                raise RuntimeError(
                    "No hay CTA de visitante (PORTAL_ALLOW_GUEST=false?). "
                    "En prod con guest off este smoke no aplica."
                )
            btn.first.click()
            page.wait_for_timeout(1500)
            body = page.inner_text("body").lower()
            if "agente" not in body and "visitante" not in body and "abonado" not in body:
                raise RuntimeError("Tras guest no se ve mensaje de derivación/cola")
            page.screenshot(path=str(ARTIFACTS / "smoke_portal_guest_ok.png"), full_page=True)
            print("OK portal guest handoff")
        except Exception:
            page.screenshot(path=str(ARTIFACTS / "smoke_portal_guest_fail.png"), full_page=True)
            raise
        finally:
            browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke Playwright Fase C")
    parser.add_argument("--base-url", default=os.getenv("QA_BASE_URL", "http://127.0.0.1:3000"))
    parser.add_argument("--console-user", default=os.getenv("VERIFY_USER", ""))
    parser.add_argument("--console-password", default=os.getenv("VERIFY_PASSWORD", ""))
    parser.add_argument("--skip-console", action="store_true")
    parser.add_argument("--skip-portal", action="store_true")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)

    if not args.skip_console:
        if not args.console_user or not args.console_password:
            print("SKIP console: set VERIFY_USER / VERIFY_PASSWORD o --console-user/--console-password")
        else:
            smoke_console(
                args.base_url,
                args.console_user,
                args.console_password,
                headed=args.headed,
            )
    if not args.skip_portal:
        smoke_portal_guest(args.base_url, headed=args.headed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
