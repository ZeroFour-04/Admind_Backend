from datetime import date
from io import BytesIO
from pathlib import Path

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.areas.models import ocupacion_areas

LOGO = Path(__file__).resolve().parent / "assets" / "logo-marca.png"
VERDE = colors.HexColor("#0E6B5A")
VERDE_CLARO = colors.HexColor("#EEF5F2")


def uso_zonas_pdf(conjunto, desde: date, hasta: date):
    filas = ocupacion_areas(conjunto.id, desde, hasta)
    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=34 * mm,
        bottomMargin=18 * mm,
        title="Uso de zonas comunes",
        author="AdMind",
    )
    estilos = getSampleStyleSheet()
    datos = [["Zona común", "Reservas confirmadas", "Horas reservadas"]]
    datos.extend(
        [
            fila["area_nombre"],
            fila["reservas"],
            f'{fila["horas_reservadas"]:.2f}',
        ]
        for fila in filas
    )
    if not filas:
        datos.append(["Sin reservas en el rango seleccionado", "", ""])

    tabla = Table(datos, colWidths=(160 * mm, 48 * mm, 48 * mm), repeatRows=1)
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), VERDE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("LEADING", (0, 0), (-1, -1), 14),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [VERDE_CLARO, colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D6DCDA")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    documento.build(
        [Paragraph("Uso de zonas comunes", estilos["Title"]), Spacer(1, 8 * mm), tabla],
        onFirstPage=lambda canvas, doc: _encabezado_y_pie(canvas, doc, conjunto, desde, hasta),
        onLaterPages=lambda canvas, doc: _encabezado_y_pie(canvas, doc, conjunto, desde, hasta),
    )
    return buffer.getvalue()


def _encabezado_y_pie(canvas, documento, conjunto, desde, hasta):
    pagina_ancho, pagina_alto = landscape(A4)
    canvas.saveState()
    canvas.drawImage(str(LOGO), 18 * mm, pagina_alto - 25 * mm, width=17 * mm, height=17 * mm, mask="auto")
    canvas.setFillColor(VERDE)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(39 * mm, pagina_alto - 15 * mm, conjunto.nombre)
    canvas.setFillColor(colors.HexColor("#4B5754"))
    canvas.setFont("Helvetica", 9)
    canvas.drawString(39 * mm, pagina_alto - 21 * mm, f"Rango: {desde:%d/%m/%Y} – {hasta:%d/%m/%Y}")
    canvas.drawRightString(
        pagina_ancho - 18 * mm,
        pagina_alto - 21 * mm,
        f"Generado: {timezone.localtime():%d/%m/%Y %H:%M}",
    )
    canvas.setStrokeColor(colors.HexColor("#D6DCDA"))
    canvas.line(18 * mm, 13 * mm, pagina_ancho - 18 * mm, 13 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(pagina_ancho - 18 * mm, 8 * mm, f"Página {documento.page}")
    canvas.restoreState()
