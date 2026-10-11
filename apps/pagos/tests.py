"""Pruebas de HU-35: el pago de la administración por vivienda y mes, con comprobante y mora.

`periodos` y `mora` (con la hora simulada) se prueban sin pasar por HTTP cuando se puede.
"""
import uuid
from datetime import date, time, timedelta
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.areas.models import Area
from apps.auditoria.models import Registro
from apps.comun.aislamiento.contexto import usar_conjunto
from apps.conjuntos.models import Conjunto
from apps.cuentas.models import TokenDeSesion, Usuario
from apps.pagos import mora, periodos, servicios
from apps.pagos.models import Comprobante, PagoDeAdministracion
from apps.permisos.catalogo import PERMISOS, PERMISOS_POR_ROL, PERMISOS_SENSIBLES, Rol
from apps.permisos.models import Asignacion
from apps.personas.models import Persona, TipoDocumento
from apps.reglas.evaluador import evaluar
from apps.reglas.models import Regla
from apps.reservas.models import Solicitud
from apps.unidades.models import TipoVinculo, Unidad, VinculoUnidad

pytestmark = pytest.mark.django_db

CONTRASENA = "una-clave-larga-2026"
PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
HOY = timezone.localdate()
ESTE_MES = HOY.replace(day=1)
ESTE_MES_TEXTO = periodos.texto_de(ESTE_MES)


# periodos: funciones puras, sin base de datos


def test_un_periodo_va_y_vuelve_entre_texto_y_fecha():
    assert periodos.periodo_de("2026-10") == date(2026, 10, 1)
    assert periodos.texto_de(date(2026, 10, 1)) == "2026-10"
    assert periodos.texto_de(periodos.periodo_de("2026-01")) == "2026-01"


@pytest.mark.parametrize("texto", ["2026-13", "2026-00", "26-10", "2026-1", "octubre", "", "2026/10", "1999-05", "2101-01", None])
def test_un_periodo_mal_escrito_no_sirve(texto):
    with pytest.raises(ValueError):
        periodos.periodo_de(texto)


def test_sumar_meses_cruza_el_cambio_de_anio_en_los_dos_sentidos():
    assert periodos.sumar_meses(date(2026, 11, 1), 3) == date(2027, 2, 1)
    assert periodos.sumar_meses(date(2026, 2, 1), -3) == date(2025, 11, 1)
    assert periodos.sumar_meses(date(2026, 10, 1), 0) == date(2026, 10, 1)
    assert periodos.sumar_meses(date(2026, 1, 1), -12) == date(2025, 1, 1)


def test_el_periodo_actual_es_el_dia_uno_del_mes_de_hoy():
    assert periodos.actual(date(2026, 10, 27)) == date(2026, 10, 1)


def test_entre_incluye_los_dos_extremos_y_queda_vacio_si_van_al_reves():
    assert periodos.entre(date(2026, 11, 1), date(2027, 1, 1)) == [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)]
    assert periodos.entre(date(2026, 10, 1), date(2026, 10, 1)) == [date(2026, 10, 1)]
    assert periodos.entre(date(2026, 10, 1), date(2026, 9, 1)) == []


def test_el_buscador_ignora_tildes_y_mayusculas():
    assert servicios.sin_tildes("GÓMEZ Peña") == "gomez pena"


# Datos de prueba


def crear_persona(nombres, apellidos, documento):
    return Persona.objects.create(
        tipo_documento=TipoDocumento.CC, numero_documento=documento, nombres=nombres, apellidos=apellidos
    )


def crear_usuario(correo, persona, rol, conjunto):
    Asignacion.objects.create(persona=persona, rol=rol, conjunto=conjunto)
    Usuario.objects.create_user(correo, CONTRASENA, persona)
    return persona


def cliente_para(correo):
    """Sesión con el segundo factor dado por verificado: su flujo se prueba en cuentas."""
    cliente = APIClient()
    respuesta = cliente.post("/auth/login/", {"correo": correo, "contrasena": CONTRASENA}, format="json")
    cliente.credentials(HTTP_AUTHORIZATION=f"Token {respuesta.json()['token']}")
    TokenDeSesion.objects.filter(usuario__correo=correo).update(dos_factores_verificado=True)
    return cliente


@pytest.fixture
def torres():
    return Conjunto.objects.create(nombre="Torres del Río")


@pytest.fixture
def viviendas(torres):
    with usar_conjunto(torres.id):
        return Unidad.objects.create(nombre="Torre 1 – 101"), Unidad.objects.create(nombre="Torre 1 – 102")


@pytest.fixture
def personas(torres, viviendas):
    """Laura es propietaria del 101 y Pedro lo arrienda (no reside); Lucía es propietaria del 102."""
    laura = crear_usuario("laura@torres.com", crear_persona("Laura", "Gómez", "1023456789"), Rol.RESIDENTE, torres)
    pedro = crear_usuario("pedro@torres.com", crear_persona("Pedro", "Ríos", "1098765432"), Rol.RESIDENTE, torres)
    lucia = crear_usuario("lucia@torres.com", crear_persona("Lucía", "Torres", "52111222"), Rol.RESIDENTE, torres)
    with usar_conjunto(torres.id):
        VinculoUnidad.objects.create(persona=laura, unidad=viviendas[0], tipo=TipoVinculo.PROPIETARIO, reside=True)
        VinculoUnidad.objects.create(persona=pedro, unidad=viviendas[0], tipo=TipoVinculo.ARRENDATARIO, reside=False)
        VinculoUnidad.objects.create(persona=lucia, unidad=viviendas[1], tipo=TipoVinculo.PROPIETARIO, reside=True)
    return {"laura": laura, "pedro": pedro, "lucia": lucia}


@pytest.fixture
def laura(personas):
    return cliente_para("laura@torres.com")


@pytest.fixture
def pedro(personas):
    return cliente_para("pedro@torres.com")


@pytest.fixture
def lucia(personas):
    return cliente_para("lucia@torres.com")


@pytest.fixture
def andres(torres):
    crear_usuario("andres@torres.com", crear_persona("Andrés", "Ruiz", "79000111"), Rol.ADMINISTRACION, torres)
    return cliente_para("andres@torres.com")


@pytest.fixture
def carlos(torres):
    crear_usuario("carlos@torres.com", crear_persona("Carlos", "Mora", "79000222"), Rol.SECRETARIA, torres)
    return cliente_para("carlos@torres.com")


@pytest.fixture
def victor(torres):
    crear_usuario("victor@torres.com", crear_persona("Víctor", "Peña", "79000333"), Rol.VIGILANCIA, torres)
    return cliente_para("victor@torres.com")


def tabla(cliente, **consulta):
    return cliente.get("/pagos/administracion/", consulta)


def fila_de(respuesta, vivienda):
    return next(f for f in respuesta.json()["filas"] if f["unidad"]["id"] == str(vivienda.id))


def marcar(cliente, vivienda, periodo=ESTE_MES_TEXTO, confirmado=True):
    return cliente.post(
        f"/pagos/administracion/{vivienda.id}/{periodo}/confirmacion/", {"confirmado": confirmado}, format="json"
    )


def subir(nombre, contenido):
    return SimpleUploadedFile(nombre, contenido, content_type="application/octet-stream")


def reportar(cliente, vivienda, archivo, periodo=ESTE_MES_TEXTO):
    return cliente.post(
        "/pagos/administracion/reportes/",
        {"unidad": str(vivienda.id), "periodo": periodo, "archivo": archivo},
        format="multipart",
    )


def en_la_base(torres):
    with usar_conjunto(torres.id):
        return list(PagoDeAdministracion.objects.order_by("periodo"))


# F1: la tabla, el buscador y el check


def test_hay_una_fila_por_vivienda_aunque_no_tenga_pago(andres, viviendas):
    respuesta = tabla(andres, periodo="2026-10")

    assert respuesta.status_code == 200
    assert respuesta.json()["periodo"] == "2026-10"
    assert len(respuesta.json()["filas"]) == 2
    primera = fila_de(respuesta, viviendas[0])
    assert primera["estado"] == "sin_reporte"
    assert primera["comprobante"] is None
    assert (primera["reportado_por"], primera["confirmado_por"]) == (None, None)


def test_sin_periodo_la_tabla_es_la_del_mes_actual(andres, viviendas):
    assert tabla(andres).json()["periodo"] == ESTE_MES_TEXTO


def test_un_periodo_mal_escrito_responde_400_bajo_periodo(andres, viviendas):
    for texto in ("octubre", "2026-13", "26-10"):
        respuesta = tabla(andres, periodo=texto)

        assert respuesta.status_code == 400
        assert "periodo" in respuesta.json()
    assert marcar(andres, viviendas[0], periodo="2026-13").status_code == 400


def test_cada_fila_trae_los_nombres_de_quien_tiene_vinculo_y_nunca_un_documento(andres, viviendas, personas):
    respuesta = tabla(andres)

    primera = fila_de(respuesta, viviendas[0])
    assert sorted((p["nombre"], p["tipo"]) for p in primera["personas"]) == [
        ("Laura Gómez", "propietario"),
        ("Pedro Ríos", "arrendatario"),
    ]
    cuerpo = respuesta.content.decode()
    for documento in ("1023456789", "1098765432", "52111222", "79000111"):
        assert documento not in cuerpo


@pytest.mark.parametrize(
    ("buscado", "esperadas"),
    [
        ("101", ["Torre 1 – 101"]),
        ("102", ["Torre 1 – 102"]),
        ("gomez", ["Torre 1 – 101"]),
        ("GÓMEZ", ["Torre 1 – 101"]),
        ("lucia torres", ["Torre 1 – 102"]),
        ("laura 101", ["Torre 1 – 101"]),
        ("laura 102", []),
        ("1.023.456.789", ["Torre 1 – 101"]),
        ("1023456789", ["Torre 1 – 101"]),
        ("10234", ["Torre 1 – 101"]),
        ("52111", ["Torre 1 – 102"]),
        # Con menos de 5 dígitos no es un documento: «1023» no encuentra a nadie.
        ("1023", []),
        ("nadie", []),
        ("", ["Torre 1 – 101", "Torre 1 – 102"]),
    ],
)
def test_el_buscador_filtra_en_el_servidor_por_vivienda_nombre_o_documento(andres, viviendas, personas, buscado, esperadas):
    respuesta = tabla(andres, buscar=buscado)

    assert [f["unidad"]["nombre"] for f in respuesta.json()["filas"]] == esperadas


def test_la_consulta_no_queda_en_la_respuesta(andres, viviendas, personas):
    cuerpo = tabla(andres, buscar="1023456789").content.decode()

    assert "1023456789" not in cuerpo


def test_administracion_marca_y_desmarca_y_queda_en_la_auditoria(andres, torres, viviendas):
    marcada = marcar(andres, viviendas[0], "2026-10")

    assert marcada.status_code == 200
    assert marcada.json()["estado"] == "confirmado"
    assert marcada.json()["confirmado_por"] == "Andrés Ruiz" and marcada.json()["confirmado_en"]
    pago = en_la_base(torres)[0]
    assert (pago.periodo, pago.confirmado_por.nombres) == (date(2026, 10, 1), "Andrés")
    with usar_conjunto(torres.id):
        registro = Registro.objects.get(accion="pago.confirmar")
    assert registro.actor.nombres == "Andrés" and registro.antes == {"confirmado": False}

    desmarcada = marcar(andres, viviendas[0], "2026-10", confirmado=False)

    assert desmarcada.json()["estado"] == "sin_reporte"
    assert desmarcada.json()["confirmado_por"] is None
    pago = en_la_base(torres)[0]
    assert (pago.confirmado_por_id, pago.confirmado_en) == (None, None)
    with usar_conjunto(torres.id):
        desmarcado = Registro.objects.get(accion="pago.desmarcar")
    # Quién lo había puesto queda en la auditoría.
    assert desmarcado.antes["confirmado"] is True and desmarcado.antes["confirmado_por"]


def test_marcar_dos_veces_deja_una_fila_y_un_registro(andres, torres, viviendas):
    assert marcar(andres, viviendas[0], "2026-10").status_code == 200
    assert marcar(andres, viviendas[0], "2026-10").status_code == 200

    assert len(en_la_base(torres)) == 1
    with usar_conjunto(torres.id):
        assert Registro.objects.filter(accion="pago.confirmar").count() == 1


def test_quitar_un_check_que_no_existe_no_crea_ni_audita_nada(andres, torres, viviendas):
    respuesta = marcar(andres, viviendas[0], "2026-10", confirmado=False)

    assert respuesta.status_code == 200 and respuesta.json()["estado"] == "sin_reporte"
    assert en_la_base(torres) == []
    with usar_conjunto(torres.id):
        assert not Registro.objects.filter(accion__startswith="pago.").exists()


def test_la_tabla_de_otro_mes_no_trae_el_check_de_este(andres, viviendas):
    marcar(andres, viviendas[0], "2026-10")

    assert fila_de(tabla(andres, periodo="2026-10"), viviendas[0])["estado"] == "confirmado"
    assert fila_de(tabla(andres, periodo="2026-11"), viviendas[0])["estado"] == "sin_reporte"


def test_secretaria_ve_la_tabla_y_recibe_403_al_marcar(carlos, torres, viviendas):
    assert tabla(carlos).status_code == 200

    respuesta = marcar(carlos, viviendas[0])

    assert respuesta.status_code == 403
    assert en_la_base(torres) == []


def test_un_residente_y_vigilancia_reciben_403_en_la_tabla(laura, victor, viviendas):
    assert tabla(laura).status_code == 403
    assert tabla(victor).status_code == 403
    assert marcar(laura, viviendas[0]).status_code == 403


def test_marcar_una_vivienda_de_otro_conjunto_responde_404(andres, torres):
    otro = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(otro.id):
        ajena = Unidad.objects.create(nombre="Casa 1")

    assert marcar(andres, ajena).status_code == 404
    assert marcar(andres, SimpleNamespace(id=uuid.uuid4())).status_code == 404


def test_la_base_rechaza_dos_pagos_del_mismo_mes_y_un_periodo_que_no_es_dia_uno(torres, viviendas):
    with usar_conjunto(torres.id):
        PagoDeAdministracion.objects.create(unidad=viviendas[0], periodo=date(2026, 10, 1))
        with pytest.raises(IntegrityError), transaction.atomic():
            PagoDeAdministracion.objects.create(unidad=viviendas[0], periodo=date(2026, 10, 1))
        with pytest.raises(IntegrityError), transaction.atomic():
            PagoDeAdministracion.objects.create(unidad=viviendas[1], periodo=date(2026, 10, 15))
        # Otra vivienda, o el mes siguiente, sí.
        PagoDeAdministracion.objects.create(unidad=viviendas[1], periodo=date(2026, 10, 1))
        PagoDeAdministracion.objects.create(unidad=viviendas[0], periodo=date(2026, 11, 1))


def test_la_base_no_acepta_un_check_sin_fecha_ni_un_reporte_sin_persona(torres, viviendas, personas):
    with usar_conjunto(torres.id):
        pago = PagoDeAdministracion.objects.create(unidad=viviendas[0], periodo=date(2026, 10, 1))
        with pytest.raises(IntegrityError), transaction.atomic():
            PagoDeAdministracion.objects.filter(pk=pago.pk).update(confirmado_por=personas["laura"])
        with pytest.raises(IntegrityError), transaction.atomic():
            PagoDeAdministracion.objects.filter(pk=pago.pk).update(reportado_en=timezone.now())


def test_los_permisos_nuevos_van_a_su_rol_y_ver_exige_segundo_factor():
    assert {"pago.ver", "pago.confirmar", "pago.reportar"} <= PERMISOS
    assert {"pago.ver", "pago.confirmar"} <= PERMISOS_POR_ROL[Rol.ADMINISTRACION]
    assert "pago.ver" in PERMISOS_POR_ROL[Rol.SECRETARIA] and "pago.confirmar" not in PERMISOS_POR_ROL[Rol.SECRETARIA]
    assert "pago.reportar" in PERMISOS_POR_ROL[Rol.RESIDENTE]
    assert not {"pago.ver", "pago.confirmar"} & PERMISOS_POR_ROL[Rol.RESIDENTE]
    assert not {"pago.ver", "pago.confirmar", "pago.reportar"} & PERMISOS_POR_ROL[Rol.VIGILANCIA]
    assert "pago.ver" in PERMISOS_SENSIBLES
    assert "pago.confirmar" not in PERMISOS_SENSIBLES and "pago.reportar" not in PERMISOS_SENSIBLES


# F2: el residente reporta y el comprobante se sirve por una ruta validada


def test_reportar_deja_el_pago_reportado_con_quien_y_cuando(laura, andres, torres, viviendas):
    antes = timezone.now()

    respuesta = reportar(laura, viviendas[0], subir("transferencia.pdf", PDF))

    assert respuesta.status_code == 201
    assert respuesta.json()["estado"] == "reportado" and respuesta.json()["reportado_por"] == "Laura Gómez"
    assert respuesta.json()["comprobante"]["nombre"] == "transferencia.pdf"
    pago = en_la_base(torres)[0]
    assert pago.reportado_por.nombres == "Laura" and antes <= pago.reportado_en <= timezone.now()
    assert pago.confirmado_por_id is None
    fila = fila_de(tabla(andres), viviendas[0])
    assert fila["estado"] == "reportado" and fila["comprobante"]["nombre"] == "transferencia.pdf"
    with usar_conjunto(torres.id):
        assert Registro.objects.get(accion="pago.reportar").actor.nombres == "Laura"


def test_la_respuesta_no_trae_el_contenido_del_archivo(laura, andres, viviendas):
    reportar(laura, viviendas[0], subir("p.pdf", PDF))

    cuerpo = tabla(andres).content.decode() + laura.get("/pagos/administracion/mios/").content.decode()

    assert PDF.decode("latin-1") not in cuerpo and "contenido" not in cuerpo


def test_un_texto_con_extension_pdf_se_rechaza_y_no_deja_pago(laura, torres, viviendas):
    respuesta = reportar(laura, viviendas[0], subir("virus.pdf", b"esto no es un pdf"))

    assert respuesta.status_code == 400
    assert respuesta.json() == {"archivo": ["El comprobante debe ser un PDF o una imagen JPG o PNG."]}
    assert en_la_base(torres) == []
    with usar_conjunto(torres.id):
        assert not Comprobante.objects.exists()


def test_un_png_llamado_pdf_se_guarda_como_png(laura, torres, viviendas):
    assert reportar(laura, viviendas[0], subir("foto.pdf", PNG)).status_code == 201

    with usar_conjunto(torres.id):
        assert Comprobante.objects.get().tipo == "image/png"


def test_mas_de_5_mb_se_rechaza(laura, viviendas):
    pesado = PDF + b"0" * (5 * 1024 * 1024)

    respuesta = reportar(laura, viviendas[0], subir("grande.pdf", pesado))

    assert respuesta.status_code == 400
    assert respuesta.json() == {"archivo": ["El comprobante no puede pesar más de 5 MB."]}


def test_no_se_reporta_una_vivienda_ajena_ni_de_otro_conjunto(laura, viviendas):
    otro = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(otro.id):
        ajena = Unidad.objects.create(nombre="Casa 1")

    assert reportar(laura, viviendas[1], subir("p.pdf", PDF)).status_code == 404
    assert reportar(laura, ajena, subir("p.pdf", PDF)).status_code == 404


def test_el_propietario_que_no_reside_y_el_arrendatario_pueden_reportar(personas, torres, viviendas):
    with usar_conjunto(torres.id):
        VinculoUnidad.objects.filter(persona=personas["laura"]).update(reside=False)
    laura_sin_residir = cliente_para("laura@torres.com")
    pedro_arrendatario = cliente_para("pedro@torres.com")

    assert reportar(laura_sin_residir, viviendas[0], subir("a.pdf", PDF)).status_code == 201
    assert reportar(pedro_arrendatario, viviendas[0], subir("b.pdf", PDF)).status_code == 201


def test_la_ventana_para_reportar_va_de_once_meses_atras_al_mes_siguiente(laura, viviendas):
    def texto(meses):
        return periodos.texto_de(periodos.sumar_meses(ESTE_MES, meses))

    for meses, estado in ((-11, 201), (1, 201), (-12, 400), (2, 400)):
        respuesta = reportar(laura, viviendas[0], subir("p.pdf", PDF), periodo=texto(meses))

        assert respuesta.status_code == estado, meses
        if estado == 400:
            assert "periodo" in respuesta.json()
    assert reportar(laura, viviendas[0], subir("p.pdf", PDF), periodo="octubre").status_code == 400


def test_con_el_mes_confirmado_ya_no_se_reporta(laura, andres, viviendas):
    marcar(andres, viviendas[0])

    respuesta = reportar(laura, viviendas[0], subir("p.pdf", PDF))

    assert respuesta.status_code == 409
    assert respuesta.json() == {"detail": "Ese mes ya está confirmado por la administración."}


def test_el_segundo_comprobante_no_borra_el_primero_y_el_vigente_es_el_mas_reciente(laura, andres, torres, viviendas):
    reportar(laura, viviendas[0], subir("primero.pdf", PDF))
    reportar(laura, viviendas[0], subir("segundo.png", PNG))

    with usar_conjunto(torres.id):
        assert sorted(Comprobante.objects.values_list("nombre", flat=True)) == ["primero.pdf", "segundo.png"]
    assert len(en_la_base(torres)) == 1
    assert fila_de(tabla(andres), viviendas[0])["comprobante"]["nombre"] == "segundo.png"


def test_administracion_marca_sin_comprobante_y_queda_confirmado(andres, viviendas):
    respuesta = marcar(andres, viviendas[0])

    assert respuesta.json()["estado"] == "confirmado" and respuesta.json()["comprobante"] is None


def id_del_comprobante(respuesta):
    return respuesta.json()["comprobante"]["id"]


def test_quien_vive_en_la_vivienda_gestion_y_secretaria_descargan_y_nadie_mas(
    laura, pedro, lucia, andres, carlos, victor, viviendas
):
    comprobante = id_del_comprobante(reportar(laura, viviendas[0], subir("t.pdf", PDF)))
    url = f"/pagos/administracion/comprobantes/{comprobante}/"

    for quien in (laura, pedro, andres, carlos):
        respuesta = quien.get(url)
        assert respuesta.status_code == 200
        assert respuesta["Content-Type"] == "application/pdf"
        assert respuesta["X-Content-Type-Options"] == "nosniff"
        assert respuesta["Content-Disposition"].startswith('inline; filename="comprobante-')
        assert respuesta.content == PDF
    # El vecino de otra vivienda no lo encuentra; Vigilancia no tiene permiso de pagos.
    assert lucia.get(url).status_code == 404
    assert victor.get(url).status_code == 403
    assert laura.get(f"/pagos/administracion/comprobantes/{uuid.uuid4()}/").status_code == 404


def test_un_png_se_sirve_con_su_tipo_y_no_con_la_extension_del_nombre(laura, andres, viviendas):
    comprobante = id_del_comprobante(reportar(laura, viviendas[0], subir("foto.pdf", PNG)))

    respuesta = andres.get(f"/pagos/administracion/comprobantes/{comprobante}/")

    assert respuesta["Content-Type"] == "image/png"
    assert respuesta["Content-Disposition"].endswith('.png"')


def test_quien_deja_de_tener_vinculo_ya_no_descarga_el_comprobante(laura, personas, torres, viviendas):
    comprobante = id_del_comprobante(reportar(laura, viviendas[0], subir("t.pdf", PDF)))
    with usar_conjunto(torres.id):
        VinculoUnidad.objects.filter(persona=personas["laura"]).update(vigencia_hasta=HOY)

    assert laura.get(f"/pagos/administracion/comprobantes/{comprobante}/").status_code == 404


def test_mis_pagos_trae_los_ultimos_seis_meses_de_cada_vivienda_propia(laura, pedro, lucia, andres, viviendas):
    reportar(laura, viviendas[0], subir("p.pdf", PDF))
    marcar(andres, viviendas[0])

    suyas = laura.get("/pagos/administracion/mios/").json()

    assert [v["unidad"]["nombre"] for v in suyas] == ["Torre 1 – 101"]
    meses = suyas[0]["periodos"]
    assert [m["periodo"] for m in meses] == [
        periodos.texto_de(periodos.sumar_meses(ESTE_MES, -n)) for n in range(6)
    ]
    assert meses[0]["estado"] == "confirmado" and meses[0]["confirmado_por"] == "Andrés Ruiz"
    assert meses[0]["reportado_por"] == "Laura Gómez" and meses[0]["comprobante"]["nombre"] == "p.pdf"
    assert all(m["estado"] == "sin_reporte" for m in meses[1:])
    # El arrendatario ve la misma vivienda; la de la vecina, no.
    assert [v["unidad"]["nombre"] for v in pedro.get("/pagos/administracion/mios/").json()] == ["Torre 1 – 101"]
    assert [v["unidad"]["nombre"] for v in lucia.get("/pagos/administracion/mios/").json()] == ["Torre 1 – 102"]
    # Quien gestiona y no tiene viviendas recibe una lista vacía.
    assert andres.get("/pagos/administracion/mios/").json() == []


# F5: la mora, con la hora simulada


def definir_dia_limite(torres, autor, dia=10, desde=date(2026, 9, 1)):
    with usar_conjunto(torres.id):
        return Regla.objects.create(
            tipo="DIA_LIMITE_DE_PAGO", parametros={"dia": dia}, vigencia_desde=desde, creada_por=autor
        )


def confirmado(torres, vivienda, mes, autor):
    with usar_conjunto(torres.id):
        PagoDeAdministracion.objects.create(
            unidad=vivienda, periodo=mes, confirmado_por=autor, confirmado_en=timezone.now()
        )


def test_sin_regla_de_dia_limite_nadie_esta_en_mora(torres, viviendas):
    with usar_conjunto(torres.id):
        assert mora.periodos_vencidos(date(2026, 10, 20)) == []
        assert mora.unidad_en_mora(viviendas[0], date(2026, 10, 20)) is False


def test_el_dia_limite_no_es_mora_y_el_siguiente_si(torres, viviendas, personas):
    definir_dia_limite(torres, personas["laura"], dia=10, desde=date(2026, 10, 1))

    with usar_conjunto(torres.id):
        assert mora.periodos_vencidos(date(2026, 10, 10)) == []
        assert mora.unidad_en_mora(viviendas[0], date(2026, 10, 10)) is False
        assert mora.periodos_vencidos(date(2026, 10, 11)) == [date(2026, 10, 1)]
        assert mora.unidad_en_mora(viviendas[0], date(2026, 10, 11)) is True


def test_al_confirmar_el_mes_deja_de_estar_en_mora(torres, viviendas, personas):
    definir_dia_limite(torres, personas["laura"], dia=10, desde=date(2026, 10, 1))
    confirmado(torres, viviendas[0], date(2026, 10, 1), personas["laura"])

    with usar_conjunto(torres.id):
        assert mora.unidad_en_mora(viviendas[0], date(2026, 10, 25)) is False
        # La otra vivienda no tiene su check.
        assert mora.unidad_en_mora(viviendas[1], date(2026, 10, 25)) is True


def test_con_dos_meses_vencidos_pagar_solo_el_ultimo_no_saca_de_la_mora(torres, viviendas, personas):
    definir_dia_limite(torres, personas["laura"], dia=10, desde=date(2026, 9, 1))
    confirmado(torres, viviendas[0], date(2026, 10, 1), personas["laura"])

    with usar_conjunto(torres.id):
        assert mora.periodos_vencidos(date(2026, 10, 11)) == [date(2026, 9, 1), date(2026, 10, 1)]
        assert mora.unidad_en_mora(viviendas[0], date(2026, 10, 11)) is True
    confirmado(torres, viviendas[0], date(2026, 9, 1), personas["laura"])
    with usar_conjunto(torres.id):
        assert mora.unidad_en_mora(viviendas[0], date(2026, 10, 11)) is False


def test_un_mes_anterior_a_la_primera_definicion_no_cuenta(torres, viviendas, personas):
    definir_dia_limite(torres, personas["laura"], dia=10, desde=date(2026, 9, 15))

    with usar_conjunto(torres.id):
        # Agosto no está entre los vencidos: nadie debe un mes anterior a la regla.
        assert date(2026, 8, 1) not in mora.periodos_vencidos(date(2026, 10, 20))
        assert mora.primer_periodo() == date(2026, 9, 1)


def test_si_la_regla_se_retira_ya_no_hay_mora(torres, viviendas, personas):
    regla = definir_dia_limite(torres, personas["laura"], dia=10, desde=date(2026, 9, 1))
    with usar_conjunto(torres.id):
        assert mora.unidad_en_mora(viviendas[0], date(2026, 10, 20)) is True
        Regla.objects.filter(pk=regla.pk).update(vigencia_hasta=date(2026, 10, 15))
        assert mora.unidad_en_mora(viviendas[0], date(2026, 10, 20)) is False


def test_la_mora_se_calcula_en_el_conjunto_de_la_vivienda(torres, viviendas, personas):
    """También fuera de una petición: no hace falta fijar el conjunto a mano."""
    definir_dia_limite(torres, personas["laura"], dia=10, desde=date(2026, 9, 1))
    otro = Conjunto.objects.create(nombre="Mirador")
    with usar_conjunto(otro.id):
        ajena = Unidad.objects.create(nombre="Casa 1")

    assert mora.unidad_en_mora(viviendas[0], date(2026, 10, 20)) is True
    assert mora.unidad_en_mora(ajena, date(2026, 10, 20)) is False


def test_ningun_evaluador_evalua_el_dia_limite_y_no_aparece_entre_los_motivos(torres, viviendas, personas):
    definir_dia_limite(torres, personas["laura"], dia=10, desde=date(2026, 9, 1))
    with usar_conjunto(torres.id):
        salon = Area.objects.create(
            nombre="Salón", hora_apertura=time(8), hora_cierre=time(22), duracion_franja_minutos=240, aforo_maximo=50
        )
        solicitud = Solicitud(
            area=salon,
            persona=personas["laura"],
            unidad=viviendas[0],
            fecha=HOY + timedelta(days=3),
            hora_inicio=time(8),
            hora_fin=time(12),
            asistentes=10,
            bloqueo_vence_en=timezone.now(),
        )
        tipos = [resultado.clave for resultado in evaluar(solicitud)]

    assert "DIA_LIMITE_DE_PAGO" not in tipos


def test_de_punta_a_punta_la_vivienda_en_mora_no_reserva_y_al_confirmar_el_mes_si(
    torres, viviendas, personas, andres, laura
):
    """Con paz y salvo y día límite definidos, la vivienda con un mes vencido sin confirmar queda rechazada."""
    with usar_conjunto(torres.id):
        salon = Area.objects.create(
            nombre="Salón comunal", hora_apertura="08:00", hora_cierre="22:00", duracion_franja_minutos=240,
            aforo_maximo=50,
        )
    # Desde el mes anterior: siempre hay al menos un mes vencido, caiga hoy donde caiga.
    mes_anterior = periodos.sumar_meses(ESTE_MES, -1)
    for tipo, parametros in (("DIA_LIMITE_DE_PAGO", {"dia": 28}), ("REQUIERE_PAZ_Y_SALVO", {})):
        creada = andres.post(
            "/reglas/",
            {"tipo": tipo, "parametros": parametros, "vigencia_desde": mes_anterior.isoformat()},
            format="json",
        )
        assert creada.status_code == 201, creada.json()
    manana = HOY + timedelta(days=1)

    def solicitar(hora):
        tomada = laura.post(
            "/reservas/solicitudes/",
            {"area": str(salon.id), "fecha": str(manana), "hora_inicio": hora},
            format="json",
        )
        assert tomada.status_code == 201, tomada.json()
        return laura.post(
            f"/reservas/solicitudes/{tomada.json()['id']}/enviar/",
            {"unidad": str(viviendas[0].id), "motivo": "Cumpleaños", "asistentes": 20},
            format="json",
        )

    rechazada = solicitar("08:00")

    assert rechazada.status_code == 400
    assert "El apartamento no está a paz y salvo con la administración." in rechazada.json()["motivos"]

    # Administración confirma los meses vencidos (el anterior y, si hoy pasó del 28, el actual).
    for mes in (mes_anterior, ESTE_MES):
        assert marcar(andres, viviendas[0], periodos.texto_de(mes)).status_code == 200

    apartada = solicitar("08:00")

    assert apartada.status_code == 200
    assert apartada.json()["estado"] == "APARTADA"
