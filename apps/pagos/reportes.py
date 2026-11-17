from datetime import date
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Alignment, Font, PatternFill
from PIL import Image

LOGO = Path(__file__).resolve().parents[1] / "areas" / "assets" / "logo-marca.png"
VERDE = "0E6B5A"
VERDE_CLARO = "EEF5F2"
BLANCO = "FFFFFF"
ETIQUETAS_ESTADO = {
    "CONFIRMADO": "Confirmado",
    "REPORTADO": "Reportado",
    "SIN_REPORTE": "Sin reporte",
}


def estado_de_pagos_excel(conjunto, periodo: date, filas):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Estado de pagos"
    hoja.sheet_view.showGridLines = False

    with Image.open(LOGO) as logo:
        logo.thumbnail((112, 80))
        imagen_buffer = BytesIO()
        logo.convert("RGBA").save(imagen_buffer, format="PNG")
    imagen_buffer.seek(0)
    imagen = ExcelImage(imagen_buffer)
    imagen.anchor = "A1"
    hoja.add_image(imagen)
    hoja.row_dimensions[1].height = 30
    hoja.row_dimensions[2].height = 24

    hoja["C1"] = "Estado de pagos del mes"
    hoja["C1"].font = Font(name="Aptos Display", size=18, bold=True, color=VERDE)
    hoja["C2"] = f"{conjunto.nombre} · {periodo:%m/%Y}"
    hoja["C2"].font = Font(name="Aptos", size=11, color="64706C")

    fila_encabezado = 5
    for columna, encabezado in enumerate(("Vivienda", "Estado"), start=1):
        celda = hoja.cell(fila_encabezado, columna, encabezado)
        celda.fill = PatternFill("solid", fgColor=VERDE)
        celda.font = Font(name="Aptos", bold=True, color=BLANCO)
        celda.alignment = Alignment(vertical="center")
    hoja.row_dimensions[fila_encabezado].height = 26

    totales = {estado: 0 for estado in ETIQUETAS_ESTADO}
    for numero_fila, fila in enumerate(filas, start=fila_encabezado + 1):
        estado = fila["estado"]
        totales[estado] += 1
        valores = (fila["unidad_nombre"], ETIQUETAS_ESTADO[estado])
        for columna, valor in enumerate(valores, start=1):
            celda = hoja.cell(numero_fila, columna, valor)
            celda.data_type = "s"
            celda.alignment = Alignment(vertical="center", wrap_text=True)
            if numero_fila % 2 == 0:
                celda.fill = PatternFill("solid", fgColor=VERDE_CLARO)

    fila_totales = max(hoja.max_row + 2, fila_encabezado + 2)
    for columna, encabezado in enumerate(("Estado", "Total"), start=1):
        celda = hoja.cell(fila_totales, columna, encabezado)
        celda.fill = PatternFill("solid", fgColor=VERDE)
        celda.font = Font(name="Aptos", bold=True, color=BLANCO)
    for desplazamiento, (estado, etiqueta) in enumerate(ETIQUETAS_ESTADO.items(), start=1):
        hoja.cell(fila_totales + desplazamiento, 1, etiqueta).data_type = "s"
        hoja.cell(fila_totales + desplazamiento, 2, totales[estado])

    hoja.column_dimensions["A"].width = 34
    hoja.column_dimensions["B"].width = 22
    hoja.freeze_panes = "A6"
    hoja.auto_filter.ref = f"A{fila_encabezado}:B{max(fila_encabezado, fila_encabezado + len(filas))}"

    archivo = BytesIO()
    libro.save(archivo)
    return archivo.getvalue()
