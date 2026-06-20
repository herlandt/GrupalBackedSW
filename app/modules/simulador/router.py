"""Router agregador del módulo Simulador de Defensa y Tribunal Virtual (Sprint 3).

Monta los routers de los submódulos bajo /api/v1 (lo registra app/main.py).
"""

from fastapi import APIRouter

from app.modules.simulador.biometrico.router import router as biometrico_router
from app.modules.simulador.integracion.router import router as integracion_router
from app.modules.simulador.simulaciones.router import router as simulaciones_router
from app.modules.simulador.tribunal.router import router as tribunal_router

router = APIRouter()
router.include_router(simulaciones_router)
router.include_router(tribunal_router)
router.include_router(biometrico_router)
router.include_router(integracion_router)
