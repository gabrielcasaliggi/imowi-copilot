"""Adjuntos de canal: persistir foto/PDF en el hilo y servirlos al operador."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.estate.database import get_session_factory
from app.estate.models import MensajeCanal, Organization
from app.services.canal_abonado import procesar_mensaje_entrante
from app.services.canal_media import MediaRechazado, guardar, resolver_path, sniff_mime
from main import app
from tests.test_inbox_canal import _admin_headers, _cerrar_convs_telefono

client = TestClient(app)

# PNG 1×1 válido
_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_sniff_png():
    assert sniff_mime(_PNG) == "image/png"
    assert sniff_mime(b"%PDF-1.4") == "application/pdf"
    assert sniff_mime(b"not-a-file") == ""


def test_guardar_rechaza_tipo_y_tamano(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.canal_media.data_dir", lambda: tmp_path)
    try:
        guardar(
            org_id="org1",
            conversacion_id="conv1",
            mensaje_id="msg1",
            raw=b"PK zip",
            tipo="document",
            mime="application/zip",
            filename="x.zip",
        )
        raise AssertionError("debía rechazar zip")
    except MediaRechazado:
        pass
    try:
        guardar(
            org_id="org1",
            conversacion_id="conv1",
            mensaje_id="msg1",
            raw=_PNG + b"\x00" * (9 * 1024 * 1024),
            tipo="image",
            mime="image/png",
            filename="huge.png",
        )
        raise AssertionError("debía rechazar tamaño")
    except MediaRechazado:
        pass


def test_guardar_y_resolver(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.canal_media.data_dir", lambda: tmp_path)
    meta = guardar(
        org_id="org-1",
        conversacion_id="conv-1",
        mensaje_id="msg-1",
        raw=_PNG,
        tipo="image",
        mime="image/png",
        filename="dni.png",
    )
    assert meta["media_tipo"] == "image"
    path = resolver_path(meta["media_relpath"])
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    try:
        resolver_path("../etc/passwd")
        raise AssertionError("path traversal")
    except MediaRechazado:
        pass


def test_inbox_persiste_foto_y_la_sirve(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.canal_media.data_dir", lambda: tmp_path)
    headers = _admin_headers()
    tel = "5492235599111"
    _cerrar_convs_telefono(tel)
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org is not None
        result = procesar_mensaje_entrante(
            db,
            org.id,
            telefono=tel,
            texto="[image]",
            canal="whatsapp",
            usar_llama=False,
            adjunto={
                "tipo": "image",
                "mime": "image/png",
                "filename": "dni.png",
                "bytes": _PNG,
            },
        )
    assert result.get("ok") is True
    assert result.get("media") is True
    assert "guardado" in (result.get("respuesta") or "").lower()
    cid = result["conversacion_id"]

    detail = client.get(f"/api/v1/inbox/conversations/{cid}", headers=headers)
    assert detail.status_code == 200
    msgs = detail.json()["mensajes"]
    foto = next(m for m in msgs if m.get("media_tipo") == "image")
    assert foto["media_filename"] == "dni.png"
    assert foto["media_url"].endswith("/media")

    listed = client.get("/api/v1/inbox/conversations", headers=headers)
    sample = next(c for c in listed.json()["conversaciones"] if c["id"] == cid)
    preview = sample.get("ultimo_mensaje_texto") or ""
    assert preview in ("Foto", "dni.png") or "guardado" in preview.lower()

    media = client.get(foto["media_url"], headers=headers)
    assert media.status_code == 200
    assert media.content.startswith(b"\x89PNG")
    anon = client.get(foto["media_url"])
    assert anon.status_code in (401, 403)


def test_foto_en_espera_agente_no_dispara_n1(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.canal_media.data_dir", lambda: tmp_path)
    tel = "5492235599112"
    _cerrar_convs_telefono(tel)
    Session = get_session_factory()
    with Session() as db:
        org = db.scalar(select(Organization).where(Organization.slug == "coop-batan"))
        assert org is not None
        from app.estate import canal_repo as crepo

        conv = crepo.get_or_create_conversacion(
            db, org.id, telefono=tel, canal="whatsapp", wa_id=tel
        )
        conv.estado = "espera_agente"
        db.commit()
        result = procesar_mensaje_entrante(
            db,
            org.id,
            telefono=tel,
            texto="[image]",
            canal="whatsapp",
            usar_llama=False,
            adjunto={
                "tipo": "image",
                "mime": "image/png",
                "filename": "dni.png",
                "bytes": _PNG,
            },
        )
    assert result.get("estado") == "espera_agente"
    assert result.get("respuesta") == ""
    assert result.get("media") is True
    with Session() as db:
        rows = list(
            db.scalars(
                select(MensajeCanal)
                .where(MensajeCanal.conversacion_id == result["conversacion_id"])
                .order_by(MensajeCanal.created_at.asc())
            ).all()
        )
    assert rows[-1].autor == "cliente"


def test_webhook_image_caption():
    from app.api.v1.whatsapp import _extraer_texto_mensaje

    assert _extraer_texto_mensaje({"type": "image", "image": {"caption": "dni"}}) == "dni"
    assert _extraer_texto_mensaje({"type": "document", "document": {}}) == "[document]"
