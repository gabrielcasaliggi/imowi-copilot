from app.domain.canales import (
    canal_display,
    enviar_externo,
    es_canal_propio,
    normalizar_canal_portal,
)


def test_normalizar_canal_portal():
    assert normalizar_canal_portal("app") == "app"
    assert normalizar_canal_portal("APP") == "app"
    assert normalizar_canal_portal("web") == "web"
    assert normalizar_canal_portal("whatsapp") == "web"
    assert normalizar_canal_portal("") == "web"


def test_es_canal_propio_y_externo():
    assert es_canal_propio("app")
    assert es_canal_propio("web")
    assert not es_canal_propio("whatsapp")
    assert enviar_externo("whatsapp")
    assert enviar_externo("telegram")
    assert not enviar_externo("app")
    assert not enviar_externo("web")


def test_canal_display():
    assert canal_display("app") == "App"
    assert canal_display("web") == "Web"
    assert canal_display("whatsapp") == "WhatsApp"
    assert canal_display("telegram") == "Telegram"
