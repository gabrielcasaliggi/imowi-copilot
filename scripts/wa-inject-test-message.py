#!/usr/bin/env python3
"""Inyecta un mensaje WhatsApp firmado al webhook (diagnóstico E2E inbound).

Uso:
  export WA_APP_SECRET='...'          # App Secret de Meta (Settings → Basic)
  python3 scripts/wa-inject-test-message.py

Opcional:
  WA_API_URL=https://ibot.ecolan.com
  WA_FROM=5492235550199
  WA_TEXT='hola eco test'
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = (os.getenv("WA_API_URL") or "https://ibot.ecolan.com").rstrip("/")
SECRET = (os.getenv("WA_APP_SECRET") or "").strip()
FROM = "".join(c for c in (os.getenv("WA_FROM") or "5492230000001") if c.isdigit())
TEXT = (os.getenv("WA_TEXT") or f"hola eco inject {int(time.time())}").strip()
PHONE_NUMBER_ID = (os.getenv("WA_PHONE_NUMBER_ID") or "1245055745266260").strip()


def main() -> int:
    if not SECRET:
        print("Falta WA_APP_SECRET (App Secret de Meta).", file=sys.stderr)
        return 2

    mid = f"wamid.DIAG_{int(time.time())}"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "diag-entry",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15556671827",
                                "phone_number_id": PHONE_NUMBER_ID,
                            },
                            "contacts": [{"profile": {"name": "Diag"}, "wa_id": FROM}],
                            "messages": [
                                {
                                    "from": FROM,
                                    "id": mid,
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": TEXT},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    req = urllib.request.Request(
        f"{API}/api/v1/whatsapp/webhook",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={sig}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"HTTP {resp.status}: {body}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        if e.code == 403:
            print(
                "Firma rechazada: el App Secret no coincide con el guardado en el hub.",
                file=sys.stderr,
            )
        return 1

    print(f"OK — buscá en bandeja (org coop-batan) el texto: {TEXT}")
    print(f"     telefono/wa_id: {FROM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
