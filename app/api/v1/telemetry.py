from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.pipeline import procesar_mensaje
from app.api.v1.deps import get_tenant_context, require_telemetry
from app.api.v1.schemas import TelemetrySimulate, TenantContext
from app.estate.database import get_db
from app.estate import repository as repo

router = APIRouter(tags=["Telemetry"])


@router.get("/telemetry")
def list_telemetry(ctx: TenantContext = Depends(get_tenant_context), db: Session = Depends(get_db)):
    elems = repo.list_telemetry(db, ctx.organizacion_id)
    return {
        "tenant": ctx.organizacion_slug,
        "elementos": [
            {
                "id": e.id,
                "elemento_red": e.elemento_red,
                "metrica": e.metrica,
                "valor_actual": e.valor_actual,
                "estado_actual": e.estado_actual,
                "ultima_actualizacion": e.ultima_actualizacion.isoformat() if e.ultima_actualizacion else "",
            }
            for e in elems
        ],
    }


@router.post("/telemetry/simulate")
async def simulate_telemetry(
    body: TelemetrySimulate,
    ctx: TenantContext = Depends(require_telemetry),
    db: Session = Depends(get_db),
):
    el = repo.simulate_failure(db, ctx.organizacion_id, body.elemento_red)
    if not el:
        raise HTTPException(404, f"Elemento '{body.elemento_red}' no encontrado")

    # Reacción proactiva autónoma (sin mensaje de cliente)
    proactive = await procesar_mensaje(
        db,
        ctx.organizacion_id,
        [],
        f"Anomalía predictiva detectada en {el.elemento_red}. Generar incidente proactivo.",
        creado_por="sistema@predictivo",
        forzar_escalamiento=True,
        admin_global=ctx.es_admin_imowi,
    )
    return {
        "status": "anomalia_simulada",
        "elemento": {
            "elemento_red": el.elemento_red,
            "estado_actual": el.estado_actual,
        },
        "reaccion_autonoma": proactive,
    }
