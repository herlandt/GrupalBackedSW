"""Router agregador del módulo Auditoría Documental Inteligente (Sprint 2)."""

from fastapi import APIRouter

from app.modules.auditoria_documental.auditoria.router import router as auditoria_router
from app.modules.auditoria_documental.documentos.router import router as documentos_router
from app.modules.auditoria_documental.etica.router import router as etica_router

router = APIRouter()
router.include_router(documentos_router)
router.include_router(auditoria_router)
router.include_router(etica_router)
