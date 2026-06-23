"""Render de reportes a PDF con reportlab (capa RENDER, devuelve bytes)."""

from collections.abc import Sequence
from datetime import UTC, datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.modules.administracion.reportes.repository import (
    BitacoraFilaData,
    GananciasData,
    PagoFilaData,
    PagoPorEstudianteData,
    ProgresoEstudianteData,
)

_STYLES = getSampleStyleSheet()


def _corta(texto: str, n: int) -> str:
    """Trunca con elipsis para que las celdas no desborden el ancho de página."""
    return texto if len(texto) <= n else texto[: n - 1] + "…"


def _doc(
    titulo: str, pagesize: tuple[float, float] = A4
) -> tuple[BytesIO, SimpleDocTemplate, list[object]]:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=pagesize, title=titulo)
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


def _tabla_izq(filas: list[list[str]]) -> Table:
    """Tabla con texto alineado a la IZQUIERDA (para columnas de texto, no de números)."""
    tabla = Table(filas, repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return tabla


def reporte_tablas_pdf(
    titulo: str, secciones: Sequence[tuple[str, list[str], list[list[str]]]]
) -> bytes:
    """Renderiza un PDF con varias secciones (subtítulo + tabla). Reutilizable (CU-07)."""
    buffer, doc, elementos = _doc(titulo, pagesize=landscape(A4))
    for subtitulo, encabezados, filas in secciones:
        elementos.append(Paragraph(subtitulo, _STYLES["Heading2"]))
        if filas:
            elementos.append(_tabla_izq([encabezados, *filas]))
        else:
            elementos.append(Paragraph("Sin datos.", _STYLES["Normal"]))
        elementos.append(Spacer(1, 12))
    doc.build(elementos)
    return buffer.getvalue()


def progreso_estudiantes_pdf(filas: Sequence[ProgresoEstudianteData]) -> bytes:
    # Apaisado: varias columnas (conteos + niveles) por estudiante.
    buffer, doc, elementos = _doc("Reporte de progreso de estudiantes", pagesize=landscape(A4))
    elementos.append(Paragraph(f"Total de estudiantes: {len(filas)}", _STYLES["Normal"]))
    elementos.append(Spacer(1, 10))
    cuerpo = [
        ["Estudiante", "Email", "# Doc.", "# Sim.", "Nivel doc.", "Nivel defensa", "Nivel general"]
    ]
    for f in filas:
        cuerpo.append(
            [
                _corta(f.nombre, 24),
                _corta(f.email, 28),
                str(f.total_documentos),
                str(f.total_simulaciones),
                f.nivel_documento or "—",
                f.nivel_defensa or "—",
                f.nivel_general,
            ]
        )
    elementos.append(_tabla_izq(cuerpo))
    doc.build(elementos)
    return buffer.getvalue()


def bitacora_pdf(filas: Sequence[BitacoraFilaData]) -> bytes:
    # Apaisado: la bitácora tiene varias columnas (incl. detalle), gana ancho.
    buffer, doc, elementos = _doc("Reporte de bitácora (auditoría)", pagesize=landscape(A4))
    elementos.append(Paragraph(f"Total de eventos: {len(filas)}", _STYLES["Normal"]))
    elementos.append(Spacer(1, 10))
    cuerpo = [["Fecha", "Actor", "Acción", "Entidad", "ID", "Detalle"]]
    for f in filas:
        cuerpo.append(
            [
                f.fecha.strftime("%Y-%m-%d %H:%M"),
                _corta(f.actor, 26),
                _corta(f.accion, 26),
                _corta(f.entidad, 18),
                str(f.entidad_id) if f.entidad_id is not None else "—",
                _corta(f.detalle, 50),
            ]
        )
    elementos.append(_tabla_izq(cuerpo))
    doc.build(elementos)
    return buffer.getvalue()
