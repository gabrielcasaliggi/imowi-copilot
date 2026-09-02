#!/usr/bin/env python3
"""Minado de sesiones Botmaker para comprensión contextual EKO.

Lee exports locales (sin subir PII al repo), anonimiza y agrega patrones:
- Respuestas cortas de usuario por contexto del bot
- Candidatos léxicos (typos frecuentes cerca de keywords ISP)
- Estadísticas de longitud y tipos de mensaje

Salida por defecto: data/comprension-botmaker/ (gitignored).
Artefacto versionable: app/data/comprension_lexico_curado.json (sin PII).

Uso:
  .venv/bin/python scripts/minar_comprension_botmaker.py \\
    --input-dir ~/Descargas/sesiones-historicas-2025_2026-06 \\
    --emit-curado app/data/comprension_lexico_curado.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Keywords ISP para detectar candidatos léxicos (ventana de contexto)
_KEYWORDS_ISP = (
    "internet",
    "wifi",
    "wi-fi",
    "fibra",
    "antena",
    "bai",
    "radio",
    "adsl",
    "deuda",
    "pago",
    "factura",
    "saldo",
    "pon",
    "los",
    "ont",
    "router",
    "móvil",
    "movil",
    "imowi",
    "datos",
    "señal",
    "senal",
)

# Clasificación heurística del último mensaje bot (pregunta pendiente proxy)
_BUCKET_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "aviso_deuda",
        (
            "saldo pendiente",
            "deuda",
            "pagar",
            "moros",
            "corte por",
            "factura impaga",
            "abonar",
            "qr",
            "preferís pagar",
            "preferis pagar",
        ),
    ),
    (
        "menu_tipo_acceso",
        (
            "fibra",
            "antena",
            "adsl",
            "cajita blanca",
            "tipo de conexión",
            "tipo de conexion",
            "por teléfono",
            "por telefono",
            "ftth",
        ),
    ),
    (
        "menu_servicio",
        (
            "opción 1",
            "opcion 1",
            "internet fijo",
            "móvil imowi",
            "movil imowi",
            "facturación",
            "facturacion",
            "elegí una opción",
            "elegi una opcion",
            "menú",
            "menu",
        ),
    ),
    (
        "wifi_interferencias",
        (
            "metálic",
            "metalic",
            "interferen",
            "microondas",
            "electrodomést",
            "electrodomest",
        ),
    ),
    (
        "confirmar_paso",
        (
            "reinici",
            "desenchuf",
            "¿pudiste",
            "¿ya",
            "probalo",
            "probá",
            "intentalo",
            "intentá",
            "hiciste",
        ),
    ),
    (
        "csat",
        (
            "calificación",
            "calificacion",
            "resolvió",
            "resolvio",
            "del 1 al 5",
            "1 al 5",
        ),
    ),
    (
        "identificacion",
        ("dni", "documento", "número de socio", "numero de socio", "titular"),
    ),
)

_DNI_RE = re.compile(r"\b\d{7,8}\b")
_PHONE_RE = re.compile(r"\b549\d{8,12}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
_COORD_RE = re.compile(r"-?\d{1,3}\.\d{4,},-?\d{1,3}\.\d{4,}")


def _anonimizar_texto(texto: str) -> str:
    t = texto or ""
    t = _PHONE_RE.sub("[telefono]", t)
    t = _DNI_RE.sub("[dni]", t)
    t = _EMAIL_RE.sub("[email]", t)
    t = _COORD_RE.sub("[ubicacion]", t)
    return t.strip()


def _clasificar_bot(bot: str) -> str:
    low = (bot or "").lower()
    for bucket, patterns in _BUCKET_PATTERNS:
        if any(p in low for p in patterns):
            return bucket
    if "?" in low or "¿" in low:
        return "confirmar_si_no"
    return "otro"


def _extraer_texto_mensaje(msg: dict[str, Any]) -> str | None:
    content = msg.get("content") or {}
    tipo = content.get("type") or ""
    if tipo == "text":
        return (content.get("text") or "").strip() or None
    if tipo == "button-click":
        for key in ("selectedButton", "text", "payload", "title"):
            val = content.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        return None
    return None


def _es_respuesta_corta(texto: str, max_len: int = 40) -> bool:
    t = (texto or "").strip()
    if not t or len(t) > max_len:
        return False
    # Excluir URLs y blobs largos sin espacios
    if len(t) > 20 and " " not in t and "/" in t:
        return False
    return True


def _cerca_keyword_isp(texto: str) -> bool:
    low = (texto or "").lower()
    return any(k in low for k in _KEYWORDS_ISP)


def _normalizar_frase(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").lower().strip())


@dataclass
class MineroStats:
    sessions: int = 0
    user_messages: int = 0
    bot_messages: int = 0
    pares_cortos: int = 0
    por_bucket: Counter = field(default_factory=Counter)
    longitudes_usuario: Counter = field(default_factory=Counter)
    tipos_mensaje: Counter = field(default_factory=Counter)


class MineroComprension:
    def __init__(self, *, max_user_len: int = 40) -> None:
        self.max_user_len = max_user_len
        self.stats = MineroStats()
        # bucket -> Counter(frase normalizada)
        self.frases_por_bucket: dict[str, Counter] = defaultdict(Counter)
        # typo candidato -> count (solo si no matchea keyword pero parece typo)
        self.candidatos_lexico: Counter = Counter()
        self.archivos_procesados: list[str] = []

    def procesar_sesion(self, session: dict[str, Any]) -> None:
        self.stats.sessions += 1
        prev_bot = ""
        prev_bucket = "otro"
        for msg in session.get("messages") or []:
            sender = msg.get("from") or ""
            content = msg.get("content") or {}
            self.stats.tipos_mensaje[content.get("type") or "unknown"] += 1

            texto = _extraer_texto_mensaje(msg)
            if not texto:
                continue

            if sender == "bot":
                self.stats.bot_messages += 1
                prev_bot = _anonimizar_texto(texto)
                prev_bucket = _clasificar_bot(prev_bot)
            elif sender == "user":
                self.stats.user_messages += 1
                anon = _anonimizar_texto(texto)
                ln = len(anon)
                if ln <= 8:
                    self.stats.longitudes_usuario["<=8"] += 1
                elif ln <= 20:
                    self.stats.longitudes_usuario["9-20"] += 1
                elif ln <= 60:
                    self.stats.longitudes_usuario["21-60"] += 1
                else:
                    self.stats.longitudes_usuario[">60"] += 1

                if _es_respuesta_corta(anon, self.max_user_len):
                    frase = _normalizar_frase(anon)
                    if frase and not frase.startswith("["):
                        self.frases_por_bucket[prev_bucket][frase] += 1
                        self.stats.pares_cortos += 1
                        self.stats.por_bucket[prev_bucket] += 1

                # Candidatos léxicos: palabras raras en mensajes con tema ISP
                if _cerca_keyword_isp(anon) or prev_bucket in (
                    "menu_tipo_acceso",
                    "aviso_deuda",
                    "wifi_interferencias",
                ):
                    for token in re.findall(r"[a-záéíóúñü0-9]{3,}", anon.lower()):
                        if token.isdigit():
                            continue
                        if any(k in token or token in k for k in _KEYWORDS_ISP):
                            continue
                        if len(token) <= 12:
                            self.candidatos_lexico[token] += 1

    def procesar_archivo(self, path: Path) -> None:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        for session in data.get("items") or []:
            self.procesar_sesion(session)
        self.archivos_procesados.append(path.name)

    def top_frases(self, bucket: str, n: int = 50) -> list[dict[str, Any]]:
        ctr = self.frases_por_bucket.get(bucket) or Counter()
        return [{"frase": f, "count": c} for f, c in ctr.most_common(n)]

    def generar_reporte(self) -> dict[str, Any]:
        return {
            "generado_at": datetime.now(UTC).isoformat(),
            "archivos": self.archivos_procesados,
            "stats": {
                "sessions": self.stats.sessions,
                "user_messages": self.stats.user_messages,
                "bot_messages": self.stats.bot_messages,
                "pares_cortos": self.stats.pares_cortos,
                "por_bucket": dict(self.stats.por_bucket),
                "longitudes_usuario": dict(self.stats.longitudes_usuario),
                "tipos_mensaje": dict(self.stats.tipos_mensaje),
            },
            "top_frases_por_bucket": {
                bucket: self.top_frases(bucket, 40)
                for bucket in sorted(self.frases_por_bucket.keys())
            },
            "top_candidatos_lexico": [
                {"token": t, "count": c}
                for t, c in self.candidatos_lexico.most_common(80)
            ],
        }

    def generar_lexico_curado(self) -> dict[str, Any]:
        """Artefacto versionable: patrones agregados sin PII."""

        # Reemplazos léxicos data-driven (solo tokens con frecuencia alta y semántica clara)
        reemplazos_extra: list[tuple[str, str]] = []
        lex_map = {
            "intenet": "internet",
            "intenret": "internet",
            "internt": "internet",
            "wfi": "wifi",
            "wiffi": "wifi",
            "beibe": "bai",
            "beibi": "bai",
            "anel": "antena",
            "anntena": "antena",
            "fibbra": "fibra",
            "factura": "factura",  # noop anchor
            "deuda": "deuda",
        }
        for token, count in self.candidatos_lexico.most_common(200):
            if count < 15:
                break
            if token in lex_map and lex_map[token] != token:
                reemplazos_extra.append((rf"\b{re.escape(token)}\b", lex_map[token]))

        # Frases cortas frecuentes por bucket (top 25, min count 20)
        frases_contexto: dict[str, list[str]] = {}
        for bucket, ctr in self.frases_por_bucket.items():
            items = [f for f, c in ctr.most_common(25) if c >= 20]
            if items:
                frases_contexto[bucket] = items

        # Afirmaciones/negaciones ampliadas desde datos
        afirmaciones = set()
        negaciones = set()
        for frase, count in self.frases_por_bucket.get("confirmar_si_no", Counter()).items():
            if count < 30:
                continue
            if frase in ("si", "sí", "sip", "sep", "ok", "dale", "listo", "claro", "bueno", "ya"):
                afirmaciones.add(frase)
            if frase in ("no", "nop", "nada", "nah"):
                negaciones.add(frase)

        # Frases técnicas en aviso deuda (excluir saludos y números de menú Botmaker)
        _skip = frozenset(
            {
                "hola",
                "gracias",
                "ok",
                "menu",
                ".",
                "?",
                "buen día",
                "buen dia",
                "buenas",
                "buenas tardes",
                "excelente",
                "buena",
            }
        )
        frases_tecnico_deuda: list[str] = []
        ctr_deuda = self.frases_por_bucket.get("aviso_deuda") or Counter()
        for frase, count in ctr_deuda.most_common(60):
            if count < 25:
                break
            if frase in _skip or frase.isdigit() or frase.endswith(")"):
                continue
            if any(
                k in frase
                for k in (
                    "internet",
                    "wifi",
                    "antena",
                    "fibra",
                    "no ",
                    "sin ",
                    "cort",
                    "servicio",
                    "lento",
                    "bai",
                    "radio",
                    "datos",
                    "móvil",
                    "movil",
                )
            ):
                frases_tecnico_deuda.append(frase)

        return {
            "version": 1,
            "fuente": "botmaker_sessions_2025_2026",
            "generado_at": datetime.now(UTC).isoformat(),
            "sessions_muestra": self.stats.sessions,
            "reemplazos_regex": [
                {"patron": p, "reemplazo": r} for p, r in reemplazos_extra
            ],
            "frases_frecuentes_por_contexto": frases_contexto,
            "frases_tecnico_en_aviso_deuda": frases_tecnico_deuda,
            "afirmaciones_cortas_extra": sorted(afirmaciones),
            "negaciones_cortas_extra": sorted(negaciones),
            "menu_numerico_frecuente": self.top_frases("menu_servicio", 15)
            + self.top_frases("menu_tipo_acceso", 15),
            "nota_menu_numerico": (
                "Botmaker usaba menús numéricos (ej. '7' en aviso deuda). "
                "EKO no replica esos códigos; solo se versionan como estadística."
            ),
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Minar patrones de comprensión Botmaker")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path.home() / "Descargas/sesiones-historicas-2025_2026-06",
        help="Directorio con sessions-*.raw.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/comprension-botmaker"),
        help="Salida agregada (gitignored)",
    )
    parser.add_argument(
        "--emit-curado",
        type=Path,
        default=Path("app/data/comprension_lexico_curado.json"),
        help="JSON curado versionable en el repo",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=0,
        help="Limitar archivos (0 = todos)",
    )
    parser.add_argument(
        "--file",
        action="append",
        dest="files",
        help="Procesar solo estos archivos (nombre base)",
    )
    args = parser.parse_args(argv)

    input_dir: Path = args.input_dir
    if not input_dir.is_dir():
        print(f"ERROR: no existe {input_dir}", file=sys.stderr)
        return 1

    if args.files:
        paths = [input_dir / f for f in args.files]
    else:
        paths = sorted(input_dir.glob("sessions-*.raw.json"))
        if args.max_files > 0:
            paths = paths[: args.max_files]

    if not paths:
        print(f"ERROR: sin archivos en {input_dir}", file=sys.stderr)
        return 1

    minero = MineroComprension()
    for path in paths:
        if not path.is_file():
            print(f"WARN: omitido {path}", file=sys.stderr)
            continue
        print(f"Procesando {path.name}...", flush=True)
        minero.procesar_archivo(path)

    report = minero.generar_reporte()
    curado = minero.generar_lexico_curado()

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "patrones_agregados.json").write_text(
        json.dumps(curado, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    emit: Path = args.emit_curado
    emit.parent.mkdir(parents=True, exist_ok=True)
    emit.write_text(json.dumps(curado, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"\nOK: {minero.stats.sessions} sesiones, "
        f"{minero.stats.pares_cortos} pares cortos bot→usuario"
    )
    print(f"Reporte: {out_dir / 'report.json'}")
    print(f"Curado:  {emit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
