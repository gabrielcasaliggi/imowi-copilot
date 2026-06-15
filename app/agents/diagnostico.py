"""Agente 2 — diagnóstico con KB documental, JSC y base operativa de anomalías."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.estate import repository as repo
from app.jsc import connector as jsc
from app.services import knowledge_unified


def _correlacionar_anomalia(el, geo: str, sintoma: str) -> bool:
    nombre = el.elemento_red.lower()
    geo_n = geo.replace("ü", "u")
    nombre_n = nombre.replace("ü", "u")
    if geo and geo_n in nombre_n:
        return True
    if "roaming" in sintoma and "roaming" in nombre:
        return True
    if "red" in sintoma or "datos" in sintoma or "señal" in sintoma:
        return el.estado_actual != "Normal"
    return False


def ejecutar_diagnostico(
    db: Session,
    org_id: str,
    datos_triaje: dict,
    query: str,
    *,
    admin_global: bool = False,
) -> dict:
    traces: list[str] = []
    traces.append("⚙️ [Agente Diagnóstico]: Iniciando análisis con KB documental, JSC y anomalías vigentes…")

    ficha = None
    linea_n = datos_triaje.get("linea") or ""
    if linea_n:
        row = jsc.buscar_linea(db, org_id, linea_n, admin_global=admin_global)
        ficha = jsc.ficha_linea(row)
        if ficha:
            traces.append(
                f"📡 [JSC]: Línea {ficha['msisdn']} — {ficha['abonado']} | Plan {ficha['plan']} | {ficha['estado_linea']}"
            )
            if ficha.get("estado_cuenta") not in ("Al día", "OK"):
                traces.append(
                    f"💰 [Contable]: Estado cuenta «{ficha['estado_cuenta']}» — verificar antes de escalar a red"
                )
        else:
            traces.append(
                f"📡 [JSC]: Línea {linea_n} no encontrada en la réplica local — continúo con triaje operativo"
            )

    consulta = query or datos_triaje.get("sintoma", "")
    kb = knowledge_unified.buscar_unificado(db, org_id, consulta)
    kb_ctx = kb.get("kb_contexto", "")
    if kb.get("encontrado"):
        fuentes = []
        if kb.get("tenant_count"):
            fuentes.append(f"{kb['tenant_count']} tenant")
        if kb.get("rag", {}).get("encontrado"):
            fuentes.append("global RAG")
        traces.append(f"📚 [KB Documental]: Contexto encontrado ({', '.join(fuentes) or 'match'}) — modo {kb.get('modo')}.")

    anomalias = repo.telemetry_anomalies(db, org_id)
    geo = (datos_triaje.get("geolocalizacion") or "").lower()
    sintoma = (datos_triaje.get("sintoma") or "").lower()

    alertas_red: list[dict] = []
    elemento_afectado = ""
    anomalia_red_global = bool(anomalias)
    anomalia_red_correlacionada = False

    for el in anomalias:
        correlacionada = _correlacionar_anomalia(el, geo, sintoma)
        alertas_red.append({
            "elemento_red": el.elemento_red,
            "metrica": el.metrica,
            "valor_actual": el.valor_actual,
            "estado_actual": el.estado_actual,
            "correlacionada": correlacionada,
        })
        traces.append(
            f"⚠️ [Base de Anomalías]: {el.elemento_red} — {el.metrica}={el.valor_actual}"
            + (" (correlacionada)" if correlacionada else " (global)")
        )
        if correlacionada:
            anomalia_red_correlacionada = True
            elemento_afectado = el.elemento_red

    if not anomalia_red_correlacionada:
        for el in repo.list_telemetry(db, org_id):
            if _correlacionar_anomalia(el, geo, sintoma) and el.estado_actual != "Normal":
                traces.append(f"⚙️ [Base de Anomalías]: Correlación con {el.elemento_red}.")
                anomalia_red_correlacionada = True
                elemento_afectado = el.elemento_red
                break

    diagnostico = "Problema aparentemente aislado al abonado."
    if anomalia_red_correlacionada:
        diagnostico = (
            f"Anomalía correlacionada en infraestructura ({elemento_afectado}). "
            "El inconveniente del cliente puede estar vinculado a incidencia de red."
        )
    elif anomalia_red_global:
        diagnostico = (
            "Hay anomalías generales en la red del tenant. "
            "Verificar si impactan a este abonado antes de escalar."
        )
    elif kb.get("encontrado"):
        diagnostico = f"Caso alineado con KB «{kb.get('titulo_principal', '')}». Troubleshooting guiado aplicable."

    categoria = "General"
    if kb.get("articulos"):
        categoria = kb["articulos"][0].get("categoria", "General")

    if ficha and ficha.get("estado_linea") == "Suspendida":
        diagnostico = "Línea suspendida en JSC. Verificar estado de cuenta antes de troubleshooting de red."

    tickets_similares: list[dict] = []
    ticket_abierto = None
    if linea_n:
        tickets_similares = repo.buscar_tickets_similares(db, org_id, linea_n, sintoma or consulta)
        ticket_abierto_row = repo.ticket_abierto_por_linea_categoria(db, org_id, linea_n, categoria)
        if ticket_abierto_row:
            ticket_abierto = repo._ticket_resumen(ticket_abierto_row)
            traces.append(f"📋 [Memoria]: Ticket abierto {ticket_abierto['id']} para línea {linea_n}.")
        if tickets_similares:
            traces.append(
                f"📋 [Memoria]: {len(tickets_similares)} reclamo(s) previo(s) para línea {linea_n}."
            )

    return {
        "diagnostico": diagnostico,
        "anomalia_red": anomalia_red_correlacionada,
        "anomalia_red_global": anomalia_red_global,
        "anomalia_red_correlacionada": anomalia_red_correlacionada,
        "elemento_afectado": elemento_afectado,
        "alertas_red": alertas_red,
        "tickets_similares": tickets_similares,
        "ticket_abierto_existente": ticket_abierto,
        "categoria": categoria,
        "kb_articulos": [a.get("titulo", "") for a in kb.get("articulos", [])],
        "kb_contexto": kb_ctx,
        "kb_resultado": kb,
        "ficha_jsc": ficha,
        "traces": traces,
    }
