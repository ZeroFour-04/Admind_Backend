from io import BytesIO
from pathlib import Path

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from openpyxl.styles import Alignment, Font, PatternFill
from PIL import Image

from apps.reservas.models import Solicitud

LOGO = Path(__file__).resolve().parents[1] / "areas" / "assets" / "logo-marca.png"
VERDE = "0E6B5A"
VERDE_CLARO = "EEF5F2"
BLANCO = "FFFFFF"


def agendas_excel():
    """Genera todas las solicitudes del conjunto activo, sin excluir estados."""
    solicitudes = Solicitud.objects.select_related("area", "persona", "unidad").order_by(
        "fecha", "hora_inicio", "area__nombre", "creada_en"
    )
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Agendas registradas"
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
    hoja.row_dimensions[2].height = 26

    hoja["C1"] = "Agendas de zonas comunes"
    hoja["C1"].font = Font(name="Aptos Display", size=18, bold=True, color=VERDE)
    hoja["C2"] = f"Generado: {timezone.localtime():%d/%m/%Y %H:%M}"
    hoja["C2"].font = Font(name="Aptos", size=10, color="64706C")

    encabezados = [
        "Zona común",
        "Fecha",
        "Hora de inicio",
        "Hora de fin",
        "Estado",
        "Residente",
        "Vivienda",
        "Asistentes",
        "Motivo",
        "Observaciones",
        "Motivo de decisión",
        "Creada en",
        "Enviada en",
    ]
    fila_encabezado = 5
    for columna, encabezado in enumerate(encabezados, start=1):
        celda = hoja.cell(fila_encabezado, columna, encabezado)
        celda.fill = PatternFill("solid", fgColor=VERDE)
        celda.font = Font(name="Aptos", bold=True, color=BLANCO)
        celda.alignment = Alignment(vertical="center", wrap_text=True)
    hoja.row_dimensions[fila_encabezado].height = 30

    for numero_fila, solicitud in enumerate(solicitudes, start=fila_encabezado + 1):
        valores = [
            solicitud.area.nombre,
            solicitud.fecha,
            solicitud.hora_inicio,
            solicitud.hora_fin,
            solicitud.get_estado_display(),
            f"{solicitud.persona.nombres} {solicitud.persona.apellidos}",
            solicitud.unidad.nombre if solicitud.unidad else "",
            solicitud.asistentes,
            solicitud.motivo,
            solicitud.observaciones,
            solicitud.motivo_decision,
            timezone.localtime(solicitud.creada_en).replace(tzinfo=None),
            timezone.localtime(solicitud.enviada_en).replace(tzinfo=None) if solicitud.enviada_en else None,
        ]
        for columna, valor in enumerate(valores, start=1):
            celda = hoja.cell(numero_fila, columna, valor)
            if isinstance(valor, str):
                celda.data_type = "s"
            celda.alignment = Alignment(vertical="top", wrap_text=True)
            if numero_fila % 2 == 0:
                celda.fill = PatternFill("solid", fgColor=VERDE_CLARO)

    anchos = (24, 14, 14, 14, 17, 26, 22, 14, 30, 40, 40, 21, 21)
    for numero, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[hoja.cell(1, numero).column_letter].width = ancho
    hoja.freeze_panes = "A6"
    if hoja.max_row >= fila_encabezado:
        hoja.auto_filter.ref = f"A{fila_encabezado}:M{hoja.max_row}"

    archivo = BytesIO()
    libro.save(archivo)
    archivo.seek(0)
    return archivo.getvalue()
