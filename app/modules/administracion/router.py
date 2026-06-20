"""Router agregador del módulo Administración del Sistema (Sprint 1).

Monta los routers de los submódulos bajo /api/v1 (lo registra app/main.py).
"""

from fastapi import APIRouter

from app.modules.administracion.dashboard.router import router as dashboard_router
from app.modules.administracion.monitoreo.router import router as monitoreo_router
from app.modules.administracion.pagos.router import router as pagos_router
from app.modules.administracion.reportes.router import router as reportes_router
from app.modules.administracion.suscripciones.router import router as suscripciones_router
from app.modules.administracion.usuarios.router import router as usuarios_router

router = APIRouter()
router.include_router(usuarios_router)
router.include_router(suscripciones_router)
router.include_router(pagos_router)
router.include_router(reportes_router)
router.include_router(dashboard_router)
router.include_router(monitoreo_router)
