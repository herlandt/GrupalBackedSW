"""Render de reportes a PDF con reportlab (capa RENDER, devuelve bytes)."""

from collections.abc import Sequence
from datetime import UTC, datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.modules.administracion.reportes.repository import (
    GananciasData,
    PagoFilaData,
    PagoPorEstudianteData,
)

_STYLES = getSampleStyleSheet()


def _doc(titulo: str) -> tuple[BytesIO, SimpleDocTemplate, list[object]]:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=titulo)
    generado = datetime.now(UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M")
    elementos: list[object] = [
        Paragraph(titulo, _STYLES["Title"]),
        Paragraph(f"Generado: {generado} UTC", _STYLES["Normal"]),
        Spacer(1, 16),
    ]
    return buffer, doc, elementos


def _tabla(filas: list[list[str]]) -> Table:
    tabla = Table(filas, repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    return tabla


def ganancias_pdf(data: GananciasData) -> bytes:
    buffer, doc, elementos = _doc("Reporte de ganancias totales")
    elementos.append(
        _tabla(
            [
                ["Métrica", "Valor"],
                ["Total recaudado", f"{data.total:.2f} {data.moneda}"],
                ["Pagos completados", str(data.cantidad_pagos)],
            ]
        )
    )
    doc.build(elementos)
    return buffer.getvalue()


def pagos_por_estudiante_pdf(filas: Sequence[PagoPorEstudianteData]) -> bytes:
    buffer, doc, elementos = _doc("Pagos por estudiante")
    cuerpo = [["Estudiante", "Email", "Total", "# pagos"]]
    for f in filas:
        cuerpo.append([f.nombre, f.email, f"{f.total_pagado:.2f}", str(f.cantidad_pagos)])
    elementos.append(_tabla(cuerpo))
    doc.build(elementos)
    return buffer.getvalue()


def historial_usuario_pdf(nombre: str, filas: Sequence[PagoFilaData]) -> bytes:
    buffer, doc, elementos = _doc(f"Historial de pagos — {nombre}")
    cuerpo = [["Fecha", "Monto", "Moneda", "Estado"]]
    for f in filas:
        cuerpo.append([f.fecha.strftime("%Y-%m-%d %H:%M"), f"{f.monto:.2f}", f.moneda, f.estado])
    elementos.append(_tabla(cuerpo))
    doc.build(elementos)
    return buffer.getvalue()
