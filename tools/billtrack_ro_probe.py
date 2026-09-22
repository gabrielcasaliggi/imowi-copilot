#!/usr/bin/env python3
"""BillTrack schema probe — READ ONLY — ejecución manual por Ops.

Uso (en el runtime con acceso BillTrack, p.ej. /opt/operations-hub):

  cd /opt/operations-hub
  source .venv/bin/activate
  python tools/billtrack_ro_probe.py

Reutiliza app.services.billtrack.resolve_connection (platform_config / env).
NO imprime passwords ni connection strings.
NO escribe en BillTrack ni en Data Estate.
NO modifica Facts / Eko / flags / config.

Salida: reporte markdown en stdout + "PROBE COMPLETE".
"""

from __future__ import annotations

import re
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Safety: refuse if invoked with write-like args
# ---------------------------------------------------------------------------
_FORBIDDEN_ARGS = frozenset(
    {"--write", "--mutate", "--apply", "--migrate", "--install"}
)
if _FORBIDDEN_ARGS.intersection(a.lower() for a in sys.argv[1:]):
    print("REFUSED: este script es solo discovery READ-ONLY.", file=sys.stderr)
    raise SystemExit(2)


TABLE_KW = re.compile(
    r"invoice|factura|factur|billing|bill|payment|pago|pagos|receipt|recibo|"
    r"comprobante|collection|cobranza|account|cuenta|statement|current_account|"
    r"cuenta_corriente|due|vencimiento|installment|cuota|document|documento",
    re.I,
)

COLUMN_KW = re.compile(
    r"person|customer|account|client|partner|invoice|factura|period|periodo|"
    r"issue|emission|emision|due|vencimiento|amount|importe|total|status|estado|"
    r"payment|pago|method|medio|receipt|recibo|comprobante|document|pdf|"
    r"doc_cuit|dni|balance|billing",
    re.I,
)

SAMPLE_TABLE_KW = re.compile(
    r"invoice|factura|payment|pago|receipt|recibo|comprobante|statement|"
    r"cuenta_corriente|current_account",
    re.I,
)

# Never SELECT these column names (case-insensitive substring)
_SENSITIVE_COL = re.compile(
    r"password|passwd|secret|token|api_key|apikey|sid|session|"
    r"card|tarjeta|cvv|cvc|pan|iban|cbu|alias_cbu|pin",
    re.I,
)

# Prefer these for sample semantics (non-PII-ish)
_SAMPLE_PREFER = re.compile(
    r"id$|_id$|number|numero|period|periodo|issue|emission|emision|"
    r"due|vencimiento|amount|importe|total|status|estado|method|medio|"
    r"type|tipo|date|fecha|client_number|partner_number|account|"
    r"pdf|document|url|path|file",
    re.I,
)

# Anonymize these if they appear in samples
_PII_COL = re.compile(
    r"name|nombre|email|mail|phone|telefono|msisdn|cuit|doc_|dni|"
    r"address|direccion|street|calle|collection_account|payer",
    re.I,
)


def _anon(val: Any) -> str:
    s = str(val) if val is not None else ""
    if not s:
        return ""
    if len(s) <= 2:
        return "**"
    return s[:1] + ("*" * min(8, len(s) - 2)) + s[-1:]


def _bootstrap_runtime() -> None:
    """Permite ejecutar desde /tmp o tools/ en el server de Ops."""
    import os
    from pathlib import Path

    # Repo root típico en prod
    candidates = [
        Path.cwd(),
        Path("/opt/operations-hub"),
        Path(__file__).resolve().parent.parent,
    ]
    for root in candidates:
        if (root / "app" / "services" / "billtrack.py").is_file():
            root_s = str(root)
            if root_s not in sys.path:
                sys.path.insert(0, root_s)
            env_file = root / ".env"
            if env_file.is_file():
                try:
                    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, _, v = line.partition("=")
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
                except OSError:
                    pass
            break


def _resolve_url() -> tuple[str, dict[str, Any], str]:
    """Retorna (url, meta_sin_secretos, error)."""
    _bootstrap_runtime()
    meta: dict[str, Any] = {
        "enabled": False,
        "host_set": False,
        "user": "",
        "dbname": "",
        "sslmode": "",
    }
    try:
        from app.estate.database import get_session_factory
        from app.services.billtrack import resolve_connection

        session = get_session_factory()()
        try:
            params = resolve_connection(session)
        finally:
            session.close()
    except Exception as exc:
        return "", meta, f"resolve_connection falló: {type(exc).__name__}"

    meta["enabled"] = bool(params.get("enabled"))
    meta["user"] = str(params.get("user") or "").strip()
    meta["dbname"] = str(params.get("dbname") or "").strip()
    meta["sslmode"] = str(params.get("sslmode") or "disable").strip() or "disable"
    host = str(params.get("host") or "").strip()
    url = str(params.get("url") or "").strip()
    meta["host_set"] = bool(host or url)
    if not url:
        return "", meta, "BillTrack URL no configurada (platform_config / env)"
    return url, meta, ""


def _verify_readonly(conn) -> tuple[bool, list[str]]:
    """Verifica RO real. No confía solo en el nombre del usuario.

    Criterios (todos deben pasar):
    1. current_user obtenido.
    2. default_transaction_read_only = on (sesión).
    3. Ningún privilegio de escritura (INSERT/UPDATE/DELETE/TRUNCATE/TRIGGER)
       sobre tablas public BASE TABLE muestreadas (api_person + hasta 20 más).
    4. has_database_privilege CREATE = false (ideal).
    """
    notes: list[str] = []
    try:
        conn.execute(__import__("sqlalchemy", fromlist=["text"]).text(
            "SET default_transaction_read_only = on"
        ))
        notes.append("SET default_transaction_read_only = on → OK")
    except Exception as exc:
        notes.append(f"SET read_only falló: {type(exc).__name__}")
        return False, notes

    from sqlalchemy import text

    try:
        ro = conn.execute(text("SHOW default_transaction_read_only")).scalar()
        notes.append(f"SHOW default_transaction_read_only = {ro}")
        if str(ro).lower() not in ("on", "true", "1"):
            notes.append("Sesión no quedó read-only")
            return False, notes
    except Exception as exc:
        notes.append(f"SHOW read_only falló: {type(exc).__name__}")
        return False, notes

    # Privileges on sample of public tables
    tables = [
        r[0]
        for r in conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY
                  CASE WHEN table_name = 'api_person' THEN 0 ELSE 1 END,
                  table_name
                LIMIT 25
                """
            )
        ).all()
    ]
    if not tables:
        notes.append("No hay tablas public BASE TABLE visibles")
        return False, notes

    write_privs = ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "TRIGGER")
    write_hits: list[str] = []
    for tname in tables:
        for priv in write_privs:
            try:
                ok = conn.execute(
                    text("SELECT has_table_privilege(current_user, :rel, :priv)"),
                    {"rel": f"public.{tname}", "priv": priv},
                ).scalar()
            except Exception:
                # Si no puede evaluar, no afirmar RO
                notes.append(f"has_table_privilege falló para {tname}/{priv}")
                return False, notes
            if ok:
                write_hits.append(f"{tname}:{priv}")

    if write_hits:
        notes.append(
            "Privilegios de escritura detectados (muestra): "
            + ", ".join(write_hits[:12])
            + ("…" if len(write_hits) > 12 else "")
        )
        return False, notes
    notes.append(
        f"Sin INSERT/UPDATE/DELETE/TRUNCATE/TRIGGER en {len(tables)} tablas muestreadas"
    )

    try:
        can_create = conn.execute(
            text("SELECT has_database_privilege(current_user, current_database(), 'CREATE')")
        ).scalar()
        notes.append(f"has_database_privilege CREATE = {can_create}")
        if can_create:
            notes.append("Usuario puede CREATE en la DB → no RO estricto")
            return False, notes
    except Exception as exc:
        notes.append(f"check CREATE privilege omitido: {type(exc).__name__}")

    return True, notes


def _relevant_columns(cols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in cols:
        name = str(c.get("column_name") or "")
        if COLUMN_KW.search(name):
            out.append(c)
    return out or cols[:12]  # si ninguna keyword, muestra primeras


def _pick_sample_columns(cols: list[dict[str, Any]], *, limit: int = 10) -> list[str]:
    names = [str(c["column_name"]) for c in cols]
    safe = [n for n in names if not _SENSITIVE_COL.search(n)]
    preferred = [n for n in safe if _SAMPLE_PREFER.search(n)]
    rest = [n for n in safe if n not in preferred]
    picked = (preferred + rest)[:limit]
    return picked


def _classify_gate(
    *,
    ro_ok: bool,
    reachable: bool,
    candidates: list[str],
    columns_by_table: dict[str, list[dict[str, Any]]],
    fks: list[dict[str, Any]],
) -> tuple[str, dict[str, dict[str, str]]]:
    """Retorna (GATE line, capability matrix rows)."""
    empty_caps = {
        k: {
            "source": "—",
            "ownership": "—",
            "confidence": "none",
            "status": "UNKNOWN_ACCESS" if not reachable else "NOT_FOUND",
        }
        for k in (
            "invoice number",
            "invoice amount",
            "invoice period",
            "issue date",
            "due date",
            "invoice status",
            "payment history",
            "payment date",
            "payment amount",
            "payment method",
            "payment status",
            "receipt",
            "PDF/document",
        )
    }
    if not reachable or not ro_ok:
        for v in empty_caps.values():
            v["status"] = "UNKNOWN_ACCESS"
        return "GATE E — ACCESS BLOCKED", empty_caps

    if not candidates:
        return "GATE D — NO STRUCTURED BILLING SOURCE FOUND", empty_caps

    # Heuristic field presence across candidates (nombre de columna)
    flat_cols: dict[str, list[str]] = {}
    for t, cols in columns_by_table.items():
        for c in cols:
            flat_cols.setdefault(str(c["column_name"]).lower(), []).append(t)

    def has(*patterns: str) -> list[str]:
        hit: list[str] = []
        for pat in patterns:
            rx = re.compile(pat, re.I)
            for col, tables in flat_cols.items():
                if rx.search(col):
                    hit.extend(f"{t}.{col}" for t in tables)
        return sorted(set(hit))

    invoice_num = has(r"invoice_?number", r"invoice_?no", r"nro_?factura", r"numero_?factura", r"^factura$")
    invoice_amt = has(r"invoice_?amount", r"importe_?factura", r"^total$", r"^importe$", r"^amount$")
    period = has(r"period", r"periodo", r"billing_?period")
    issue = has(r"issue_?date", r"issued_at", r"fecha_?emision", r"emission")
    due = has(r"due_?date", r"due_at", r"fecha_?vencimiento", r"^vencimiento$")
    inv_status = has(r"invoice_?status", r"estado_?factura")
    pay_date = has(r"payment_?date", r"paid_at", r"fecha_?pago")
    pay_amt = has(r"payment_?amount", r"importe_?pago")
    pay_method = has(r"payment_?method", r"medio_?pago", r"^method$")
    pay_status = has(r"payment_?status", r"estado_?pago")
    receipt = has(r"receipt", r"recibo", r"comprobante")
    pdf = has(r"^pdf$", r"document_?url", r"file_?url", r"document_path", r"pdf_path")

    # Ownership path evidence
    own_person = has(r"^person_id$", r"api_person_id", r"^customer_id$")
    own_client = has(r"client_number", r"partner_number", r"account_number", r"^account_id$")
    fk_to_person = any(
        str(f.get("foreign_table_name") or "") == "api_person" for f in fks
    )

    ownership_note = "unclear"
    if fk_to_person or own_person:
        ownership_note = "api_person.id (FK or person_id)"
    elif own_client:
        ownership_note = "client/partner/account number (inferred)"

    def fill(cap: str, hits: list[str], *, needs_own: bool = True) -> None:
        if not hits:
            empty_caps[cap] = {
                "source": "—",
                "ownership": ownership_note if candidates else "—",
                "confidence": "low",
                "status": "NOT_FOUND",
            }
            return
        conf = "medium" if needs_own and ownership_note != "unclear" else "low"
        if needs_own and ownership_note == "unclear":
            status = "DISCOVERED_BUT_NEEDS_CONTRACT"
        else:
            status = "AVAILABLE_BUT_AMBIGUOUS" if conf == "low" else "AVAILABLE_STRUCTURED"
        empty_caps[cap] = {
            "source": ", ".join(hits[:4]) + ("…" if len(hits) > 4 else ""),
            "ownership": ownership_note,
            "confidence": conf,
            "status": status,
        }

    fill("invoice number", invoice_num)
    fill("invoice amount", invoice_amt)
    fill("invoice period", period)
    fill("issue date", issue)
    fill("due date", due)
    fill("invoice status", inv_status)
    # payment history = presence of payment-like table+date/amount
    pay_hist_hits = pay_date or pay_amt or [t for t in candidates if re.search(r"pago|payment", t, re.I)]
    fill("payment history", list(pay_hist_hits) if pay_hist_hits else [])
    fill("payment date", pay_date)
    fill("payment amount", pay_amt)
    fill("payment method", pay_method)
    fill("payment status", pay_status)
    fill("receipt", receipt)
    fill("PDF/document", pdf)

    structured = sum(
        1
        for v in empty_caps.values()
        if v["status"] in ("AVAILABLE_STRUCTURED", "AVAILABLE_BUT_AMBIGUOUS")
    )
    unclear = sum(
        1 for v in empty_caps.values() if v["status"] == "DISCOVERED_BUT_NEEDS_CONTRACT"
    )
    found_any = structured + unclear > 0

    # Semantic clarity: need due OR invoice number + ownership FK
    clear = bool(invoice_num and (due or issue) and ownership_note.startswith("api_person"))
    partial = found_any and not clear

    if clear and structured >= 3:
        gate = "GATE A — STRUCTURED BILLING SOURCE FOUND"
    elif partial and unclear and not clear:
        gate = "GATE C — BILLING TABLES FOUND BUT SEMANTICS UNCLEAR"
    elif partial:
        gate = "GATE B — PARTIAL BILLING SOURCE FOUND"
    elif candidates and not found_any:
        gate = "GATE C — BILLING TABLES FOUND BUT SEMANTICS UNCLEAR"
    else:
        gate = "GATE D — NO STRUCTURED BILLING SOURCE FOUND"
    return gate, empty_caps


def main() -> int:
    print("# BILLTRACK RO PROBE")
    print()
    print("## ACCESS")
    print()

    url, meta, err = _resolve_url()
    if err or not url:
        print("RO_VERIFIED: NO")
        print("DATABASE_REACHABLE: NO")
        print("PROBE_STATUS: BLOCKED")
        print(f"REASON: {err or 'sin URL'}")
        print(f"CONFIG_ENABLED: {meta.get('enabled')}")
        print(f"HOST_SET: {meta.get('host_set')}")
        print(f"USER: {meta.get('user') or '(vacío)'}")
        print(f"DBNAME: {meta.get('dbname') or '(vacío)'}")
        print()
        print("## DECISION GATE")
        print()
        print("GATE E — ACCESS BLOCKED")
        print()
        print("## SAFETY")
        print()
        print("FILES CHANGED: NONE (solo lectura de este script)")
        print("MIGRATIONS: NONE")
        print("WRITES: NONE")
        print("PRODUCTION BEHAVIOR: NONE")
        print()
        print("PROBE COMPLETE")
        return 1

    from sqlalchemy import create_engine, text

    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 12, "sslmode": meta.get("sslmode") or "disable"},
    )

    ro_ok = False
    reachable = False
    current_user = ""
    current_db = ""
    ro_notes: list[str] = []
    all_tables: list[str] = []
    candidates: list[str] = []
    columns_by_table: dict[str, list[dict[str, Any]]] = {}
    fks: list[dict[str, Any]] = []
    pks: list[dict[str, Any]] = []
    uniques: list[dict[str, Any]] = []
    indexes: list[dict[str, Any]] = []
    samples: dict[str, list[dict[str, Any]]] = {}
    inferred: list[str] = []

    try:
        with engine.connect() as conn:
            reachable = True
            current_user = str(conn.execute(text("SELECT current_user")).scalar() or "")
            current_db = str(conn.execute(text("SELECT current_database()")).scalar() or "")
            try:
                ver = str(conn.execute(text("SELECT version()")).scalar() or "")[:90]
            except Exception:
                ver = ""

            ro_ok, ro_notes = _verify_readonly(conn)

            print(f"RO_VERIFIED: {'YES' if ro_ok else 'NO'}")
            print("DATABASE_REACHABLE: YES")
            print(f"PROBE_STATUS: {'PASS' if ro_ok else 'BLOCKED'}")
            print(f"CURRENT_USER: {current_user}")
            print(f"CURRENT_DATABASE: {current_db}")
            if ver:
                print(f"VERSION: {ver}")
            print(f"CONFIG_USER: {meta.get('user') or '(from url)'}")
            print(f"CONFIG_DBNAME: {meta.get('dbname') or current_db}")
            for n in ro_notes:
                print(f"RO_NOTE: {n}")
            print()

            if not ro_ok:
                print("## DECISION GATE")
                print()
                print("GATE E — ACCESS BLOCKED")
                print()
                print("## SAFETY")
                print()
                print("FILES CHANGED: NONE")
                print("MIGRATIONS: NONE")
                print("WRITES: NONE")
                print("PRODUCTION BEHAVIOR: NONE")
                print()
                print("PROBE COMPLETE")
                return 1

            # --- TABLES ---
            rows = conn.execute(
                text(
                    """
                    SELECT table_schema, table_name, table_type
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """
                )
            ).mappings().all()
            all_tables = [str(r["table_name"]) for r in rows]
            candidates = [t for t in all_tables if TABLE_KW.search(t)]

            print("## TABLES")
            print()
            print(f"PUBLIC_BASE_TABLE_COUNT: {len(all_tables)}")
            print(f"CANDIDATE_COUNT: {len(candidates)}")
            print()
            print("| SCHEMA | TABLE | CANDIDATE |")
            print("|--------|-------|-----------|")
            for t in all_tables:
                cand = "YES" if t in candidates else ""
                if cand or t.startswith("api_"):
                    print(f"| public | {t} | {cand} |")
            if not candidates:
                print()
                print("(sin candidatas por nombre; listado api_* arriba)")
            print()

            # Always include known Eko tables for ownership context
            inspect_tables = sorted(set(candidates) | {"api_person", "api_service"})
            inspect_tables = [t for t in inspect_tables if t in all_tables]

            # --- COLUMNS ---
            print("## COLUMNS")
            print()
            for tname in inspect_tables:
                cols = [
                    dict(r)
                    for r in conn.execute(
                        text(
                            """
                            SELECT column_name, data_type, is_nullable, ordinal_position
                            FROM information_schema.columns
                            WHERE table_schema = 'public' AND table_name = :n
                            ORDER BY ordinal_position
                            """
                        ),
                        {"n": tname},
                    ).mappings().all()
                ]
                columns_by_table[tname] = cols
                rel = _relevant_columns(cols)
                print(f"### {tname}")
                print()
                print("| COLUMN | TYPE | NULLABLE |")
                print("|--------|------|----------|")
                for c in rel:
                    print(
                        f"| {c['column_name']} | {c['data_type']} | {c['is_nullable']} |"
                    )
                print()

                # Inferred ownership columns (no FK yet)
                for c in cols:
                    cn = str(c["column_name"]).lower()
                    if cn in (
                        "person_id",
                        "api_person_id",
                        "client_number",
                        "partner_number",
                        "account_id",
                        "customer_id",
                    ):
                        inferred.append(
                            f"RELACIÓN INFERIDA — NO FK: {tname}.{c['column_name']}"
                        )

            # --- RELATIONSHIPS (formal FKs) ---
            print("## RELATIONSHIPS")
            print()
            fks = [
                dict(r)
                for r in conn.execute(
                    text(
                        """
                        SELECT
                          tc.table_name AS from_table,
                          kcu.column_name AS from_column,
                          ccu.table_name AS foreign_table_name,
                          ccu.column_name AS foreign_column_name,
                          tc.constraint_name
                        FROM information_schema.table_constraints AS tc
                        JOIN information_schema.key_column_usage AS kcu
                          ON tc.constraint_name = kcu.constraint_name
                         AND tc.table_schema = kcu.table_schema
                        JOIN information_schema.constraint_column_usage AS ccu
                          ON ccu.constraint_name = tc.constraint_name
                         AND ccu.table_schema = tc.table_schema
                        WHERE tc.constraint_type = 'FOREIGN KEY'
                          AND tc.table_schema = 'public'
                        ORDER BY tc.table_name, kcu.ordinal_position
                        """
                    )
                ).mappings().all()
            ]
            # Filter to candidates + api_person edges
            focus = set(inspect_tables)

            def _fk_relevant(fk: dict[str, Any]) -> bool:
                return (
                    fk.get("from_table") in focus
                    or fk.get("foreign_table_name") in focus
                    or fk.get("foreign_table_name") == "api_person"
                    or fk.get("from_table") == "api_person"
                )

            rel_fks = [f for f in fks if _fk_relevant(f)]
            print("### FORMAL FK")
            print()
            if not rel_fks:
                print("(ninguna FK formal relevante a candidatas / api_person)")
            else:
                print("| FROM_TABLE | FROM_COLUMN | TO_TABLE | TO_COLUMN | CONSTRAINT |")
                print("|------------|-------------|----------|-----------|------------|")
                for f in rel_fks:
                    print(
                        f"| {f['from_table']} | {f['from_column']} | "
                        f"{f['foreign_table_name']} | {f['foreign_column_name']} | "
                        f"{f['constraint_name']} |"
                    )
            print()
            print("### RELACIÓN INFERIDA — NO FK")
            print()
            # Drop inferred if already covered by formal FK
            formal_pairs = {
                (str(f["from_table"]), str(f["from_column"])) for f in rel_fks
            }
            shown = False
            for line in inferred:
                # parse "…: table.col"
                m = re.search(r":\s*([^.]+)\.(\S+)$", line)
                if m and (m.group(1), m.group(2)) in formal_pairs:
                    continue
                print(f"- {line}")
                shown = True
            if not shown:
                print("(ninguna)")
            print()

            # --- KEYS / INDEXES ---
            print("## KEYS / INDEXES")
            print()
            pks = []
            uniques = []
            indexes = []
            if inspect_tables:
                pks = [
                    dict(r)
                    for r in conn.execute(
                        text(
                            """
                            SELECT tc.table_name, kcu.column_name, tc.constraint_name
                            FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu
                              ON tc.constraint_name = kcu.constraint_name
                             AND tc.table_schema = kcu.table_schema
                            WHERE tc.constraint_type = 'PRIMARY KEY'
                              AND tc.table_schema = 'public'
                              AND tc.table_name = ANY(:tables)
                            ORDER BY tc.table_name, kcu.ordinal_position
                            """
                        ),
                        {"tables": inspect_tables},
                    ).mappings().all()
                ]
                uniques = [
                    dict(r)
                    for r in conn.execute(
                        text(
                            """
                            SELECT tc.table_name, kcu.column_name, tc.constraint_name
                            FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu
                              ON tc.constraint_name = kcu.constraint_name
                             AND tc.table_schema = kcu.table_schema
                            WHERE tc.constraint_type = 'UNIQUE'
                              AND tc.table_schema = 'public'
                              AND tc.table_name = ANY(:tables)
                            ORDER BY tc.table_name, kcu.ordinal_position
                            """
                        ),
                        {"tables": inspect_tables},
                    ).mappings().all()
                ]
                indexes = [
                    dict(r)
                    for r in conn.execute(
                        text(
                            """
                            SELECT
                              tablename AS table_name,
                              indexname AS index_name,
                              indexdef
                            FROM pg_indexes
                            WHERE schemaname = 'public'
                              AND tablename = ANY(:tables)
                            ORDER BY tablename, indexname
                            """
                        ),
                        {"tables": inspect_tables},
                    ).mappings().all()
                ]

            print("### PRIMARY KEYS")
            print()
            for r in pks:
                print(f"- PK {r['table_name']}.{r['column_name']} ({r['constraint_name']})")
            if not pks:
                print("(ninguna en tablas inspeccionadas)")
            print()
            print("### UNIQUE")
            print()
            for r in uniques:
                print(f"- UQ {r['table_name']}.{r['column_name']} ({r['constraint_name']})")
            if not uniques:
                print("(ninguna)")
            print()
            print("### INDEXES (filtrados por ownership / invoice / payment / fechas)")
            print()
            idx_kw = re.compile(
                r"person_id|client_number|partner_number|account_id|invoice|"
                r"payment|fecha|date|due|number",
                re.I,
            )
            any_idx = False
            for r in indexes:
                blob = f"{r.get('index_name')} {r.get('indexdef')}"
                if idx_kw.search(blob) or r["table_name"] in candidates:
                    # no print full indexdef if huge; still OK (no secrets)
                    print(f"- {r['table_name']}: {r['index_name']}")
                    any_idx = True
            if not any_idx:
                print("(ninguno relevante)")
            print()

            # --- SAMPLE ---
            print("## SAMPLE SEMANTICS")
            print()
            sample_targets = [
                t for t in candidates if SAMPLE_TABLE_KW.search(t)
            ][:8]
            if not sample_targets:
                print(
                    "(sin tablas claramente invoice/payment/receipt/statement "
                    "para sample LIMIT 3)"
                )
            for tname in sample_targets:
                cols = columns_by_table.get(tname) or []
                pick = _pick_sample_columns(cols)
                if not pick:
                    print(f"### {tname}")
                    print()
                    print("(sin columnas seguras para sample)")
                    print()
                    continue
                # Quote identifiers safely (only allow alnum/_)
                safe_cols = [c for c in pick if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", c)]
                if not safe_cols:
                    continue
                col_sql = ", ".join(f'"{c}"' for c in safe_cols)
                # table name already from information_schema
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", tname):
                    continue
                q = text(f'SELECT {col_sql} FROM public."{tname}" LIMIT 3')
                try:
                    srows = [dict(r) for r in conn.execute(q).mappings().all()]
                except Exception as exc:
                    print(f"### {tname}")
                    print()
                    print(f"(sample omitido: {type(exc).__name__})")
                    print()
                    continue
                samples[tname] = srows
                print(f"### {tname} (LIMIT 3, cols={', '.join(safe_cols)})")
                print()
                if not srows:
                    print("(0 filas)")
                    print()
                    continue
                for i, row in enumerate(srows, 1):
                    parts = []
                    for k, v in row.items():
                        if v is None:
                            parts.append(f"{k}=null")
                        elif _PII_COL.search(str(k)):
                            parts.append(f"{k}={_anon(v)}")
                        else:
                            sv = str(v)
                            if len(sv) > 80:
                                sv = sv[:77] + "..."
                            parts.append(f"{k}={sv}")
                    print(f"- row{i}: " + "; ".join(parts))
                # Semantic hint (nombre + columnas; no afirmar)
                print()
                print(
                    "HINT: validar manualmente si cada fila es factura / detalle / "
                    "movimiento CC / pago / comprobante. "
                    "NO inferir desde billing_balance."
                )
                print()

            # --- OWNERSHIP ---
            print("## OWNERSHIP")
            print()
            print("Ruta conocida Eko (código):")
            print("  api_person (doc_cuit / client_number) → billing_balance")
            print("  api_service.base_account_number ≈ api_person.client_number")
            print()
            print("Ruta hacia invoice/payment (este probe):")
            if any(f.get("foreign_table_name") == "api_person" for f in rel_fks):
                print("  FORMAL FK hacia api_person detectada (ver RELATIONSHIPS).")
            else:
                print("  Sin FK formal candidata→api_person en el filtro.")
            if any("INFERIDA" in x for x in inferred):
                print("  Hay columnas person_id/client_number/… sin FK (inferidas).")
            print()

            gate, caps = _classify_gate(
                ro_ok=ro_ok,
                reachable=reachable,
                candidates=candidates,
                columns_by_table={k: v for k, v in columns_by_table.items() if k in candidates},
                fks=rel_fks,
            )

            print("## CAPABILITY MATRIX")
            print()
            print(
                "| Capability | Structured source | Ownership | Confidence | Status |"
            )
            print(
                "|------------|-------------------|-----------|------------|--------|"
            )
            for cap, row in caps.items():
                print(
                    f"| {cap} | {row['source']} | {row['ownership']} | "
                    f"{row['confidence']} | {row['status']} |"
                )
            print()
            print("## DECISION GATE")
            print()
            print(gate)
            print()
            print("## SAFETY")
            print()
            print("FILES CHANGED: NONE")
            print("MIGRATIONS: NONE")
            print("WRITES: NONE")
            print("PRODUCTION BEHAVIOR: NONE")
            print()
            print("PROBE COMPLETE")
            return 0
    except Exception as exc:
        print("RO_VERIFIED: NO")
        print("DATABASE_REACHABLE: NO")
        print("PROBE_STATUS: BLOCKED")
        print(f"REASON: {type(exc).__name__}: {str(exc)[:160]}")
        print()
        print("## DECISION GATE")
        print()
        print("GATE E — ACCESS BLOCKED")
        print()
        print("## SAFETY")
        print()
        print("FILES CHANGED: NONE")
        print("MIGRATIONS: NONE")
        print("WRITES: NONE")
        print("PRODUCTION BEHAVIOR: NONE")
        print()
        print("PROBE COMPLETE")
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    # Asegurar cwd/repo en path cuando se corre desde /opt/operations-hub
    raise SystemExit(main())
