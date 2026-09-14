"""Adjuntos de canal (fotos / PDF) en el hilo del inbox.

Los bytes viven en disco bajo data/canal_media/. El LLM no recibe el archivo:
solo un marcador de texto. El operador los ve autenticado en la bandeja.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.persistencia import data_dir

logger = logging.getLogger("operations_hub.canal_media")

MAX_BYTES = 8 * 1024 * 1024
_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


class MediaRechazado(ValueError):
    """Tipo, tamaño o contenido no permitido."""


def sniff_mime(raw: bytes) -> str:
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"%PDF"):
        return "application/pdf"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    return ""


def es_marcador_media(texto: str) -> bool:
    t = (texto or "").strip().lower()
    return t in {"[image]", "[document]", "[video]", "[sticker]", "[audio]"}


def preview_adjunto(*, tipo: str, filename: str, texto: str) -> str:
    kind = (tipo or "").strip().lower()
    cap = (texto or "").strip()
    if kind == "image":
        if cap and not es_marcador_media(cap):
            return cap
        return "Foto"
    if kind == "document":
        name = (filename or "").strip()
        if name:
            return name
        if cap and not es_marcador_media(cap):
            return cap
        return "Documento"
    return cap or "Archivo"


def _assert_id(value: str, *, campo: str) -> str:
    s = (value or "").strip()
    if not s or not _ID_RE.match(s) or ".." in s:
        raise MediaRechazado(f"{campo} inválido")
    return s


def _safe_filename(name: str, mime: str) -> str:
    raw = (name or "").strip().replace("\\", "/").split("/")[-1]
    stem = _SAFE_NAME_RE.sub("_", raw).strip("._")[:80]
    ext = _EXT.get(mime, "")
    if stem and "." in stem:
        return stem[:180]
    if stem:
        return f"{stem}{ext}"[:180]
    if mime.startswith("image/"):
        return f"foto{ext}"
    return f"documento{ext}" or "documento.bin"


def media_root() -> Path:
    root = data_dir() / "canal_media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def guardar(
    *,
    org_id: str,
    conversacion_id: str,
    mensaje_id: str,
    raw: bytes,
    tipo: str,
    mime: str = "",
    filename: str = "",
) -> dict[str, str]:
    """Persiste bytes y retorna metadatos para MensajeCanal."""
    blob = bytes(raw or b"")
    if not blob:
        raise MediaRechazado("archivo vacío")
    if len(blob) > MAX_BYTES:
        raise MediaRechazado("archivo demasiado grande")
    sniffed = sniff_mime(blob)
    if not sniffed:
        raise MediaRechazado("tipo no permitido")
    declared = (mime or "").strip().lower()
    if declared and declared != sniffed:
        logger.info("Media mime declarado=%s sniff=%s; se usa sniff", declared, sniffed)
    mime_ok = sniffed
    kind = (tipo or "").strip().lower()
    if kind not in ("image", "document"):
        kind = "document" if mime_ok == "application/pdf" else "image"
    if mime_ok == "application/pdf":
        kind = "document"
    elif kind == "document" and mime_ok.startswith("image/"):
        kind = "image"

    org = _assert_id(org_id, campo="org_id")
    conv = _assert_id(conversacion_id, campo="conversacion_id")
    mid = _assert_id(mensaje_id, campo="mensaje_id")
    ext = _EXT[mime_ok]
    rel = f"{org}/{conv}/{mid}{ext}"
    dest = media_root() / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(blob)
    return {
        "media_tipo": kind,
        "media_mime": mime_ok,
        "media_filename": _safe_filename(filename, mime_ok),
        "media_relpath": rel,
    }


def resolver_path(relpath: str) -> Path:
    rel = (relpath or "").strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel:
        raise MediaRechazado("ruta inválida")
    root = media_root().resolve()
    dest = (root / rel).resolve()
    if dest != root and root not in dest.parents:
        raise MediaRechazado("ruta inválida")
    if not dest.is_file():
        raise FileNotFoundError(rel)
    return dest
