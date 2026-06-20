"""Capa API del submódulo Reportes (CU-05 admin + export CU-04 estudiante)."""

from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.database import DbDep
from app.modules.administracion.reportes.schemas import ResumenReportes
from app.modules.administracion.reportes.service import Archivo, ReporteService
from app.modules.administracion.usuarios.dependencies import RequireAdmin, RequireEstudiante

router = APIRouter(prefix="/reportes", tags=["reportes"])

Formato = Literal["pdf", "excel"]


def get_reporte_service(db: DbDep) -> ReporteService:
    return ReporteService(db)


ServiceDep = Annotated[ReporteService, Depends(get_reporte_service)]


def _descarga(archivo: Archivo) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(archivo.contenido),
        media_type=archivo.media_type,
        headers={"Content-Disposition": f'attachment; filename="{archivo.filename}"'},
    )


@router.get("/resumen", response_model=ResumenReportes)
async def resumen(service: ServiceDep, _: RequireAdmin) -> ResumenReportes:
    """Resumen JSON para el gráfico (chart.js) del panel de reportes."""
    return await service.resumen()


@router.get("/ganancias")
async def reporte_ganancias(
    service: ServiceDep, admin: RequireAdmin, formato: Formato = "pdf"
) -> StreamingResponse:
    return _descarga(await service.ganancias(admin, formato))


@router.get("/pagos-por-estudiante")
async def reporte_pagos_por_estudiante(
    service: ServiceDep, admin: RequireAdmin, formato: Formato = "pdf"
) -> StreamingResponse:
    return _descarga(await service.pagos_por_estudiante(admin, formato))


@router.get("/mi-historial/export")
async def export_mi_historial(
    service: ServiceDep, user: RequireEstudiante, formato: Formato = "pdf"
) -> StreamingResponse:
    return _descarga(await service.historial_propio(user, formato))
