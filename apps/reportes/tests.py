from datetime import date
from io import BytesIO

import pytest
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.pagos.models import PagoDeAdministracion
from apps.permisos.catalogo import Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.unidades.models import Unidad

pytestmark = pytest.mark.django_db
CONTRASENA = "una-clave-larga-2026"
PERIODO = date(2026, 11, 1)


def crear_cliente(correo, rol, conjunto):
    persona = Persona.objects.create(
        tipo_documento=TipoDocumento.CC,
        numero_documento=str(Persona.objects.count() + 1023456789),
        nombres="Laura",
        apellidos="Gómez",
    )
    Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    Usuario.objects.create_user(correo, CONTRASENA, persona)
    cliente = APIClient()
    sesion = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {sesion.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def admin(torres):
    return crear_cliente("admin-reportes@torres.com", Rol.ADMINISTRACION, torres)


@pytest.fixture
def residente(torres):
    return crear_cliente("residente-reportes@torres.com", Rol.RESIDENTE, torres)


def test_reporte_de_pagos_descarga_excel_con_totales_y_solo_datos_del_conjunto(admin, torres):
    otro = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(torres.id):
        confirmada = Unidad.objects.create(nombre="Torre 1 - 101")
        reportada = Unidad.objects.create(nombre="Torre 1 - 102")
        sin_reporte = Unidad.objects.create(nombre="Torre 1 - 103")
        persona = Persona.objects.create(
            tipo_documento=TipoDocumento.CC,
            numero_documento="1034567890",
            nombres="Ana",
            apellidos="Pérez",
        )
        PagoDeAdministracion.objects.create(
            unidad=confirmada,
            periodo=PERIODO,
            reportado_por=persona,
            reportado_en=timezone.now(),
            confirmado_por=persona,
            confirmado_en=timezone.now(),
        )
        PagoDeAdministracion.objects.create(
            unidad=reportada, periodo=PERIODO, reportado_por=persona, reportado_en=timezone.now()
        )
    with usar_conjunto(otro.id):
        Unidad.objects.create(nombre="Vivienda ajena")

    respuesta = admin.get("/api/reportes/pagos.xlsx?periodo=2026-11")
    hoja = load_workbook(BytesIO(respuesta.content)).active
    estados = {hoja.cell(fila, 1).value: hoja.cell(fila, 2).value for fila in range(6, 9)}

    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert respuesta["Content-Disposition"] == 'attachment; filename="estado-pagos-2026-11.xlsx"'
    assert hoja["C1"].value == "Estado de pagos del mes"
    assert hoja.freeze_panes == "A6"
    assert hoja["A5"].value == "Vivienda" and hoja["A5"].font.color.rgb.endswith("FFFFFF")
    assert hoja["A5"].fill.fgColor.rgb.endswith("0E6B5A")
    assert estados == {
        "Torre 1 - 101": "Confirmado",
        "Torre 1 - 102": "Reportado",
        "Torre 1 - 103": "Sin reporte",
    }
    assert "Vivienda ajena" not in [celda.value for fila in hoja.iter_rows() for celda in fila]
    assert [hoja.cell(fila, 1).value for fila in range(11, 14)] == [
        "Confirmado",
        "Reportado",
        "Sin reporte",
    ]
    assert [hoja.cell(fila, 2).value for fila in range(11, 14)] == [1, 1, 1]


def test_reporte_de_pagos_exige_permiso_y_periodo_valido(admin, residente):
    denegado = residente.get("/api/reportes/pagos.xlsx?periodo=2026-11")
    periodo_invalido = admin.get("/api/reportes/pagos.xlsx?periodo=2026-13")
    periodo_ausente = admin.get("/api/reportes/pagos.xlsx")

    assert denegado.status_code == 403
    assert periodo_invalido.status_code == 400
    assert periodo_ausente.status_code == 400


def test_reporte_de_zonas_descarga_pdf_y_exige_permiso(admin, residente, torres, monkeypatch):
    from apps.reportes import views

    invocacion = {}

    def crear_pdf(conjunto, desde, hasta):
        invocacion.update(conjunto=conjunto, desde=desde, hasta=hasta)
        return b"%PDF-prueba"

    monkeypatch.setattr(views.reportes_areas, "uso_zonas_pdf", crear_pdf)
    consulta = "?desde=2026-11-01&hasta=2026-11-30"
    denegado = residente.get(f"/api/reportes/zonas.pdf{consulta}")
    respuesta = admin.get(f"/api/reportes/zonas.pdf{consulta}")
    rango_invalido = admin.get("/api/reportes/zonas.pdf?desde=2026-11-30&hasta=2026-11-01")

    assert denegado.status_code == 403
    assert respuesta.status_code == 200
    assert respuesta["Content-Type"] == "application/pdf"
    assert respuesta["Content-Disposition"] == 'attachment; filename="uso-zonas-comunes.pdf"'
    assert respuesta.content.startswith(b"%PDF")
    assert invocacion["conjunto"].id == torres.id
    assert (invocacion["desde"], invocacion["hasta"]) == (date(2026, 11, 1), date(2026, 11, 30))
    assert rango_invalido.status_code == 400
