"""Punto de entrada de la aplicación. Solo arma (wiring) las piezas;
no contiene lógica de negocio.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.core.exceptions import BusinessRuleError, ResourceNotFoundError
from app.modules.administracion.router import router as administracion_router
from app.modules.auditoria_documental.router import router as auditoria_documental_router
from app.modules.simulador.router import router as simulador_router

app = FastAPI(title=settings.app_name, debug=settings.debug)

# El frontend (web y móvil) vive en orígenes separados.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Archivos subidos en desarrollo (storage local). En producción se sirven desde S3.
Path(settings.local_media_dir).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.local_media_dir), name="media")

# Traduce las excepciones del dominio a respuestas HTTP.
# Así los services se mantienen libres de detalles de HTTP.


@app.exception_handler(ResourceNotFoundError)
def handle_not_found(request: Request, exc: ResourceNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(BusinessRuleError)
def handle_business_rule(request: Request, exc: BusinessRuleError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness: confirma que la app responde."""
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
async def ready() -> JSONResponse:
    """Readiness: confirma que la app puede comunicarse con la base de datos."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "db_unavailable"})
    return JSONResponse(status_code=200, content={"status": "ready"})


app.include_router(administracion_router, prefix="/api/v1")
app.include_router(auditoria_documental_router, prefix="/api/v1")
app.include_router(simulador_router, prefix="/api/v1")
