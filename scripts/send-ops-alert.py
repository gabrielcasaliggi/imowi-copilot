#!/usr/bin/env python3
"""Envía alerta ops por SMTP (app.services.email) y/o Telegram Bot API.

Uso:
  python scripts/send-ops-alert.py --subject "..." --body "..."
Lee APP_ROOT/.env y /etc/default/operations-hub-alert (vía env ya exportado).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key and key not in os.environ:
            os.environ[key] = val


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": True}
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"telegram fail: {exc}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Alerta ops SMTP/Telegram")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument(
        "--app-root",
        default=os.environ.get("APP_ROOT", "/opt/operations-hub"),
    )
    args = parser.parse_args()

    _load_dotenv(Path(args.app_root) / ".env")

    ok_any = False

    email_to = (os.environ.get("ALERT_EMAIL_TO") or "").strip()
    if email_to:
        try:
            from app.services.email import send_email

            if send_email(to=email_to, subject=args.subject, body_text=args.body):
                print(f"email OK → {email_to}")
                ok_any = True
            else:
                from app.services.email import get_last_error

                print(f"email FAIL → {get_last_error()}", file=sys.stderr)
        except Exception as exc:
            print(f"email FAIL → {exc}", file=sys.stderr)

    token = (os.environ.get("ALERT_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("ALERT_TELEGRAM_CHAT_ID") or "").strip()
    if token and chat:
        text = f"{args.subject}\n\n{args.body}"
        if send_telegram(token, chat, text):
            print(f"telegram OK → chat {chat}")
            ok_any = True
        else:
            print("telegram FAIL", file=sys.stderr)

    if not email_to and not (token and chat):
        print(
            "sin canal: definí ALERT_EMAIL_TO y/o ALERT_TELEGRAM_CHAT_ID "
            "(+ TELEGRAM_BOT_TOKEN)",
            file=sys.stderr,
        )
        return 2

    return 0 if ok_any else 1


if __name__ == "__main__":
    raise SystemExit(main())
