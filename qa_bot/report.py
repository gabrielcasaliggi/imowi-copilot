"""Generación de reporte Markdown QA del bot N1."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from qa_bot.analyzer import AnalisisEscenario


def _pct(n: int, d: int) -> str:
    if d <= 0:
        return "0%"
    return f"{(100.0 * n / d):.1f}%"


def generar_reporte(
    resultados: list[AnalisisEscenario],
    *,
    portal_url: str,
    metodo: str,
    out_path: Path,
) -> Path:
    total = len(resultados)
    resolutivos = sum(1 for r in resultados if r.resolutivo_autonomo)
    prematuros = sum(1 for r in resultados if r.ticket_prematuro)
    bucles = sum(1 for r in resultados if r.bucle_detectado)
    comprension = sum(1 for r in resultados if r.falla_comprension)
    con_ticket = sum(1 for r in resultados if r.ticket_creado_o_ofrecido)
    score_avg = (
        round(sum(r.score_n1 for r in resultados) / total, 3) if total else 0.0
    )

    # Latencias
    lats: list[int] = []
    for r in resultados:
        for t in r.turnos:
            if t.latency_ms is not None:
                lats.append(t.latency_ms)
    lat_avg = int(sum(lats) / len(lats)) if lats else None
    lat_max = max(lats) if lats else None

    # Recomendaciones derivadas
    recs: list[str] = []
    if prematuros:
        recs.append(
            "**Guardrail anti-ticket prematuro**: exigir completar ≥ N pasos del playbook "
            f"(`internet_*`, `wifi`, `movil_*`) antes de ofrecer derivación. Hoy {prematuros}/{total} "
            "escenarios derivaron antes de agotar N1."
        )
    if bucles:
        recs.append(
            "**Anti-bucle**: si el usuario repite el mismo mensaje, no reiniciar el playbook; "
            "reformular el paso actual o avanzar con confirmación explícita "
            "(«¿Seguimos con el reinicio de la ONT?»). "
            f"Detectado en {bucles} escenario(s)."
        )
    if comprension:
        recs.append(
            "**Robustez NLP**: ampliar sinónimos coloquiales/typos («interntt», «no anda nada») "
            "en `clasificar_intencion` y en el intérprete conversacional. "
            f"Fallos de comprensión en {comprension} escenario(s)."
        )
    recs.append(
        "**Modo invitado + facturación**: ante saldo/factura/QR, priorizar CTA a login DNI+OTP "
        "antes de abrir ticket de facturación; ofrecer guía genérica de pago QR Fiserv sin cuenta."
    )
    recs.append(
        "**Prompt system N1**: reforzar política «nunca crear ticket en el primer turno técnico»; "
        "primero menú de servicio → triaje de acceso → 2–4 pasos de autodiagnóstico → "
        "solo entonces confirmar handoff."
    )
    recs.append(
        "**Métrica operativa**: exponer en analytics `% resolución N1 sin ticket` y "
        "`tickets creados en turno ≤2` como alerta de regresión de prompt/flujos."
    )
    recs.append(
        "**Pedido de humano**: si el usuario pide operador sin síntoma, responder con menú "
        "(internet / móvil / factura) y 1 pregunta de diagnóstico; no abrir ticket por la sola "
        "solicitud de humano salvo keywords de emergencia (caída masiva B2B, seguridad)."
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = []
    lines += [
        "# Reporte QA — Bot N1 Portal Ecolan / Cooperativa Batán",
        "",
        f"**Fecha:** {now}  ",
        f"**Portal:** {portal_url}  ",
        f"**Modo de ingreso:** Invitado / Guest  ",
        f"**Método de ejecución:** {metodo}  ",
        f"**Escenarios ejecutados:** {total}",
        "",
        "---",
        "",
        "## 1. Resumen ejecutivo",
        "",
        f"El bot en modo invitado **resuelve de forma autónoma (criterio N1) el {_pct(resolutivos, total)}** "
        f"de los escenarios de la matriz ({resolutivos}/{total}). "
        f"Score N1 promedio: **{score_avg}** (0–1).",
        "",
        "| Métrica | Valor |",
        "|---------|-------|",
        f"| Resolutividad autónoma N1 | **{_pct(resolutivos, total)}** ({resolutivos}/{total}) |",
        f"| Escenarios con ticket ofrecido/creado | {_pct(con_ticket, total)} ({con_ticket}/{total}) |",
        f"| Tickets/derivaciones **prematuras** | **{_pct(prematuros, total)}** ({prematuros}/{total}) |",
        f"| Bucles / respuestas repetidas | {_pct(bucles, total)} ({bucles}/{total}) |",
        f"| Fallas de comprensión | {_pct(comprension, total)} ({comprension}/{total}) |",
        f"| Score N1 promedio | {score_avg} |",
    ]
    if lat_avg is not None:
        lines.append(f"| Latencia promedio por turno | {lat_avg} ms (máx {lat_max} ms) |")
    lines += ["", "### Veredicto", ""]

    if resolutivos / total >= 0.75 and prematuros / total <= 0.2 if total else False:
        lines.append(
            "**GO condicional para piloto N1**: buena contención técnica en triaje, "
            "con mejoras prioritarias en anti-ticket prematuro y modo invitado/facturación."
        )
    elif resolutivos / total >= 0.5:
        lines.append(
            "**NO-GO suave**: resolutividad intermedia. El bot inicia bien muchos flujos N1, "
            "pero la derivación prematura o fallas puntuales comprometen el objetivo de "
            "reducir tickets humanos innecesarios."
        )
    else:
        lines.append(
            "**NO-GO**: resolutividad autónoma insuficiente. Priorizar endurecimiento de playbooks "
            "y políticas de escalamiento antes de ampliar el canal."
        )

    lines += ["", "---", "", "## 2. Matriz de resultados", "", 
              "| ID | Escenario | Categoría | Score | Resolutivo N1 | Ticket | Prematuro | Bucle | Comprensión |",
              "|----|-----------|-----------|-------|---------------|--------|-----------|-------|-------------|"]
    for r in resultados:
        lines.append(
            f"| {r.escenario_id} | {r.nombre} | `{r.categoria}` | {r.score_n1} | "
            f"{'✅' if r.resolutivo_autonomo else '❌'} | "
            f"{'sí' if r.ticket_creado_o_ofrecido else 'no'} | "
            f"{'⚠️ sí' if r.ticket_prematuro else 'no'} | "
            f"{'⚠️' if r.bucle_detectado else 'ok'} | "
            f"{'⚠️' if r.falla_comprension else 'ok'} |"
        )

    lines += ["", "---", "", "## 3. Detalle por escenario", ""]
    for r in resultados:
        lines += [
            f"### {r.escenario_id} — {r.nombre}",
            "",
            f"- **Categoría:** `{r.categoria}`",
            f"- **Resolutivo autónomo:** {'Sí' if r.resolutivo_autonomo else 'No'}",
            f"- **Score N1:** {r.score_n1}",
            f"- **Ticket ofrecido/creado:** {'Sí' if r.ticket_creado_o_ofrecido else 'No'}",
            f"- **Ticket prematuro:** {'Sí' if r.ticket_prematuro else 'No'}",
            f"- **Bucle:** {'Sí' if r.bucle_detectado else 'No'}",
            f"- **Falla comprensión:** {'Sí' if r.falla_comprension else 'No'}",
            "",
        ]
        if r.resumen_fallas:
            lines.append("**Hallazgos:**")
            for h in r.resumen_fallas:
                lines.append(f"- {h}")
            lines.append("")
        lines.append("<details><summary>Transcripción</summary>")
        lines.append("")
        for turn in r.turnos:
            lat = f" _{turn.latency_ms} ms_" if turn.latency_ms is not None else ""
            lines.append(f"**Usuario:** {turn.usuario}")
            lines.append("")
            lines.append(f"**Bot:** {turn.respuesta}{lat}")
            lines.append("")
            lines.append(
                f"- Resolvió en chat: {'sí' if turn.resolvio_en_chat else 'no'} · "
                f"Autodiagnóstico: {'sí' if turn.instruyo_autodiagnostico else 'no'} · "
                f"Derivó: {'sí' if turn.derivo_ticket else 'no'}"
            )
            lines.append("")
        lines.append("</details>")
        lines.append("")

    lines += [
        "---",
        "",
        "## 4. Criterios de evaluación aplicados",
        "",
        "Para cada turno se evaluó:",
        "",
        "1. **¿Resolvió la duda en el chat?** — Instrucciones accionables, menú de triaje o respuesta directa.",
        "2. **¿Instruyó autodiagnóstico?** — Reinicio ONT/router, luces PON/LOS/PoE, APN, QR Fiserv, etc.",
        "3. **¿Derivó a ticket humano sin N1?** — Oferta/creación de ticket, agente u operador antes de agotar playbook.",
        "4. **¿Fallas de comprensión o bucles?** — Respuestas vacías/erróneas o repetición del mismo paso sin avance.",
        "",
        "---",
        "",
        "## 5. Fallas principales encontradas",
        "",
    ]

    # Agrupar fallas
    all_fallas: dict[str, list[str]] = {}
    for r in resultados:
        for h in r.resumen_fallas:
            key = h.split(": ", 1)[-1]
            all_fallas.setdefault(key, []).append(r.escenario_id)
    if not all_fallas:
        lines.append("No se registraron fallas duras según los heurísticos de esta corrida.")
    else:
        lines.append("| Falla | Escenarios |")
        lines.append("|-------|------------|")
        for k, ids in sorted(all_fallas.items(), key=lambda x: -len(x[1])):
            lines.append(f"| {k} | {', '.join(ids)} |")

    lines += [
        "",
        "---",
        "",
        "## 6. Recomendaciones de prompt engineering y flujos",
        "",
    ]
    for i, rec in enumerate(recs, 1):
        lines.append(f"{i}. {rec}")

    lines += [
        "",
        "### Cambios concretos sugeridos en código/flujo",
        "",
        "1. En `app/domain/flujos_abonado.py`: marcar pasos `derivar_*` / `turno_campo_*` como "
        "`requiere_min_pasos_previos` y bloquear skip desde el clasificador LLM.",
        "2. En `app/services/canal_abonado.py` (modo invitado): si intención ∈ {facturacion, corte_deuda} "
        "→ respuesta plantilla con guía QR + CTA «Identificate con DNI» antes de handoff.",
        "3. En el system prompt del motor conversacional: añadir regla explícita "
        "`crear_ticket=false` mientras `paso_idx < len(playbook)-1` salvo intención B2B caída o "
        "pedido explícito post-diagnóstico.",
        "4. Detectar `mensaje_repetido` en el intérprete y emitir variante de reformulación "
        "en lugar de reenviar el mismo `PasoPlaybook.pregunta`.",
        "5. Ampliar vocabulario de `clasificar_intencion` para typos frecuentes de internet/móvil.",
        "",
        "---",
        "",
        "## 7. Cómo reproducir",
        "",
        "```bash",
        "# Desde la raíz del repo",
        ".venv/bin/pip install playwright httpx",
        ".venv/bin/playwright install chromium",
        ".venv/bin/python -m qa_bot.run_qa --mode both",
        "# Solo API (más rápido, mismo backend de producción)",
        ".venv/bin/python -m qa_bot.run_qa --mode api",
        "# Solo UI Playwright (invitado + chat)",
        ".venv/bin/python -m qa_bot.run_qa --mode playwright --scenarios E01,E08,E13",
        "```",
        "",
        "Artefactos: `qa_bot/artifacts/` (JSON de resultados + screenshots).",
        "",
        "---",
        "",
        "*Generado automáticamente por el harness QA N1 (`qa_bot/`).*",
        "",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
