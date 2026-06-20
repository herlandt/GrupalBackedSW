"""Lógica del submódulo Reportes (CU-05 + export CU-04).

Separa DATOS (ReporteRepository) de RENDER (renderers/pdf.py, renderers/excel.py).
El service decide qué reporte y qué formato, llama a la query, pasa el resultado al
renderer y devuelve los bytes + el nombre de archivo + el media type.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.service import AuditService
from app.core.exceptions import BusinessRuleError
from app.modules.administracion.reportes.renderers import excel as xlsx
from app.modules.administracion.reportes.renderers import pdf
from app.modules.administracion.reportes.repository import ReporteRepository
from app.modules.administracion.reportes.schemas import (
    FilaPagoEstudiante,
    ResumenGanancias,
    ResumenReportes,
)
from app.modules.administracion.usuarios.models import Usuario

PDF_MEDIA = "application/pdf"
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class Archivo:
    contenido: bytes
    filename: str
    media_type: str


class ReporteService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = ReporteRepository(db)
        self.audit = AuditService(db)

    # --- Resumen JSON (para el gráfico chart.js del frontend) -----------------
    async def resumen(self) -> ResumenReportes:
        ganancias = await self.repo.ganancias_totales()
        por_estudiante = await self.repo.pagos_por_estudiante()
        return ResumenReportes(
            ganancias=ResumenGanancias(
                total=ganancias.total,
                moneda=ganancias.moneda,
                cantidad_pagos=ganancias.cantidad_pagos,
            ),
            por_estudiante=[FilaPagoEstudiante.model_validate(f) for f in por_estudiante],
        )

    # --- Reportes admin (CU-05) ----------------------------------------------
    async def ganancias(self, actor: Usuario, formato: str) -> Archivo:
        data = await self.repo.ganancias_totales()
        archivo = self._render(
            formato,
            base="ganancias_totales",
            pdf_fn=lambda: pdf.ganancias_pdf(data),
            xlsx_fn=lambda: xlsx.ganancias_excel(data),
        )
        await self._auditar(actor.id, "REPORTE_GANANCIAS", formato)
        return archivo

    async def pagos_por_estudiante(self, actor: Usuario, formato: str) -> Archivo:
        filas = await self.repo.pagos_por_estudiante()
        archivo = self._render(
            formato,
            base="pagos_por_estudiante",
            pdf_fn=lambda: pdf.pagos_por_estudiante_pdf(filas),
            xlsx_fn=lambda: xlsx.pagos_por_estudiante_excel(filas),
        )
        await self._auditar(actor.id, "REPORTE_PAGOS_ESTUDIANTE", formato)
        return archivo

    # --- Export del propio historial del estudiante (CU-04) -------------------
    async def historial_propio(self, usuario: Usuario, formato: str) -> Archivo:
        filas = await self.repo.historial_de_usuario(usuario.id)
        archivo = self._render(
            formato,
            base=f"historial_{usuario.id}",
            pdf_fn=lambda: pdf.historial_usuario_pdf(usuario.nombre, filas),
            xlsx_fn=lambda: xlsx.historial_usuario_excel(filas),
        )
        await self._auditar(usuario.id, "EXPORT_HISTORIAL", formato)
        return archivo

    # --- helpers --------------------------------------------------------------
    def _render(
        self,
        formato: str,
        *,
        base: str,
        pdf_fn: Callable[[], bytes],
        xlsx_fn: Callable[[], bytes],
    ) -> Archivo:
        fmt = formato.lower()
        if fmt == "pdf":
            return Archivo(pdf_fn(), f"{base}.pdf", PDF_MEDIA)
        if fmt in ("excel", "xlsx"):
            return Archivo(xlsx_fn(), f"{base}.xlsx", XLSX_MEDIA)
        raise BusinessRuleError(f"Formato no soportado: {formato} (usa pdf o excel)")

    async def _auditar(self, actor_id: int, accion: str, formato: str) -> None:
        await self.audit.log(
            actor_id=actor_id,
            accion=accion,
            entidad="reporte",
            entidad_id=None,
            metadata={"formato": formato.lower()},
        )
