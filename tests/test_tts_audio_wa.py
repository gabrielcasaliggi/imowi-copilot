"""TTS local (Piper) y respuesta en audio por WhatsApp."""

from __future__ import annotations

from app.services.tts import sintetizar_audio, texto_apto_para_audio, tts_disponible


def test_texto_apto_para_audio():
    assert texto_apto_para_audio("Hola, ¿tenés internet?")
    assert not texto_apto_para_audio("")
    assert not texto_apto_para_audio("Pagá acá https://pay.example.com/x")
    assert not texto_apto_para_audio("x" * 900)


def test_sintetizar_deshabilitado(monkeypatch):
    monkeypatch.setattr("app.services.tts.TTS_ENABLED", False)
    assert sintetizar_audio("hola") == b""


def test_sintetizar_ok(monkeypatch):
    monkeypatch.setattr("app.services.tts.TTS_ENABLED", True)
    monkeypatch.setattr("app.services.tts.TTS_URL", "http://tts.test")

    class _Resp:
        status_code = 200
        content = b"O" * 200

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("app.services.tts.httpx.Client", _Client)
    assert len(sintetizar_audio("Hola, soy Eco")) >= 64


def test_dispatch_outbound_prefers_audio(monkeypatch, db):
    session, org_id = db
    from app.estate import canal_repo as crepo
    from app.services import canal_abonado as ca

    conv = crepo.get_or_create_conversacion(
        session, org_id, telefono="5491100000000", canal="whatsapp", wa_id="5491100000000"
    )
    ctx = crepo.get_contexto(conv)
    ctx["responder_en_audio"] = True
    crepo.set_contexto(conv, ctx)
    session.commit()

    calls: list[str] = []

    monkeypatch.setattr(
        "app.services.tts.sintetizar_audio",
        lambda _t: b"fake-ogg-bytes-xxxxxxxx",
    )

    def _audio(dest, data, **k):
        calls.append("audio")
        return {"ok": True, "to": dest, "type": "audio"}

    def _texto(dest, texto):
        calls.append("texto")
        return {"ok": True, "to": dest, "type": "text"}

    monkeypatch.setattr("app.services.whatsapp_client.enviar_audio", _audio)
    monkeypatch.setattr(ca, "enviar_texto_wa", _texto)
    # _dispatch_outbound imports enviar_audio inside the function
    monkeypatch.setattr(
        "app.services.whatsapp_client.enviar_audio",
        _audio,
    )

    out = ca._dispatch_outbound(conv, "Hola, ¿en qué te ayudo?", prefer_audio=True)
    assert out.get("ok") is True
    assert calls == ["audio"]


def test_dispatch_fallback_texto_si_tts_vacio(monkeypatch, db):
    session, org_id = db
    from app.estate import canal_repo as crepo
    from app.services import canal_abonado as ca

    conv = crepo.get_or_create_conversacion(
        session, org_id, telefono="5491100000001", canal="whatsapp", wa_id="5491100000001"
    )
    monkeypatch.setattr("app.services.tts.sintetizar_audio", lambda _t: b"")
    calls: list[str] = []

    def _texto(dest, texto):
        calls.append("texto")
        return {"ok": True, "to": dest}

    monkeypatch.setattr(ca, "enviar_texto_wa", _texto)
    out = ca._dispatch_outbound(conv, "Hola", prefer_audio=True)
    assert out.get("ok") is True
    assert calls == ["texto"]


def test_tts_disponible(monkeypatch):
    monkeypatch.setattr("app.services.tts.TTS_ENABLED", True)
    monkeypatch.setattr("app.services.tts.TTS_URL", "http://localhost:9100")
    assert tts_disponible() is True
    monkeypatch.setattr("app.services.tts.TTS_ENABLED", False)
    assert tts_disponible() is False
